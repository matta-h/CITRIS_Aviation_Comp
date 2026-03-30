import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.routing import NODES, build_graph, shortest_path, NO_FLY_ZONES, SLOW_ZONES
from backend.weather import fetch_weather_for_nodes

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

@app.get("/route")
def get_route(start: str, end: str):
    result = shortest_path(start, end)
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
def get_weather():
    global WEATHER_CACHE, WEATHER_LAST_FETCH

    now = time.time()

    if now - WEATHER_LAST_FETCH > WEATHER_TTL:
        WEATHER_CACHE = fetch_weather_for_nodes(NODES)
        WEATHER_LAST_FETCH = now

    return WEATHER_CACHE