from __future__ import annotations

import math
import glob
from typing import List, Dict, Any, Tuple, Optional

import numpy as np
import rasterio

# NorCal bounding box for terrain grid sampling
_GRID_LAT_MIN, _GRID_LAT_MAX = 36.5, 38.9
_GRID_LON_MIN, _GRID_LON_MAX = -122.8, -120.2
_GRID_LAT_STEP = 0.05
_GRID_LON_STEP = 0.06

_TERRAIN_GRID: Optional[List[Dict[str, Any]]] = None


def _classify_elevation(elev_ft: float) -> str:
    if elev_ft < 200:
        return "flat"
    if elev_ft < 800:
        return "low"
    if elev_ft < 2000:
        return "medium"
    if elev_ft < 4000:
        return "high"
    return "alpine"


def get_terrain_grid() -> List[Dict[str, Any]]:
    global _TERRAIN_GRID
    if _TERRAIN_GRID is not None:
        return _TERRAIN_GRID

    points: List[Dict[str, Any]] = []
    lat = _GRID_LAT_MIN
    while lat <= _GRID_LAT_MAX:
        lon = _GRID_LON_MIN
        while lon <= _GRID_LON_MAX:
            elev = sample_elevation_ft(lat, lon)
            if elev is not None:
                points.append({
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                    "elevation_ft": round(elev, 1),
                    "tier": _classify_elevation(elev),
                })
            lon += _GRID_LON_STEP
        lat += _GRID_LAT_STEP

    _TERRAIN_GRID = points
    print(f"[TERRAIN] Grid sampled: {len(points)} points")
    return _TERRAIN_GRID

DEM_FILES = glob.glob("backend/terrain_data/*.tif")

# Load each DEM tile and cache its band array in memory.
# This avoids re-reading the raster from disk on every elevation sample.
# Each tile is kept open so we can use its transform and bounds.
DEM_DATASETS = []
DEM_BANDS: List[np.ndarray] = []

for _path in DEM_FILES:
    # Skip the LandScan population TIFs — they are not elevation data
    if "landscan" in _path.lower():
        continue
    try:
        _ds = rasterio.open(_path)
        _band = _ds.read(1)          # read once, keep in RAM
        DEM_DATASETS.append(_ds)
        DEM_BANDS.append(_band)
    except Exception as _e:
        print(f"[TERRAIN] Failed to load {_path}: {_e}")

print(f"[TERRAIN] Loaded {len(DEM_DATASETS)} DEM tiles")


def sample_elevation_ft(lat: float, lon: float) -> Optional[float]:
    """
    Read terrain elevation from cached DEM band arrays.
    Returns elevation in feet, or None if outside all tiles.
    """
    for ds, band in zip(DEM_DATASETS, DEM_BANDS):
        bounds = ds.bounds

        if not (bounds.left <= lon <= bounds.right and bounds.bottom <= lat <= bounds.top):
            continue

        try:
            row, col = ds.index(lon, lat)

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