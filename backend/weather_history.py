from __future__ import annotations

from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta, date as date_type
import json
import os
import time
import requests


def _weather_base_url(day_str: str) -> str:
    """Return the correct Open-Meteo base URL for the given date.
    Historical archive only covers dates up to ~5 days ago; use the
    forecast API for recent or future dates."""
    today = date_type.today()
    target = date_type.fromisoformat(day_str)
    # Archive API lags ~5 days; use forecast for anything within that window
    if (today - target).days >= 5:
        return "https://archive-api.open-meteo.com/v1/archive"
    return "https://api.open-meteo.com/v1/forecast"

# -----------------------------
# Thresholds (same as before)
# -----------------------------
UNSAFE_GUST_MPH = 30.0
UNSAFE_WIND_MPH = 25.0
UNSAFE_VISIBILITY_M = 3000.0
UNSAFE_PRECIPITATION = 6.0

CAUTION_GUST_MPH = 22.0
CAUTION_WIND_MPH = 18.0
CAUTION_VISIBILITY_M = 8000.0
CAUTION_PRECIP_MM = 2.5

# -----------------------------
# Persistent disk cache
# -----------------------------
_CACHE_FILE = os.path.join(os.path.dirname(__file__), "data", "weather_cache.json")
_DIRTY = False  # written entries not yet flushed

# In-memory dict keyed by "node_name|time_iso"
_DISK_CACHE: Dict[str, dict] = {}


def _load_cache() -> None:
    global _DISK_CACHE
    try:
        with open(_CACHE_FILE, "r") as f:
            _DISK_CACHE = json.load(f)
        print(f"[WEATHER CACHE] Loaded {len(_DISK_CACHE)} entries from disk")
    except FileNotFoundError:
        _DISK_CACHE = {}
    except Exception as exc:
        print(f"[WEATHER CACHE] Failed to load disk cache: {exc}")
        _DISK_CACHE = {}


def _flush_cache() -> None:
    global _DIRTY
    if not _DIRTY:
        return
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(_DISK_CACHE, f)
        _DIRTY = False
    except Exception as exc:
        print(f"[WEATHER CACHE] Failed to flush disk cache: {exc}")


def _cache_get(node_name: str, time_iso: str) -> Optional[dict]:
    return _DISK_CACHE.get(f"{node_name}|{time_iso}")


def _cache_set(node_name: str, time_iso: str, value: dict) -> None:
    global _DIRTY
    _DISK_CACHE[f"{node_name}|{time_iso}"] = value
    _DIRTY = True


# Compatibility shim — existing code sets WEATHER_CACHE[(name, iso)] = ...
# We replace it with a dict-like wrapper so old call sites keep working.
class _CacheProxy:
    def __contains__(self, key: Tuple[str, str]) -> bool:
        return _cache_get(key[0], key[1]) is not None

    def __getitem__(self, key: Tuple[str, str]) -> dict:
        v = _cache_get(key[0], key[1])
        if v is None:
            raise KeyError(key)
        return v

    def __setitem__(self, key: Tuple[str, str], value: dict) -> None:
        _cache_set(key[0], key[1], value)
        _flush_cache()

    def get(self, key: Tuple[str, str], default=None):
        return _cache_get(key[0], key[1]) or default


WEATHER_CACHE: _CacheProxy = _CacheProxy()

_load_cache()

