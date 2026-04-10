from __future__ import annotations

import math
from typing import List, Dict, Any, Tuple, Optional

import requests


USGS_EPQS_URL = "https://epqs.nationalmap.gov/v1/json"
DEFAULT_TIMEOUT = 20


def sample_elevation_ft(lat: float, lon: float) -> Optional[float]:
    """
    Query terrain elevation in feet for a single point.
    Returns None if unavailable.
    """
    params = {
        "x": lon,
        "y": lat,
        "units": "Feet",
        "wkid": "4326",
        "includeDate": "false",
    }

    try:
        response = requests.get(USGS_EPQS_URL, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        payload = response.json()

        value = (
            payload.get("value")
            or payload.get("elevation")
            or payload.get("Elevation")
        )

        if value is None:
            return None

        return float(value)
    except Exception:
        return None


def _miles_per_degree_lon(lat_deg: float) -> float:
    return 69.0 * math.cos(math.radians(lat_deg))


def _distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    ref_lat = (lat1 + lat2) / 2.0
    dx = (lon2 - lon1) * _miles_per_degree_lon(ref_lat)
    dy = (lat2 - lat1) * 69.0
    return math.hypot(dx, dy)


def _interpolate_points(
    polyline: List[List[float]],
    spacing_miles: float = 2.0,
) -> List[Tuple[float, float]]:
    """
    Sample points along the polyline at roughly spacing_miles intervals.
    """
    if not polyline:
        return []

    sampled: List[Tuple[float, float]] = []
    sampled.append((polyline[0][0], polyline[0][1]))

    for i in range(len(polyline) - 1):
        lat1, lon1 = polyline[i]
        lat2, lon2 = polyline[i + 1]

        seg_dist = _distance_miles(lat1, lon1, lat2, lon2)
        n = max(1, int(math.ceil(seg_dist / spacing_miles)))

        for k in range(1, n + 1):
            t = k / n
            lat = lat1 + t * (lat2 - lat1)
            lon = lon1 + t * (lon2 - lon1)
            sampled.append((lat, lon))

    return sampled


def sample_route_elevations(
    polyline: List[List[float]],
    spacing_miles: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    Returns sampled terrain elevations along a route.
    """
    points = _interpolate_points(polyline, spacing_miles=spacing_miles)
    out: List[Dict[str, Any]] = []

    for lat, lon in points:
        elev_ft = sample_elevation_ft(lat, lon)
        out.append({
            "lat": lat,
            "lon": lon,
            "elevation_ft": elev_ft,
        })

    return out