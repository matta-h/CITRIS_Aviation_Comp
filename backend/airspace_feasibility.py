from __future__ import annotations

from typing import List, Tuple, Dict, Any, Set, Optional

from backend.constraint_model import Constraint

DEFAULT_CRUISE_ALT_FT = 3500.0


def point_in_polygon(lat: float, lon: float, polygon_points: List[Tuple[float, float]]) -> bool:
    """
    Ray-casting point-in-polygon test.
    polygon_points are [(lat, lon), ...]
    """
    inside = False
    n = len(polygon_points)
    if n < 3:
        return False

    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon_points[i]
        lat_j, lon_j = polygon_points[j]

        intersects = ((lon_i > lon) != (lon_j > lon)) and (
            lat < (lat_j - lat_i) * (lon - lon_i) / ((lon_j - lon_i) + 1e-12) + lat_i
        )
        if intersects:
            inside = not inside
        j = i

    return inside

def segment_hits_polygon(
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
    polygon_points: List[Tuple[float, float]],
    samples: int = 7,
) -> bool:
    """
    Approximate segment/polygon intersection by sampling points along the segment.
    Good enough for current routing density and much better than endpoint-only checks.
    """
    for i in range(samples + 1):
        t = i / samples
        lat = a_lat + t * (b_lat - a_lat)
        lon = a_lon + t * (b_lon - a_lon)
        if point_in_polygon(lat, lon, polygon_points):
            return True
    return False

def _altitude_conflicts(route_alt_ft: float, floor_alt_ft: float, ceiling_alt_ft: float) -> bool:
    """
    True if the route altitude lies inside the constraint altitude band.
    """
    return floor_alt_ft <= route_alt_ft <= ceiling_alt_ft


def _constraint_key(c: Constraint) -> tuple:
    metadata = c.metadata or {}
    return (
        c.name,
        c.mode,
        c.constraint_type,
        metadata.get("feature_id"),
        c.floor_alt_ft,
        c.ceiling_alt_ft,
    )


def evaluate_airspace_constraints_for_polyline(
    polyline: List[List[float]],
    constraints: List[Constraint],
    cruise_alt_ft: float = DEFAULT_CRUISE_ALT_FT,
    altitude_profile: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Check a lateral route polyline against altitude-aware airspace constraints.

    Current simple model:
    - evaluate each polyline point against polygon constraints
    - if route altitude is inside floor/ceiling band and the point is inside polygon:
        - hard constraint => reject
        - soft constraint => record warning/penalty

    Important:
    - each airspace is counted only once, even if many route points lie inside it
    """
    hard_conflicts: List[Dict[str, Any]] = []
    soft_conflicts: List[Dict[str, Any]] = []

    soft_distance_penalty = 0.0

    hard_seen: Set[tuple] = set()
    soft_seen: Set[tuple] = set()

    # === allow tolerance near endpoints (airport ingress/egress) ===
    ENDPOINT_TOLERANCE_POINTS = 1  # first/last N points are exempt
    endpoint_skip_miles = 3
    n_points = len(polyline)

    for idx in range(1, len(polyline)):
        lat, lon = polyline[idx]
        prev_lat, prev_lon = polyline[idx - 1]
        
        # rough miles conversion
        ref_lat = (lat + prev_lat) / 2.0
        miles_per_deg_lat = 69.0
        miles_per_deg_lon = 69.0 * abs(__import__("math").cos(__import__("math").radians(ref_lat)))

        dx = (lon - prev_lon) * miles_per_deg_lon
        dy = (lat - prev_lat) * miles_per_deg_lat
        segment_length_miles = (dx * dx + dy * dy) ** 0.5

        # Skip constraint enforcement near endpoints
        # compute distance along route
        distance_along = idx * segment_length_miles
        distance_remaining = (n_points - idx) * segment_length_miles

        if distance_along < endpoint_skip_miles or distance_remaining < endpoint_skip_miles:
            continue
        
        point_alt_ft = cruise_alt_ft
        if altitude_profile and idx < len(altitude_profile):
            point_alt_ft = altitude_profile[idx].get("alt_ft", cruise_alt_ft)

        for c in constraints:
            if c.geometry_type != "polygon" or not c.polygon_points:
                continue

            if not segment_hits_polygon(prev_lat, prev_lon, lat, lon, c.polygon_points):
                continue

            if not _altitude_conflicts(point_alt_ft, c.floor_alt_ft, c.ceiling_alt_ft):
                continue

            conflict_info = {
                "name": c.name,
                "constraint_type": c.constraint_type,
                "mode": c.mode,
                "floor_alt_ft": c.floor_alt_ft,
                "ceiling_alt_ft": c.ceiling_alt_ft,
                "route_alt_ft": point_alt_ft,
                "severity": c.severity,
                "metadata": c.metadata,
            }

            key = _constraint_key(c)

            if c.mode == "hard":
                if key not in hard_seen:
                    hard_seen.add(key)
                    hard_conflicts.append(conflict_info)
            else:
                # accumulate penalty based on distance inside soft airspace
                soft_distance_penalty += segment_length_miles * c.severity

                # still record the airspace once for UI/debug
                if key not in soft_seen:
                    soft_seen.add(key)
                    soft_conflicts.append(conflict_info)

    if hard_conflicts:
        print(f"[AIRSPACE DEBUG] hard conflicts: {[c['name'] for c in hard_conflicts]}")
    if soft_conflicts:
        print(f"[AIRSPACE DEBUG] soft conflicts: {[c['name'] for c in soft_conflicts]}")
    return {
        "is_feasible": len(hard_conflicts) == 0,
        "hard_conflicts": hard_conflicts,
        "soft_conflicts": soft_conflicts,
        "suggested_penalty": round(soft_distance_penalty, 2),
    }