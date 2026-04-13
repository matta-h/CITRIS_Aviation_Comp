from __future__ import annotations

import math
from typing import List, Dict, Any


def _segment_distance_miles(a: List[float], b: List[float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b

    ref_lat = (lat1 + lat2) / 2.0
    miles_per_deg_lat = 69.0
    miles_per_deg_lon = 69.0 * math.cos(math.radians(ref_lat))

    dx = (lon2 - lon1) * miles_per_deg_lon
    dy = (lat2 - lat1) * miles_per_deg_lat
    return math.hypot(dx, dy)


def cumulative_distances_miles(polyline: List[List[float]]) -> List[float]:
    if not polyline:
        return []

    cumulative = [0.0]
    total = 0.0

    for i in range(1, len(polyline)):
        total += _segment_distance_miles(polyline[i - 1], polyline[i])
        cumulative.append(total)

    return cumulative


def altitude_at_distance(
    dist_along_miles: float,
    total_distance_miles: float,
    cruise_alt_ft: float,
    climb_distance_miles: float,
    descent_distance_miles: float,
    origin_alt_ft: float = 0.0,
    destination_alt_ft: float = 0.0,
) -> float:
    if total_distance_miles <= 0:
        return origin_alt_ft

    dist_from_end = total_distance_miles - dist_along_miles

    departure_transition_alt_ft = min(cruise_alt_ft, origin_alt_ft + 1500.0)
    arrival_transition_alt_ft = min(cruise_alt_ft, destination_alt_ft + 1500.0)

    vertical_transition_miles = 0.15

    # Departure VTOL lift: near-vertical climb to safer transition altitude
    if dist_along_miles < vertical_transition_miles:
        frac = max(0.0, min(1.0, dist_along_miles / vertical_transition_miles))
        return origin_alt_ft + frac * (departure_transition_alt_ft - origin_alt_ft)

    # Forward climb from transition altitude to cruise altitude
    if dist_along_miles < climb_distance_miles:
        frac = max(
            0.0,
            min(
                1.0,
                (dist_along_miles - vertical_transition_miles)
                / max(climb_distance_miles - vertical_transition_miles, 1e-6),
            ),
        )
        return departure_transition_alt_ft + frac * (cruise_alt_ft - departure_transition_alt_ft)

    # Arrival VTOL descent: stay higher until near destination, then descend
    if dist_from_end < vertical_transition_miles:
        frac = max(0.0, min(1.0, dist_from_end / vertical_transition_miles))
        return destination_alt_ft + frac * (arrival_transition_alt_ft - destination_alt_ft)

    if dist_from_end < descent_distance_miles:
        frac = max(
            0.0,
            min(
                1.0,
                (dist_from_end - vertical_transition_miles)
                / max(descent_distance_miles - vertical_transition_miles, 1e-6),
            ),
        )
        return arrival_transition_alt_ft + frac * (cruise_alt_ft - arrival_transition_alt_ft)

    return cruise_alt_ft


def generate_altitude_profile(
    polyline: List[List[float]],
    cruise_alt_ft: float = 4500.0,
    climb_distance_miles: float = 2.0,
    descent_distance_miles: float = 2.0,
    origin_alt_ft: float = 0.0,
    destination_alt_ft: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Build a simple 2.5D altitude profile for a route polyline.

    Model:
    - first N miles: linear climb from origin_alt_ft to cruise_alt_ft
    - middle: hold cruise_alt_ft
    - last N miles: linear descent from cruise_alt_ft to destination_alt_ft
    """
    if not polyline:
        return []

    cumulative = cumulative_distances_miles(polyline)
    total_distance = cumulative[-1] if cumulative else 0.0

    profile: List[Dict[str, Any]] = []

    for idx, (point, dist_along) in enumerate(zip(polyline, cumulative)):
        lat, lon = point
        alt_ft = altitude_at_distance(
            dist_along_miles=dist_along,
            total_distance_miles=total_distance,
            cruise_alt_ft=cruise_alt_ft,
            climb_distance_miles=climb_distance_miles,
            descent_distance_miles=descent_distance_miles,
            origin_alt_ft=origin_alt_ft,
            destination_alt_ft=destination_alt_ft,
        )

        profile.append(
            {
                "idx": idx,
                "lat": lat,
                "lon": lon,
                "distance_miles": round(dist_along, 3),
                "alt_ft": round(alt_ft, 1),
            }
        )

    return profile