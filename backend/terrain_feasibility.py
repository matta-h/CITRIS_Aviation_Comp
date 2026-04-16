from __future__ import annotations

from typing import Dict, Any, List, Optional

from backend.terrain_adapter import sample_route_elevations
from backend.altitude_profile import generate_altitude_profile


DEFAULT_CLEARANCE_MARGIN_FT = 1000.0
DEFAULT_SAMPLING_SPACING_MILES = 2.0


def evaluate_terrain_for_polyline(
    polyline: List[List[float]],
    cruise_alt_ft: float,
    clearance_margin_ft: float = DEFAULT_CLEARANCE_MARGIN_FT,
    spacing_miles: float = DEFAULT_SAMPLING_SPACING_MILES,
    altitude_profile: Optional[List[Dict[str, Any]]] = None,
    endpoint_skip_distance_miles: float = 0.5,
) -> Dict[str, Any]:
    """
    Terrain feasibility for a route polyline.

    Current simple model:
    - sample elevations along route
    - find highest terrain point
    - require cruise altitude >= max terrain + clearance margin
    """
    samples = sample_route_elevations(polyline, spacing_miles=spacing_miles)

    sampled_polyline = [
        [s["lat"], s["lon"]]
        for s in samples
    ]

    sampled_altitude_profile = None
    if altitude_profile:
        origin_alt_ft = altitude_profile[0].get("alt_ft", cruise_alt_ft) if altitude_profile else cruise_alt_ft
        destination_alt_ft = altitude_profile[-1].get("alt_ft", cruise_alt_ft) if altitude_profile else cruise_alt_ft

        sampled_altitude_profile = generate_altitude_profile(
            sampled_polyline,
            cruise_alt_ft=cruise_alt_ft,
            climb_distance_miles=4.0,
            descent_distance_miles=4.0,
            origin_alt_ft=origin_alt_ft,
            destination_alt_ft=destination_alt_ft,
        )

    valid_samples = [
        s for s in samples
        if s.get("elevation_ft") is not None
    ]

    if not valid_samples:
        return {
            "terrain_clearance_ok": True,
            "max_terrain_ft": None,
            "min_clearance_ft": None,
            "samples": samples,
            "reason": "No terrain data available",
        }

    max_terrain_ft = max(s["elevation_ft"] for s in valid_samples)

    min_clearance_ft = float("inf")
    worst_sample = None

    total_route_distance = 0.0
    if sampled_altitude_profile:
        total_route_distance = sampled_altitude_profile[-1].get("distance_miles", 0.0)

    for idx, sample in enumerate(samples):
        if sample.get("elevation_ft") is None:
            continue

        route_alt_ft = cruise_alt_ft
        sample_distance_miles = 0.0

        if sampled_altitude_profile and idx < len(sampled_altitude_profile):
            route_alt_ft = sampled_altitude_profile[idx].get("alt_ft", cruise_alt_ft)
            sample_distance_miles = sampled_altitude_profile[idx].get("distance_miles", 0.0)

        dist_from_end = total_route_distance - sample_distance_miles

        # Ignore terrain-clearance enforcement very close to departure/arrival
        if (
            sample_distance_miles < endpoint_skip_distance_miles
            or dist_from_end < endpoint_skip_distance_miles
        ):
            continue

        clearance_ft = route_alt_ft - sample["elevation_ft"]

        if clearance_ft < min_clearance_ft:
            min_clearance_ft = clearance_ft
            worst_sample = {
                **sample,
                "route_alt_ft": round(route_alt_ft, 1),
                "clearance_ft": round(clearance_ft, 1),
                "distance_miles": round(sample_distance_miles, 3),
            }

    if min_clearance_ft == float("inf"):
        min_clearance_ft = None
        terrain_clearance_ok = True
    else:
        terrain_clearance_ok = min_clearance_ft >= clearance_margin_ft

    return {
        "terrain_clearance_ok": terrain_clearance_ok,
        "max_terrain_ft": round(max_terrain_ft, 1),
        "min_clearance_ft": round(min_clearance_ft, 1) if min_clearance_ft is not None else None,
        "required_margin_ft": clearance_margin_ft,
        "endpoint_skip_distance_miles": endpoint_skip_distance_miles,
        "worst_sample": worst_sample,
        "samples": samples,
    }