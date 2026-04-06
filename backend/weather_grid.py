from __future__ import annotations

import numpy as np
import requests
from datetime import datetime
from typing import Dict, List, Tuple

# -----------------------------
# Bounding box
# -----------------------------
LAT_MIN = 36.5278
LAT_MAX = 38.6897
LON_MIN = -122.4115
LON_MAX = -120.2656
GRID_SPACING = 0.2

# -----------------------------
# Thresholds
# -----------------------------
UNSAFE_GUST_MPH = 30.0
UNSAFE_WIND_MPH = 25.0
UNSAFE_VISIBILITY_M = 3000.0

CAUTION_GUST_MPH = 22.0
CAUTION_WIND_MPH = 18.0
CAUTION_VISIBILITY_M = 8000.0
CAUTION_PRECIP_MM = 1.0

# -----------------------------
# Caches
# -----------------------------
HOURLY_GRID_CACHE: Dict[str, List[Dict]] = {}
DAY_GRID_CACHE: Dict[str, Dict[str, List[Dict]]] = {}


def weather_status(
    wind_mph: float,
    gust_mph: float,
    visibility_m: float,
    precip_mm: float,
) -> str:
    if gust_mph >= UNSAFE_GUST_MPH or wind_mph >= UNSAFE_WIND_MPH or visibility_m < UNSAFE_VISIBILITY_M:
        return "unsafe"
    if (
        gust_mph >= CAUTION_GUST_MPH
        or wind_mph >= CAUTION_WIND_MPH
        or visibility_m < CAUTION_VISIBILITY_M
        or precip_mm > CAUTION_PRECIP_MM
    ):
        return "caution"
    return "good"


def safe_float(value, default):
    return float(value) if value is not None else default


def normalize_hour_iso(target_time_iso: str) -> str:
    dt = datetime.fromisoformat(target_time_iso)
    return f"{dt.date().isoformat()}T{dt.hour:02d}:00"


def generate_grid_points() -> List[Dict]:
    lat_points = np.arange(LAT_MIN, LAT_MAX + GRID_SPACING, GRID_SPACING)
    lon_points = np.arange(LON_MIN, LON_MAX + GRID_SPACING, GRID_SPACING)

    grid = []
    for lat in lat_points:
        for lon in lon_points:
            grid.append(
                {
                    "lat": float(lat),
                    "lon": float(lon),
                    "name": f"grid_{round(lat, 3)}_{round(lon, 3)}",
                }
            )
    return grid


def fetch_weather_grid_batched(target_time_iso: str) -> List[Dict]:
    target_time_iso = normalize_hour_iso(target_time_iso)

    if target_time_iso in HOURLY_GRID_CACHE:
        return HOURLY_GRID_CACHE[target_time_iso]

    grid_points = generate_grid_points()
    target_dt = datetime.fromisoformat(target_time_iso)
    day_str = target_dt.date().isoformat()

    latitudes = ",".join(str(p["lat"]) for p in grid_points)
    longitudes = ",".join(str(p["lon"]) for p in grid_points)

    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={latitudes}"
        f"&longitude={longitudes}"
        f"&start_date={day_str}"
        f"&end_date={day_str}"
        "&hourly=wind_speed_10m,wind_gusts_10m,visibility,precipitation"
        "&wind_speed_unit=mph"
        "&timezone=auto"
    )

    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()

    # If only one coordinate is returned, Open-Meteo may return a dict instead of a list.
    # Normalize to a list for consistent handling.
    if isinstance(data, dict) and "latitude" in data:
        data = [data]

    results: List[Dict] = []

    for idx, point_data in enumerate(data):
        hourly = point_data.get("hourly", {})

        times = hourly.get("time", [])
        winds = hourly.get("wind_speed_10m", [])
        gusts = hourly.get("wind_gusts_10m", [])
        vis = hourly.get("visibility", [])
        precip = hourly.get("precipitation", [])

        if target_time_iso in times:
            t_idx = times.index(target_time_iso)
        else:
            # fallback to nearest hour if exact string mismatch occurs
            parsed = [datetime.fromisoformat(t) for t in times]
            target = datetime.fromisoformat(target_time_iso)
            t_idx = min(range(len(parsed)), key=lambda i: abs((parsed[i] - target).total_seconds()))

        wind = safe_float(winds[t_idx] if t_idx < len(winds) else None, 0.0)
        gust = safe_float(gusts[t_idx] if t_idx < len(gusts) else None, 0.0)
        visibility = safe_float(vis[t_idx] if t_idx < len(vis) else None, 99999.0)
        precipitation = safe_float(precip[t_idx] if t_idx < len(precip) else None, 0.0)

        grid_point = grid_points[idx]

        results.append(
            {
                "lat": grid_point["lat"],
                "lon": grid_point["lon"],
                "weather": {
                    "forecast_time": times[t_idx] if times else target_time_iso,
                    "wind_speed_mph": wind,
                    "wind_gusts_mph": gust,
                    "visibility_m": visibility,
                    "precipitation_mm": precipitation,
                    "status": weather_status(wind, gust, visibility, precipitation),
                },
            }
        )

    HOURLY_GRID_CACHE[target_time_iso] = results
    return results


def preload_weather_day(date_str: str) -> Dict:
    if date_str in DAY_GRID_CACHE and len(DAY_GRID_CACHE[date_str]) == 24:
        return {
            "status": "already_cached",
            "date": date_str,
            "hours_loaded": 24,
        }

    DAY_GRID_CACHE[date_str] = {}

    for hour in range(24):
        timestamp = f"{date_str}T{hour:02d}:00"
        DAY_GRID_CACHE[date_str][timestamp] = fetch_weather_grid_batched(timestamp)

    return {
        "status": "cached",
        "date": date_str,
        "hours_loaded": 24,
    }


def get_cached_weather_grid(target_time_iso: str) -> List[Dict]:
    normalized = normalize_hour_iso(target_time_iso)
    dt = datetime.fromisoformat(normalized)
    date_str = dt.date().isoformat()

    if date_str in DAY_GRID_CACHE and normalized in DAY_GRID_CACHE[date_str]:
        return DAY_GRID_CACHE[date_str][normalized]

    return fetch_weather_grid_batched(normalized)