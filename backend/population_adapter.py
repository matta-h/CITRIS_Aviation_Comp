from __future__ import annotations

import os
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

# ─────────────────────────────────────────────────────────────
# LandScan USA 2021 — CONUS population density adapter
#
# Raw TIF stores ambient population counts per ~90m cell.
# We sample a coarse grid over the NorCal operational region
# and classify cells into density tiers for:
#   1. Frontend display (colored grid overlay)
#   2. Routing soft penalties (avoid dense areas when possible)
#
# Files expected at backend/terrain_data/:
#   landscan-usa-2021-conus-day.tif
#   landscan-usa-2021-conus-night.tif
# ─────────────────────────────────────────────────────────────

# NorCal bounding box — matches weather_grid.py
LAT_MIN =  36.33625
LAT_MAX =  38.88125
LON_MIN = -122.6111
LON_MAX = -120.0661

# Sampling resolution — one point every ~5 miles
LAT_SPACING = 0.07   # ~5 miles
LON_SPACING = 0.09   # ~5 miles

# Population density thresholds (people per 90m cell, LandScan ambient)
# Calibrated for NorCal: Bay Area cores run 2000–8000+, rural Central Valley < 10
THRESHOLD_LOW       =   50   # rural / open land
THRESHOLD_MEDIUM    =  300   # suburban
THRESHOLD_HIGH      = 1500   # dense suburban / urban
THRESHOLD_VERY_HIGH = 5000   # downtown / dense urban core

# Routing soft penalty (minutes added to route score per zone intersection)
# Kept modest — population avoidance is a tiebreaker, not a hard constraint
PENALTY_HIGH       = 5.0
PENALTY_VERY_HIGH  = 12.0

# Soft zone radius (miles) — how far around a dense cell we apply the penalty
PENALTY_RADIUS_HIGH       = 3.0
PENALTY_RADIUS_VERY_HIGH  = 4.0

DATA_DIR = os.path.join(os.path.dirname(__file__), "terrain_data")
DAY_TIF   = os.path.join(DATA_DIR, "landscan-usa-2021-conus-day.tif")
NIGHT_TIF = os.path.join(DATA_DIR, "landscan-usa-2021-conus-night.tif")

# Module-level cache so we only open files and sample once
_DAY_GRID:   Optional[List[Dict]] = None
_NIGHT_GRID: Optional[List[Dict]] = None


def _classify(pop: float) -> str:
    if pop >= THRESHOLD_VERY_HIGH:
        return "very_high"
    if pop >= THRESHOLD_HIGH:
        return "high"
    if pop >= THRESHOLD_MEDIUM:
        return "medium"
    if pop >= THRESHOLD_LOW:
        return "low"
    return "minimal"


def _sample_tif(tif_path: str) -> List[Dict]:
    """
    Sample the LandScan CONUS TIF over the NorCal bounding box.
    Returns a list of {lat, lon, population, status} dicts.

    Performance: reads the raster band ONCE, then samples by index.
    The full CONUS TIF is ~75MB but we only touch the NorCal window.
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
    except ImportError:
        print("[POPULATION] rasterio not installed — population grid unavailable")
        return []

    if not os.path.exists(tif_path):
        print(f"[POPULATION] TIF not found: {tif_path}")
        return []

    print(f"[POPULATION] Opening {os.path.basename(tif_path)}...")

    results: List[Dict] = []

    try:
        with rasterio.open(tif_path) as ds:
            nodata = ds.nodata

            # Read only the NorCal window — much faster than full CONUS band
            window = from_bounds(
                left=LON_MIN - 0.1,
                bottom=LAT_MIN - 0.1,
                right=LON_MAX + 0.1,
                top=LAT_MAX + 0.1,
                transform=ds.transform,
            )

            print(f"[POPULATION] Reading NorCal window...")
            band = ds.read(1, window=window)
            win_transform = ds.window_transform(window)

            print(f"[POPULATION] Window shape: {band.shape}, sampling grid...")

            lats = np.arange(LAT_MIN, LAT_MAX + LAT_SPACING, LAT_SPACING)
            lons = np.arange(LON_MIN, LON_MAX + LON_SPACING, LON_SPACING)

            for lat in lats:
                for lon in lons:
                    try:
                        # Convert lat/lon to row/col within the windowed band
                        col_f, row_f = ~win_transform * (lon, lat)
                        row = int(row_f)
                        col = int(col_f)

                        if row < 0 or col < 0 or row >= band.shape[0] or col >= band.shape[1]:
                            continue

                        value = float(band[row, col])

                        if nodata is not None and value == nodata:
                            continue
                        if value < 0:
                            continue

                        results.append({
                            "lat": round(float(lat), 5),
                            "lon": round(float(lon), 5),
                            "population": int(value),
                            "status": _classify(value),
                        })

                    except Exception:
                        continue

    except Exception as exc:
        print(f"[POPULATION] Failed to read {tif_path}: {exc}")
        return []

    print(f"[POPULATION] Sampled {len(results)} points from {os.path.basename(tif_path)}")
    return results


def get_population_grid(time_of_day: str = "day") -> List[Dict]:
    """
    Returns the cached population grid for the given time of day.
    First call reads and samples the TIF; subsequent calls use cache.

    time_of_day: "day" or "night"
    """
    global _DAY_GRID, _NIGHT_GRID

    if time_of_day == "night":
        if _NIGHT_GRID is None:
            _NIGHT_GRID = _sample_tif(NIGHT_TIF)
        return _NIGHT_GRID
    else:
        if _DAY_GRID is None:
            _DAY_GRID = _sample_tif(DAY_TIF)
        return _DAY_GRID


def build_population_penalty_zones(time_of_day: str = "day") -> List[Dict]:
    """
    Returns soft routing penalty zones for high and very-high density areas.
    These are added to the field router's soft_zones list.

    Each zone matches the soft_zone dict format used in routing.py:
    {
        "name": str,
        "geometry": "circle",
        "lat": float,
        "lon": float,
        "radius_miles": float,
        "mode": "soft",
        "hazard_type": "population",
        "penalty": float,
    }
    """
    grid = get_population_grid(time_of_day)
    zones: List[Dict] = []

    for point in grid:
        status = point["status"]

        if status == "very_high":
            zones.append({
                "name": f"Population very_high ({point['population']} pop)",
                "geometry": "circle",
                "lat": point["lat"],
                "lon": point["lon"],
                "radius_miles": PENALTY_RADIUS_VERY_HIGH,
                "mode": "soft",
                "hazard_type": "population",
                "penalty": PENALTY_VERY_HIGH,
            })
        elif status == "high":
            zones.append({
                "name": f"Population high ({point['population']} pop)",
                "geometry": "circle",
                "lat": point["lat"],
                "lon": point["lon"],
                "radius_miles": PENALTY_RADIUS_HIGH,
                "mode": "soft",
                "hazard_type": "population",
                "penalty": PENALTY_HIGH,
            })

    print(f"[POPULATION] Built {len(zones)} penalty zones ({time_of_day})")
    return zones


# ── Pre-load at import time so routing calls never block ──────
# Runs once when the module is first imported (server startup).
# Both day and night grids are loaded so routing can switch
# between them without any delay.
import threading as _threading

def _preload_both() -> None:
    print("[POPULATION] Pre-loading day grid at startup...")
    get_population_grid("day")
    print("[POPULATION] Pre-loading night grid at startup...")
    get_population_grid("night")
    print("[POPULATION] Pre-load complete.")

_preload_thread = _threading.Thread(target=_preload_both, daemon=True)
_preload_thread.start()