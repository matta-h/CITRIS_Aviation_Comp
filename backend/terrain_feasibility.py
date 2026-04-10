from __future__ import annotations

from typing import Dict, Any, List

from backend.terrain_adapter import sample_route_elevations


DEFAULT_CLEARANCE_MARGIN_FT = 1000.0
DEFAULT_SAMPLING_SPACING_MILES = 2.0


def evaluate_terrain_for_polyline(
    polyline: List[List[float]],
    cruise_alt_ft: float,
    clearance_margin_ft: float = DEFAULT_CLEARANCE_MARGIN_FT,
    spacing_miles: float = DEFAULT_SAMPLING_SPACING_MILES,
) -> Dict[str, Any]:
    """
    Terrain feasibility for a route polyline.

    Current simple model:
    - sample elevations along route
    - find highest terrain point
    - require cruise altitude >= max terrain + clearance margin
    """
    samples = sample_route_elevations(polyline, spacing_miles=spacing_miles)

    valid_elevations = [
        s["elevation_ft"] for s in samples
        if s.get("elevation_ft") is not None
    ]

    if not valid_elevations:
        return {
            "terrain_clearance_ok": True,
            "max_terrain_ft": None,
            "min_clearance_ft": None,
            "samples": samples,
            "reason": "No terrain data available",
        }

    max_terrain_ft = max(valid_elevations)
    min_clearance_ft = cruise_alt_ft - max_terrain_ft
    terrain_clearance_ok = min_clearance_ft >= clearance_margin_ft

    return {
        "terrain_clearance_ok": terrain_clearance_ok,
        "max_terrain_ft": round(max_terrain_ft, 1),
        "min_clearance_ft": round(min_clearance_ft, 1),
        "required_margin_ft": clearance_margin_ft,
        "samples": samples,
    }