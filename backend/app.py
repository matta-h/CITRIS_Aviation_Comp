import datetime
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.routing_old import NODES, build_graph, shortest_path, NO_FLY_ZONES, SLOW_ZONES
from backend.weather_history import fetch_weather_for_nodes
from backend.weather_grid import get_cached_weather_grid, preload_weather_day
from backend.sim_time import SimulationClock, parse_iso_utc
from datetime import timedelta

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

@app.get("/graph")
def get_graph():
    return build_graph()

@app.get("/weather-grid")
def get_weather_grid(target_time: str):
    return get_cached_weather_grid(target_time)

@app.get("/route")
def get_route(start: str, end: str, departure_time: str | None = None):
    if departure_time is None:
        departure_time = datetime.now().isoformat(timespec="minutes")

    sim_time = parse_iso_utc(departure_time)

    # Create simulation clock (Step 1)
    clock = SimulationClock(
        start_time=sim_time,
        end_time=sim_time + timedelta(minutes=60),
        step=timedelta(minutes=5),
    )

    result = shortest_path(start, end, departure_time, clock)

    if result is None:
        raise HTTPException(status_code=404, detail="No feasible route found")

    return result

@app.get("/obstacles")
def get_obstacles():
    return {
        "no_fly_zones": NO_FLY_ZONES,
        "slow_zones": SLOW_ZONES,
    }

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
    return preload_weather_day(date)