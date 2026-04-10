import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.routing_single import NODES, NO_FLY_ZONES, SLOW_ZONES
from backend.mission_planner import plan_mission
from backend.weather_history import fetch_weather_for_nodes
#from backend.sim_time import SimulationClock, parse_iso_utc
from datetime import datetime
from backend.weather_grid import (
    get_cached_weather_grid,
    start_preload_weather_day,
    get_preload_status,
)
from backend import airspace_adapter
from backend.airspace_adapter import build_frontend_airspace_overlays
from backend.airspace_adapter import get_airspace_geojson_for_frontend
from backend.terrain_feasibility import evaluate_terrain_for_polyline
from backend.airspace import load_airspace
from backend.routing import build_weather_hazard_zones


WEATHER_CACHE = {}
WEATHER_LAST_FETCH = 0
WEATHER_TTL = 30  # seconds

app = FastAPI(title="CITRIS Routing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/nodes")
def get_nodes():
    return NODES

@app.get("/weather-grid")
def get_weather_grid(target_time: str):
    return get_cached_weather_grid(target_time)

@app.get("/route")
def get_route(start: str, end: str, departure_time: str | None = None):
    if departure_time is None:
        departure_time = datetime.now().isoformat(timespec="minutes")

    result = plan_mission(start, end, departure_time)

    if result is None:
        raise HTTPException(status_code=404, detail="No feasible route found")

    return result

@app.get("/obstacles")
def get_obstacles(target_time: str | None = None):
    weather_hard, weather_soft = build_weather_hazard_zones(
        target_time or datetime.now().isoformat(timespec="minutes")
    )
    return {
        "no_fly_zones": NO_FLY_ZONES,
        "slow_zones": SLOW_ZONES,
        "airspace_zones": load_airspace(),
        "weather_hard": weather_hard,
        "weather_soft": weather_soft,
    }

@app.post("/terrain-check")
def terrain_check(payload: dict):
    polyline = payload.get("polyline", [])
    cruise_alt_ft = float(payload.get("cruise_alt_ft", 3500.0))
    return evaluate_terrain_for_polyline(polyline, cruise_alt_ft=cruise_alt_ft)

@app.get("/airspace-geojson")
def get_airspace_geojson():
    bounds = (-124.0, 35.5, -119.0, 39.5)
    return get_airspace_geojson_for_frontend(bounds, {"B", "C", "D", "G"})

@app.get("/set-airspace-source")
def set_airspace_source(source: str):
    if source not in {"foreflight", "geojson"}:
        raise HTTPException(status_code=400, detail="source must be 'foreflight' or 'geojson'")

    airspace_adapter.AIRSPACE_SOURCE = source
    airspace_adapter.GLOBAL_AIRSPACE = None
    airspace_adapter.GLOBAL_AIRSPACE_GEOJSON = None

    return {"status": "ok", "source": source}

@app.get("/airspace-overlays")
def get_airspace_overlays():
    bounds = (-124.0, 35.5, -119.0, 39.5)
    overlays = build_frontend_airspace_overlays(bounds)
    print(f"[AIRSPACE OVERLAYS] returning {len(overlays)} overlays")
    return overlays

@app.get("/weather")
def get_weather(target_time: str | None = None):
    global WEATHER_CACHE, WEATHER_LAST_FETCH

    # If caller asks for a specific time, do not use the generic cache
    if target_time is not None:
        return fetch_weather_for_nodes(NODES, target_time)

    now = time.time()

    if now - WEATHER_LAST_FETCH > WEATHER_TTL:
        WEATHER_CACHE = fetch_weather_for_nodes(NODES)
        WEATHER_LAST_FETCH = now

    return WEATHER_CACHE

@app.post("/weather-grid-day-preload")
def weather_grid_day_preload(date: str):
    return start_preload_weather_day(date)


@app.get("/weather-grid-day-preload-status")
def weather_grid_day_preload_status():
    return get_preload_status()
