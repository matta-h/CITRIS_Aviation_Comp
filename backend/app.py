import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.routing_single import NODES, NO_FLY_ZONES, SLOW_ZONES
from backend.mission_planner import plan_mission
from backend.weather_history import fetch_weather_for_nodes, precache_weather_for_range
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
from backend.airspace_legacy import load_airspace
from backend.routing import build_weather_hazard_zones
from backend.population_adapter import get_population_grid as _get_population_grid
from backend.terrain_adapter import get_terrain_grid as _get_terrain_grid
from backend.fleet import (
    assign_vtol, battery_cost_pct,
    get_fleet_snapshot, get_fleet_params, update_fleet_params, reset_fleet,
)


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

    distance = result.get("total_distance_miles", 0.0)
    arrival_iso = result.get("arrival_time") or departure_time
    flight_id = f"{start}-{end}-{departure_time}"

    exchange_info = None
    if result.get("exchange_required"):
        leg1_dist = result.get("leg1_distance_miles", 0.0)
        leg2_dist = result.get("leg2_distance_miles", 0.0)
        exchange_stop = (result.get("exchange_stops") or [None])[0]
        exchange_delay = result.get("selection_notes", {}).get("exchange_delay_min", 30.0)
        if leg1_dist and exchange_stop:
            from datetime import datetime, timedelta
            leg1_time_min = (leg1_dist / 120.0) * 60.0
            dt = datetime.fromisoformat(departure_time)
            leg1_arrival_iso = (dt + timedelta(minutes=leg1_time_min)).isoformat(timespec="minutes")
            leg2_departure_iso = (dt + timedelta(minutes=leg1_time_min + exchange_delay)).isoformat(timespec="minutes")
            exchange_info = {
                "stop_port": exchange_stop,
                "leg1_arrival_iso": leg1_arrival_iso,
                "leg2_departure_iso": leg2_departure_iso,
                "leg1_dist": leg1_dist,
                "leg2_dist": leg2_dist,
            }

    vtol_id = assign_vtol(
        origin_port=start,
        departure_iso=departure_time,
        arrival_iso=arrival_iso,
        distance_miles=distance,
        flight_id=flight_id,
        destination_port=end,
        exchange_info=exchange_info,
    )

    result["vtol_id"] = vtol_id
    result["vtol_battery_cost_pct"] = round(battery_cost_pct(distance), 1)

    return result


@app.get("/fleet")
def get_fleet(current_time: str | None = None):
    return get_fleet_snapshot(current_time)


@app.get("/fleet/params")
def fleet_params_get():
    return get_fleet_params()


@app.post("/fleet/params")
def fleet_params_update(payload: dict):
    return update_fleet_params(payload)


@app.post("/fleet/reset")
def fleet_reset():
    reset_fleet()
    return {"status": "ok"}

@app.get("/obstacles")
def get_obstacles(target_time: str | None = None):
    weather_hard, weather_soft = build_weather_hazard_zones(
        target_time or datetime.now().isoformat(timespec="minutes")
    )
    return {
        "no_fly_zones": [],
        "slow_zones": [],
        "airspace_zones": [],
        "weather_hard": weather_hard,
        "weather_soft": weather_soft,
    }

@app.get("/population-grid")
def get_population_grid_endpoint(time_of_day: str = "day"):
    if time_of_day not in {"day", "night"}:
        raise HTTPException(status_code=400, detail="time_of_day must be 'day' or 'night'")
    grid = _get_population_grid(time_of_day)
    return [pt for pt in grid if pt["status"] not in ("minimal", "low")]

@app.get("/terrain-grid")
def get_terrain_grid_endpoint():
    return _get_terrain_grid()

@app.post("/terrain-check")
def terrain_check(payload: dict):
    polyline = payload.get("polyline", [])
    cruise_alt_ft = float(payload.get("cruise_alt_ft", 3500.0))
    return evaluate_terrain_for_polyline(polyline, cruise_alt_ft=cruise_alt_ft)

@app.get("/airspace-geojson")
def get_airspace_geojson():
    bounds = (-124.0, 35.5, -119.0, 39.5)
    return get_airspace_geojson_for_frontend(bounds, None)

@app.get("/set-airspace-source")
def set_airspace_source(source: str):
    if source not in {"foreflight", "openair"}:
        raise HTTPException(status_code=400, detail="source must be 'foreflight' or 'openair'")

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
def weather_grid_day_preload(payload: dict):
    date = payload.get("date")
    start_hour = int(payload.get("start_hour", 6))
    end_hour = int(payload.get("end_hour", 22))

    if not date:
        raise HTTPException(status_code=400, detail="Missing 'date'")

    if start_hour < 0 or start_hour > 23 or end_hour < 0 or end_hour > 23:
        raise HTTPException(status_code=400, detail="Hours must be between 0 and 23")

    if end_hour < start_hour:
        raise HTTPException(status_code=400, detail="end_hour must be >= start_hour")

    return precache_weather_for_range(NODES, date, start_hour, end_hour)


@app.get("/weather-grid-day-preload-status")
def weather_grid_day_preload_status():
    return get_preload_status()


@app.post("/simulate-day")
def simulate_day(payload: dict):
    # Import here to avoid circular imports at module load time
    from backend.daily_sim import run_daily_simulation

    date = payload.get("date")
    if not date:
        raise HTTPException(status_code=400, detail="Missing 'date'")

    ticket_price = float(payload.get("ticket_price", 100.0))
    demand_scale = float(payload.get("demand_scale", 1.0))
    start_hour = int(payload.get("start_hour", 6))
    end_hour = int(payload.get("end_hour", 22))
    pilot_enabled = bool(payload.get("pilot_enabled", True))
    battery_min_pct = float(payload.get("battery_min_pct", 20.0))
    turnaround_base_minutes = int(payload.get("turnaround_base_minutes", 20))
    min_passengers = int(payload.get("min_passengers", 1))

    return run_daily_simulation(
        date=date,
        ticket_price=ticket_price,
        demand_scale=demand_scale,
        start_hour=start_hour,
        end_hour=end_hour,
        pilot_enabled=pilot_enabled,
        battery_min_pct=battery_min_pct,
        turnaround_base_minutes=turnaround_base_minutes,
        min_passengers=min_passengers,
    )