# -----------------------------
# Status logic (unchanged)
# -----------------------------
def weather_status(wind, gust, visibility, precip):
    if gust >= UNSAFE_GUST_MPH or wind >= UNSAFE_WIND_MPH or visibility < UNSAFE_VISIBILITY_M:
        return "unsafe"
    if (
        gust >= CAUTION_GUST_MPH
        or wind >= CAUTION_WIND_MPH
        or visibility < CAUTION_VISIBILITY_M
        or precip > CAUTION_PRECIP_MM
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

# -----------------------------
# Time matching
# -----------------------------
def hourly_time_strings_for_range(date_str: str, start_hour: int, end_hour: int) -> List[str]:
    return [
        f"{date_str}T{hour:02d}:00"
        for hour in range(start_hour, end_hour + 1)
    ]


def _get_with_retry(url: str, timeout: int = 15, max_retries: int = 4) -> requests.Response:
    """GET with exponential backoff on 429 rate-limit responses."""
    delay = 2.0
    for attempt in range(max_retries):
        r = requests.get(url, timeout=timeout)
        if r.status_code == 429:
            wait = delay * (2 ** attempt)
            print(f"[WEATHER] Rate limited (429) — retrying in {wait:.0f}s (attempt {attempt+1}/{max_retries})")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def fetch_historical_weather_day_for_node(node: dict, day_str: str) -> dict:
    """
    Fetch one full day of hourly weather for a node in a single API call.
    Returns from disk cache when all 24 hours are already present.
    Uses historical archive for past dates and forecast API for future dates.
    """
    # If every hour of the day is already cached, reconstruct from cache
    all_hours = [f"{day_str}T{h:02d}:00" for h in range(24)]
    cached = {t: _cache_get(node["name"], t) for t in all_hours}
    if all(v is not None for v in cached.values()):
        return {t: cached[t] for t in all_hours}

    url = (
        f"{_weather_base_url(day_str)}"
        f"?latitude={node['lat']}"
        f"&longitude={node['lon']}"
        f"&start_date={day_str}"
        f"&end_date={day_str}"
        "&hourly=wind_speed_10m,wind_gusts_10m,visibility,precipitation"
        "&wind_speed_unit=mph"
        "&timezone=auto"
    )

    r = _get_with_retry(url)

    data = r.json().get("hourly", {})
    times = data.get("time", [])
    winds = data.get("wind_speed_10m", [])
    gusts = data.get("wind_gusts_10m", [])
    vis = data.get("visibility", [])
    precip = data.get("precipitation", [])

    if not times:
        raise ValueError("No historical weather data returned")

    results = {}
    for idx, iso_time in enumerate(times):
        wind_raw = winds[idx] if idx < len(winds) else None
        gust_raw = gusts[idx] if idx < len(gusts) else None
        visibility_raw = vis[idx] if idx < len(vis) else None
        precip_raw = precip[idx] if idx < len(precip) else None

        wind = float(wind_raw) if wind_raw is not None else 0.0
        gust = float(gust_raw) if gust_raw is not None else 0.0
        visibility = float(visibility_raw) if visibility_raw is not None else 99999.0
        precipitation = float(precip_raw) if precip_raw is not None else 0.0

        entry = {
            "forecast_time": iso_time,
            "wind_speed_mph": wind,
            "wind_gusts_mph": gust,
            "visibility_m": visibility,
            "precipitation_mm": precipitation,
            "status": weather_status(wind, gust, visibility, precipitation),
        }
        results[iso_time] = entry
        _cache_set(node["name"], iso_time, entry)

    _flush_cache()
    return results

# -----------------------------
# MAIN HISTORICAL FETCH
# -----------------------------
def floor_hour_iso(target_time_iso: str) -> str:
    dt = datetime.fromisoformat(target_time_iso)
    return f"{dt.date().isoformat()}T{dt.hour:02d}:00"


def ceil_hour_iso(target_time_iso: str) -> str:
    dt = datetime.fromisoformat(target_time_iso)
    if dt.minute == 0:
        return f"{dt.date().isoformat()}T{dt.hour:02d}:00"

    dt2 = dt.replace(minute=0) + timedelta(hours=1)
    return f"{dt2.date().isoformat()}T{dt2.hour:02d}:00"


def interpolation_fraction(target_time_iso: str) -> float:
    dt = datetime.fromisoformat(target_time_iso)
    return dt.minute / 60.0


def nearest_hour_index(times: List[str], target_time_iso: str) -> int:
    target_dt = datetime.fromisoformat(target_time_iso)
    best_idx, best_diff = 0, float("inf")
    for i, t in enumerate(times):
        diff = abs((datetime.fromisoformat(t) - target_dt).total_seconds())
        if diff < best_diff:
            best_diff, best_idx = diff, i
    return best_idx

def fetch_historical_weather_for_node(node: dict, target_time_iso: str) -> dict:
    target_dt = datetime.fromisoformat(target_time_iso)
    day_str = target_dt.date().isoformat()

    # Check persistent cache first
    cached = _cache_get(node["name"], target_time_iso)
    if cached is not None:
        return cached

    # Fetch the whole day at once and cache every hour — avoids per-hour API calls
    full_day = fetch_historical_weather_day_for_node(node, day_str)

    # Return the nearest hour to the requested time
    if target_time_iso in full_day:
        return full_day[target_time_iso]

    idx = nearest_hour_index(list(full_day.keys()), target_time_iso)
    return list(full_day.values())[idx]

# -----------------------------
# MULTI-NODE FETCH
# -----------------------------
def interpolate_node_weather(a: dict, b: dict, target_time_iso: str, alpha: float) -> dict:
    wind = a.get("wind_speed_mph", 0.0) + alpha * (b.get("wind_speed_mph", 0.0) - a.get("wind_speed_mph", 0.0))
    gust = a.get("wind_gusts_mph", 0.0) + alpha * (b.get("wind_gusts_mph", 0.0) - a.get("wind_gusts_mph", 0.0))
    visibility = a.get("visibility_m", 99999.0) + alpha * (b.get("visibility_m", 99999.0) - a.get("visibility_m", 99999.0))
    precipitation = a.get("precipitation_mm", 0.0) + alpha * (b.get("precipitation_mm", 0.0) - a.get("precipitation_mm", 0.0))

    return {
        "forecast_time": target_time_iso,
        "wind_speed_mph": round(wind, 2),
        "wind_gusts_mph": round(gust, 2),
        "visibility_m": round(visibility, 1),
        "precipitation_mm": round(precipitation, 2),
        "status": weather_status(wind, gust, visibility, precipitation),
    }

def fetch_weather_for_nodes(nodes: Dict[str, dict], target_time_iso: Optional[str] = None) -> Dict[str, dict]:
    results = {}

    if target_time_iso is None:
        target_time_iso = datetime.now().replace(minute=0, second=0).isoformat(timespec="minutes")

    dt = datetime.fromisoformat(target_time_iso)

    # exact hour: existing behavior
    if dt.minute == 0:
        for node_id, node in nodes.items():
            try:
                results[node_id] = fetch_historical_weather_for_node(node, target_time_iso)
            except Exception as exc:
                results[node_id] = {
                    "status": "unknown",
                    "error": str(exc),
                }
        return results

    lower_iso = floor_hour_iso(target_time_iso)
    upper_iso = ceil_hour_iso(target_time_iso)
    alpha = interpolation_fraction(target_time_iso)

    for node_id, node in nodes.items():
        try:
            lower = fetch_historical_weather_for_node(node, lower_iso)
            upper = fetch_historical_weather_for_node(node, upper_iso)
            results[node_id] = interpolate_node_weather(lower, upper, target_time_iso, alpha)
        except Exception as exc:
            results[node_id] = {
                "status": "unknown",
                "error": str(exc),
            }

    return results

def precache_weather_for_range(
    nodes: Dict[str, dict],
    date_str: str,
    start_hour: int,
    end_hour: int,
) -> Dict[str, object]:
    """
    Pre-cache hourly node weather for a selected date/time window.

    Optimization:
    - one API request per node per day
    - fill WEATHER_CACHE for each requested hour
    """
    requested_times = hourly_time_strings_for_range(date_str, start_hour, end_hour)
    populated = 0
    skipped = 0
    errors = []

    for node_id, node in nodes.items():
        missing_times = [
            t for t in requested_times
            if (node["name"], t) not in WEATHER_CACHE
        ]

        if not missing_times:
            skipped += len(requested_times)
            continue

        try:
            full_day = fetch_historical_weather_day_for_node(node, date_str)

            for t in requested_times:
                cache_key = (node["name"], t)
                if cache_key in WEATHER_CACHE:
                    skipped += 1
                    continue

                if t in full_day:
                    WEATHER_CACHE[cache_key] = full_day[t]
                    populated += 1

        except Exception as exc:
            errors.append(f"{node_id}: {exc}")

    return {
        "status": "ok",
        "date": date_str,
        "start_hour": start_hour,
        "end_hour": end_hour,
        "cached_entries": populated,
        "skipped_entries": skipped,
        "errors": errors,
    }