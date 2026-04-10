from __future__ import annotations

from typing import List, Tuple, Dict, Any, Set

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

    hard_seen: Set[tuple] = set()
    soft_seen: Set[tuple] = set()

    # === allow tolerance near endpoints (airport ingress/egress) ===
    ENDPOINT_TOLERANCE_POINTS = 5  # first/last N points are exempt
    n_points = len(polyline)

    for idx, point in enumerate(polyline):
        lat, lon = point

        # Skip constraint enforcement near endpoints
        if idx < ENDPOINT_TOLERANCE_POINTS or idx > n_points - ENDPOINT_TOLERANCE_POINTS:
            continue

        for c in constraints:
            if c.geometry_type != "polygon" or not c.polygon_points:
                continue

            if not point_in_polygon(lat, lon, c.polygon_points):
                continue

            if not _altitude_conflicts(cruise_alt_ft, c.floor_alt_ft, c.ceiling_alt_ft):
                continue

            conflict_info = {
                "name": c.name,
                "constraint_type": c.constraint_type,
                "mode": c.mode,
                "floor_alt_ft": c.floor_alt_ft,
                "ceiling_alt_ft": c.ceiling_alt_ft,
                "severity": c.severity,
                "metadata": c.metadata,
            }

            key = _constraint_key(c)

            if c.mode == "hard":
                if key not in hard_seen:
                    hard_seen.add(key)
                    hard_conflicts.append(conflict_info)
            else:
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
        "suggested_penalty": sum(item["severity"] for item in soft_conflicts),
    }