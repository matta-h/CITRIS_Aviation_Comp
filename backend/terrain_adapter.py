from __future__ import annotations

import math
import glob
from typing import List, Dict, Any, Tuple, Optional

import rasterio

DEM_FILES = glob.glob("backend/terrain_data/*.tif")
DEM_DATASETS = [rasterio.open(path) for path in DEM_FILES]

print(f"[TERRAIN] Loaded {len(DEM_DATASETS)} DEM tiles")


def sample_elevation_ft(lat: float, lon: float) -> Optional[float]:
    """
    Read terrain elevation from local DEM GeoTIFF tiles.
    Returns elevation in feet.
    """
    for ds in DEM_DATASETS:
        bounds = ds.bounds

        if not (bounds.left <= lon <= bounds.right and bounds.bottom <= lat <= bounds.top):
            continue

        try:
            row, col = ds.index(lon, lat)
            band = ds.read(1)

            if row < 0 or col < 0 or row >= band.shape[0] or col >= band.shape[1]:
                continue

            value = band[row, col]

            if ds.nodata is not None and value == ds.nodata:
                continue

            # USGS DEM GeoTIFF elevations are typically in meters
            return float(value) * 3.28084

        except Exception:
            continue

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