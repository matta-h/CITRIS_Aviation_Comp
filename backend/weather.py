from __future__ import annotations

from typing import Dict, Optional
from datetime import datetime, timedelta
import requests

UNSAFE_GUST_MPH = 30.0
UNSAFE_WIND_MPH = 25.0
UNSAFE_VISIBILITY_M = 3000.0

CAUTION_GUST_MPH = 22.0
CAUTION_WIND_MPH = 18.0
CAUTION_VISIBILITY_M = 8000.0
CAUTION_PRECIP_MM = 1.0


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


def weather_penalty(entry: dict) -> float:
    status = entry.get("status", "good")
    if status == "unsafe":
        return float("inf")
    if status == "caution":
        return 20.0
    return 0.0


def nearest_hour_index(times: list[str], target_iso: str) -> int:
    target = datetime.fromisoformat(target_iso)
    parsed = [datetime.fromisoformat(t) for t in times]
    best_idx = min(range(len(parsed)), key=lambda i: abs((parsed[i] - target).total_seconds()))
    return best_idx


def fetch_forecast_for_node(node: dict, target_time_iso: Optional[str] = None) -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={node['lat']}"
        f"&longitude={node['lon']}"
        "&hourly=wind_speed_10m,wind_gusts_10m,visibility,precipitation"
        "&wind_speed_unit=mph"
        "&forecast_days=2"
        "&timezone=auto"
    )

    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json().get("hourly", {})

    times = data.get("time", [])
    winds = data.get("wind_speed_10m", [])
    gusts = data.get("wind_gusts_10m", [])
    vis = data.get("visibility", [])
    precip = data.get("precipitation", [])

    if not times:
        raise ValueError("No hourly forecast data returned")

    if target_time_iso is None:
        idx = 0
        forecast_time = times[idx]
    else:
        idx = nearest_hour_index(times, target_time_iso)
        forecast_time = times[idx]

    wind = float(winds[idx]) if idx < len(winds) else 0.0
    gust = float(gusts[idx]) if idx < len(gusts) else 0.0
    visibility = float(vis[idx]) if idx < len(vis) else 99999.0
    precipitation = float(precip[idx]) if idx < len(precip) else 0.0

    return {
        "forecast_time": forecast_time,
        "wind_speed_mph": wind,
        "wind_gusts_mph": gust,
        "visibility_m": visibility,
        "precipitation_mm": precipitation,
        "status": weather_status(wind, gust, visibility, precipitation),
    }


def fetch_weather_for_nodes(nodes: Dict[str, dict], target_time_iso: Optional[str] = None) -> Dict[str, dict]:
    results: Dict[str, dict] = {}

    for node_id, node in nodes.items():
        try:
            results[node_id] = fetch_forecast_for_node(node, target_time_iso)
        except Exception as exc:
            results[node_id] = {
                "forecast_time": target_time_iso,
                "wind_speed_mph": None,
                "wind_gusts_mph": None,
                "visibility_m": None,
                "precipitation_mm": None,
                "status": "unknown",
                "error": str(exc),
            }

    return results


def add_minutes_iso(start_iso: str, minutes: float) -> str:
    dt = datetime.fromisoformat(start_iso)
    return (dt + timedelta(minutes=minutes)).isoformat(timespec="minutes")