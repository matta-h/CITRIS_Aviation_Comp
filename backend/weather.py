from __future__ import annotations

from typing import Dict
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


def fetch_weather_for_nodes(nodes: Dict[str, dict]) -> Dict[str, dict]:
    results: Dict[str, dict] = {}

    for node_id, node in nodes.items():
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={node['lat']}"
            f"&longitude={node['lon']}"
            "&current=wind_speed_10m,wind_gusts_10m,visibility,precipitation"
            "&wind_speed_unit=mph"
        )

        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json().get("current", {})

            wind = float(data.get("wind_speed_10m", 0.0))
            gust = float(data.get("wind_gusts_10m", 0.0))
            visibility = float(data.get("visibility", 99999.0))
            precip = float(data.get("precipitation", 0.0))

            results[node_id] = {
                "wind_speed_mph": wind,
                "wind_gusts_mph": gust,
                "visibility_m": visibility,
                "precipitation_mm": precip,
                "status": weather_status(wind, gust, visibility, precip),
            }
        except Exception as exc:
            results[node_id] = {
                "wind_speed_mph": None,
                "wind_gusts_mph": None,
                "visibility_m": None,
                "precipitation_mm": None,
                "status": "unknown",
                "error": str(exc),
            }

    return results


def weather_penalty(entry: dict) -> float:
    status = entry.get("status", "good")
    if status == "unsafe":
        return float("inf")
    if status == "caution":
        return 20.0
    return 0.0