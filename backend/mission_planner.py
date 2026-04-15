from __future__ import annotations

import math
import time
from typing import List, Optional, Tuple

from backend.routing_single import NODES, distance_between
from backend.routing import shortest_path_field
from backend.airspace_adapter import get_global_airspace, filter_constraints_by_bounds
from backend.airspace_feasibility import evaluate_airspace_constraints_for_polyline
from backend.terrain_feasibility import evaluate_terrain_for_polyline
from backend.weather_history import fetch_weather_for_nodes
from backend.altitude_profile import generate_altitude_profile

MAX_DIRECT_MISSION_MILES = 85.0
EFFECTIVE_AIRSPEED_MPH = 120.0
EXCHANGE_DELAY_MIN = 30.0

TERRAIN_CLEARANCE_MARGIN_FT = 300
DEFAULT_CRUISE_ALT_FT = 4500.0
AIRSPACE_SOFT_PENALTY_MIN = 0.5
CORRIDOR_PENALTY_PER_MILE_MIN = 1.5

EARLY_ACCEPT_DIRECT_DISTANCE_MILES = 75.0
EARLY_ACCEPT_DIRECT_SCORE_MIN = 45.0

DEBUG_MISSION = True
LEG_CACHE = {}

VERTIPORT_ELEVATION_FT = {
    "UCSC": 784.0,
    "UCB": 328.0,
    "UCD": 120.0,   # estimated 5+1 parking structure rooftop
    "UCM": 260.0,   # base elevation + estimated future rooftop/pad height
    "KSQL": 7.0,
    "KNUQ": 30.0,
    "KLVK": 371.0,
    "KCVH": 223.0,
    "KSNS": 79.0,
    "KOAR": 135.0,
}


def dprint(msg: str) -> None:
    if DEBUG_MISSION:
        print(msg)

def vertiport_elevation_ft(node_id: str) -> float:
    return float(VERTIPORT_ELEVATION_FT.get(node_id, 0.0))

def bounds_for_stops(stops: List[str], buffer_deg: float = 0.4) -> Tuple[float, float, float, float]:
    lats = [NODES[s]["lat"] for s in stops]
    lons = [NODES[s]["lon"] for s in stops]

    west = min(lons) - buffer_deg
    south = min(lats) - buffer_deg
    east = max(lons) + buffer_deg
    north = max(lats) + buffer_deg
    return (west, south, east, north)

def apply_terrain_checks(
    route: dict,
    cruise_alt_ft: float = DEFAULT_CRUISE_ALT_FT,
) -> Optional[dict]:
    altitude_profile = route.get("altitude_profile")
    terrain_eval = evaluate_terrain_for_polyline(
        route["polyline"],
        cruise_alt_ft=cruise_alt_ft,
        clearance_margin_ft=TERRAIN_CLEARANCE_MARGIN_FT,
        altitude_profile=altitude_profile,
    )

    if not terrain_eval["terrain_clearance_ok"]:
        dprint(
            f"[TERRAIN] rejected route: max_terrain_ft={terrain_eval['max_terrain_ft']} "
            f"min_clearance_ft={terrain_eval['min_clearance_ft']}"
        )
        return None

    updated = dict(route)
    updated["terrain_feasibility"] = terrain_eval
    return updated

def point_to_segment_distance_miles(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)

    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)

def solve_leg_cached(start: str, end: str, departure_time_iso: str):
    key = (start, end, departure_time_iso)
    if key in LEG_CACHE:
        dprint(f"[MISSION] leg cache hit {start}->{end}")
        return LEG_CACHE[key]

    t0 = time.time()
    result = shortest_path_field(start, end, departure_time_iso)
    dprint(f"[MISSION] leg solve {start}->{end} took {time.time() - t0:.2f}s")
    LEG_CACHE[key] = result
    return result

def corridor_deviation_penalty_minutes(
    polyline: List[List[float]],
    start: str,
    end: str,
) -> float:
    if len(polyline) < 2:
        return 0.0

    s = NODES[start]
    e = NODES[end]
    ref_lat = (s["lat"] + e["lat"]) / 2.0

    miles_per_deg_lat = 69.0
    miles_per_deg_lon = 69.0 * math.cos(math.radians(ref_lat))

    x1 = s["lon"] * miles_per_deg_lon
    y1 = s["lat"] * miles_per_deg_lat
    x2 = e["lon"] * miles_per_deg_lon
    y2 = e["lat"] * miles_per_deg_lat

    max_dev = 0.0
    avg_dev = 0.0
    count = 0

    for lat, lon in polyline:
        px = lon * miles_per_deg_lon
        py = lat * miles_per_deg_lat
        d = point_to_segment_distance_miles(px, py, x1, y1, x2, y2)
        max_dev = max(max_dev, d)
        avg_dev += d
        count += 1

    if count > 0:
        avg_dev /= count

    return (0.7 * avg_dev + 0.3 * max_dev) * CORRIDOR_PENALTY_PER_MILE_MIN


def apply_airspace_checks(
    route: dict,
    stops: List[str],
    cruise_alt_ft: float = DEFAULT_CRUISE_ALT_FT,
    origin_alt_ft: float = 0.0,
    destination_alt_ft: float = 0.0,
) -> Optional[dict]:
    t0 = time.time()
    bounds = bounds_for_stops(stops)
    dprint(f"[AIRSPACE] filter start stops={stops} bounds={bounds}")

    all_constraints = get_global_airspace()
    airspace_constraints = filter_constraints_by_bounds(all_constraints, bounds)

    t1 = time.time()
    dprint(f"[AIRSPACE] prepared {len(airspace_constraints)} constraints in {t1 - t0:.2f}s")

    altitude_profile = generate_altitude_profile(
        route["polyline"],
        cruise_alt_ft=cruise_alt_ft,
        climb_distance_miles=4.0,
        descent_distance_miles=4.0,
        origin_alt_ft=origin_alt_ft,
        destination_alt_ft=destination_alt_ft,
    )

    feasibility = evaluate_airspace_constraints_for_polyline(
        route["polyline"],
        airspace_constraints,
        cruise_alt_ft=cruise_alt_ft,
        altitude_profile=altitude_profile,
    )

    t2 = time.time()
    dprint(
        f"[AIRSPACE] feasibility checked in {t2 - t1:.2f}s "
        f"hard={len(feasibility['hard_conflicts'])} "
        f"soft={len(feasibility['soft_conflicts'])}"
    )

    if not feasibility["is_feasible"]:
        dprint(f"[AIRSPACE] rejected route for stops={stops}")
        return None

    updated = dict(route)
    updated["airspace_feasibility"] = feasibility
    updated["altitude_profile"] = altitude_profile
    updated["max_alt_ft"] = max((p["alt_ft"] for p in altitude_profile), default=cruise_alt_ft)
    return updated

def endpoint_weather_ok(start: str, end: str, departure_time_iso: str) -> bool:
    weather = fetch_weather_for_nodes(
        {
            start: NODES[start],
            end: NODES[end],
        },
        departure_time_iso,
    )

    start_status = weather.get(start, {}).get("status")
    end_status = weather.get(end, {}).get("status")

    if start_status == "unsafe":
        dprint(f"[MISSION] rejected: unsafe departure weather at {start}")
        return False

    if end_status == "unsafe":
        dprint(f"[MISSION] rejected: unsafe arrival weather at {end}")
        return False

    return True

def build_direct_candidate(
    start: str,
    end: str,
    departure_time_iso: str,
    cruise_alt_ft: float = DEFAULT_CRUISE_ALT_FT,
) -> Optional[dict]:
    dprint(f"[MISSION] trying direct {start}->{end}")
    if not endpoint_weather_ok(start, end, departure_time_iso):
        return None

    t_direct = time.time()
    route = shortest_path_field(start, end, departure_time_iso)
    dprint(f"[MISSION] direct solve {start}->{end} took {time.time() - t_direct:.2f}s")
    
    if not route:
        dprint("[MISSION] direct failed: no route")
        return None

    if route["total_distance_miles"] >= MAX_DIRECT_MISSION_MILES:
        dprint(
            f"[MISSION] direct rejected: routed distance "
            f"{route['total_distance_miles']:.2f} >= {MAX_DIRECT_MISSION_MILES}"
        )
        return None

    route = apply_airspace_checks(
        route,
        [start, end],
        cruise_alt_ft=cruise_alt_ft,
        origin_alt_ft=vertiport_elevation_ft(start),
        destination_alt_ft=vertiport_elevation_ft(end),
    )
    if not route:
        dprint("[MISSION] direct rejected by airspace")
        return None

    route = apply_terrain_checks(route, cruise_alt_ft=cruise_alt_ft)
    if not route:
        dprint("[MISSION] direct rejected by terrain")
        return None

    soft_conflicts = route["airspace_feasibility"]["soft_conflicts"]
    airspace_penalty = len(soft_conflicts) * AIRSPACE_SOFT_PENALTY_MIN
    corridor_penalty = corridor_deviation_penalty_minutes(route["polyline"], start, end)
    score = route["total_time_minutes"] + airspace_penalty + corridor_penalty

    dprint(
        f"[MISSION] direct accepted: dist={route['total_distance_miles']:.2f} "
        f"time={route['total_time_minutes']:.2f} "
        f"airspace_penalty={airspace_penalty:.2f} "
        f"corridor_penalty={corridor_penalty:.2f} "
        f"score={score:.2f}"
    )

    return {
        "mission_type": "direct",
        "stops": [start, end],
        "route": {
            **route,
            "selection_notes": {
                "airspace_penalty_min": round(airspace_penalty, 2),
                "corridor_penalty_min": round(corridor_penalty, 2),
            },
        },
        "num_exchanges": 0,
        "score": score,
        "exchange_required": False,
    }


def build_exchange_candidate(
    start: str,
    exchange: str,
    end: str,
    departure_time_iso: str,
    cruise_alt_ft: float = DEFAULT_CRUISE_ALT_FT,
) -> Optional[dict]:
    dprint(f"[MISSION] trying exchange {start}->{exchange}->{end}")
    if not endpoint_weather_ok(start, exchange, departure_time_iso):
        return None

    if not endpoint_weather_ok(exchange, end, departure_time_iso):
        return None

    t_leg1 = time.time()
    leg1 = solve_leg_cached(start, exchange, departure_time_iso)
    dprint(f"[MISSION] leg1 solve {start}->{exchange} took {time.time() - t_leg1:.2f}s")
    if not leg1:
        dprint("[MISSION] exchange rejected: no first leg")
        return None

    t_leg2 = time.time()
    leg2 = solve_leg_cached(exchange, end, departure_time_iso)
    dprint(f"[MISSION] leg2 solve {exchange}->{end} took {time.time() - t_leg2:.2f}s")
    if not leg2:
        dprint("[MISSION] exchange rejected: no second leg")
        return None

    if leg1["total_distance_miles"] >= MAX_DIRECT_MISSION_MILES:
        dprint(
            f"[MISSION] exchange rejected: leg1 distance "
            f"{leg1['total_distance_miles']:.2f} >= {MAX_DIRECT_MISSION_MILES}"
        )
        return None

    if leg2["total_distance_miles"] >= MAX_DIRECT_MISSION_MILES:
        dprint(
            f"[MISSION] exchange rejected: leg2 distance "
            f"{leg2['total_distance_miles']:.2f} >= {MAX_DIRECT_MISSION_MILES}"
        )
        return None

    leg1_checked = apply_airspace_checks(
        leg1,
        [start, exchange],
        cruise_alt_ft=cruise_alt_ft,
        origin_alt_ft=vertiport_elevation_ft(start),
        destination_alt_ft=vertiport_elevation_ft(exchange),
    )
    if not leg1_checked:
        dprint("[MISSION] exchange rejected by airspace on leg1")
        return None

    leg1_checked = apply_terrain_checks(leg1_checked, cruise_alt_ft=cruise_alt_ft)
    if not leg1_checked:
        dprint("[MISSION] exchange rejected by terrain on leg1")
        return None

    leg2_checked = apply_airspace_checks(
        leg2,
        [exchange, end],
        cruise_alt_ft=cruise_alt_ft,
        origin_alt_ft=vertiport_elevation_ft(exchange),
        destination_alt_ft=vertiport_elevation_ft(end),
    )
    if not leg2_checked:
        dprint("[MISSION] exchange rejected by airspace on leg2")
        return None

    leg2_checked = apply_terrain_checks(leg2_checked, cruise_alt_ft=cruise_alt_ft)
    if not leg2_checked:
        dprint("[MISSION] exchange rejected by terrain on leg2")
        return None

    total_distance = leg1_checked["total_distance_miles"] + leg2_checked["total_distance_miles"]
    total_time = leg1_checked["total_time_minutes"] + leg2_checked["total_time_minutes"] + EXCHANGE_DELAY_MIN
    # Initialize flight_data with proper structure
    flight_data = {
        "leg1Polyline": leg1_checked.get("polyline", []),
        "leg2Polyline": leg2_checked.get("polyline", []),
        "exchangeDelayMinutes": EXCHANGE_DELAY_MIN,
        "leg1Minutes": leg1_checked["total_time_minutes"],
        "leg2Minutes": leg2_checked["total_time_minutes"],
    }

    combined_polyline = leg1_checked["polyline"] + leg2_checked["polyline"][1:]
    combined_raw_polyline = leg1_checked["raw_polyline"] + leg2_checked["raw_polyline"][1:]
    combined_path = leg1_checked["path"] + leg2_checked["path"][1:]
    combined_legs = leg1_checked["legs"] + leg2_checked["legs"]

    soft_conflicts = (
        leg1_checked["airspace_feasibility"]["soft_conflicts"]
        + leg2_checked["airspace_feasibility"]["soft_conflicts"]
    )
    airspace_penalty = len(soft_conflicts) * AIRSPACE_SOFT_PENALTY_MIN
    corridor_penalty = corridor_deviation_penalty_minutes(combined_polyline, start, end)
    score = total_time + airspace_penalty + corridor_penalty

    dprint(
        f"[MISSION] exchange accepted via {exchange}: "
        f"dist={total_distance:.2f} "
        f"time={total_time:.2f} "
        f"airspace_penalty={airspace_penalty:.2f} "
        f"corridor_penalty={corridor_penalty:.2f} "
        f"score={score:.2f}"
    )

    return {
        "mission_type": "exchange",
        "stops": [start, exchange, end],
        "route": {
            "polyline": flight_data["leg1Polyline"] + flight_data["leg2Polyline"][1:],
            "legs": leg1_checked["legs"] + leg2_checked["legs"],
            "total_distance_miles": round(total_distance, 2),
            "total_time_minutes": round(
                flight_data["leg1Minutes"] + flight_data["exchangeDelayMinutes"] + flight_data["leg2Minutes"], 1
            ),
            "altitude_profile_leg1": leg1_checked.get("altitude_profile", []),
            "altitude_profile_leg2": leg2_checked.get("altitude_profile", []),
            "airspace_feasibility": {
                "is_feasible": True,
                "hard_conflicts": [],
                "soft_conflicts": leg1_checked["airspace_feasibility"]["soft_conflicts"]
                                + leg2_checked["airspace_feasibility"]["soft_conflicts"],
            },
            "exchange_stop": exchange,
            "selection_notes": {
                "exchange_delay_min": EXCHANGE_DELAY_MIN,
            },
        },
        "num_exchanges": 1,
        "score": total_time + airspace_penalty + corridor_penalty,
        "exchange_required": True,
    }


def candidate_exchange_nodes(start: str, end: str) -> List[str]:
    airport_ids = ["KSQL", "KLVK", "KCVH", "KSNS", "KOAR", "KNUQ"]
    candidates = [node_id for node_id in airport_ids if node_id not in {start, end}]

    return sorted(
        candidates,
        key=lambda node_id: (
            distance_between(NODES[start], NODES[node_id]) +
            distance_between(NODES[node_id], NODES[end])
        ),
    )

def _finalize_selected_candidate(best: dict, raw_direct_distance: float, cruise_alt_ft: float, departure_time_iso: str) -> dict:
    best_route = best["route"]

    # compute times
    departure_time = departure_time_iso
    total_minutes = best_route.get("total_time_minutes", 0)

    # simple ISO time add (minutes → seconds)
    try:
        from datetime import datetime, timedelta
        dt = datetime.fromisoformat(departure_time_iso)
        arrival_dt = dt + timedelta(minutes=total_minutes)
        arrival_time = arrival_dt.isoformat(timespec="minutes")
    except:
        arrival_time = None

    
    return {
        **best_route,
        "selected_mission_type": best["mission_type"],
        "exchange_required": best["exchange_required"],
        "exchange_stops": best["stops"][1:-1],
        "score": round(best["score"], 2),
        "raw_direct_distance_miles": round(raw_direct_distance, 2),
        "selected_cruise_alt_ft": cruise_alt_ft,
        "departure_time": departure_time,
        "arrival_time": arrival_time,
    }

def plan_mission(
    start: str,
    end: str,
    departure_time_iso: str,
    cruise_alt_ft: float = DEFAULT_CRUISE_ALT_FT,
) -> Optional[dict]:
    t0 = time.time()
    raw_direct_distance = distance_between(NODES[start], NODES[end])

    dprint(f"[MISSION] start {start}->{end} dep={departure_time_iso}")
    dprint(f"[MISSION] raw_direct_distance={raw_direct_distance:.2f} mi")

    candidates: List[dict] = []

    direct = None
    if raw_direct_distance < MAX_DIRECT_MISSION_MILES:
        direct = build_direct_candidate(
            start,
            end,
            departure_time_iso,
            cruise_alt_ft=cruise_alt_ft,
        )
        if direct:
            candidates.append(direct)

            direct_dist = direct["route"]["total_distance_miles"]
            direct_score = direct["score"]

            # Early accept strong direct missions:
            # safely under 85 miles and already much better than any realistic exchange mission.
            if (
                direct_dist <= EARLY_ACCEPT_DIRECT_DISTANCE_MILES
                and direct_score <= EARLY_ACCEPT_DIRECT_SCORE_MIN
            ):
                dprint(
                    f"[MISSION] early accept direct: "
                    f"dist={direct_dist:.2f} score={direct_score:.2f}"
                )
                dprint(f"[MISSION] completed in {time.time() - t0:.2f}s")
                return _finalize_selected_candidate(direct, raw_direct_distance, cruise_alt_ft, departure_time_iso)

    exchange_nodes = candidate_exchange_nodes(start, end)
    dprint(f"[MISSION] exchange candidates: {exchange_nodes}")

    max_exchange_candidates = 3

    for mid in exchange_nodes[:max_exchange_candidates]:
        exchange = build_exchange_candidate(
            start,
            mid,
            end,
            departure_time_iso,
            cruise_alt_ft=cruise_alt_ft,
        )

        if exchange:
            candidates.append(exchange)

            # Early accept a very good exchange route,
            # but only if it beats the already-found direct route.
            if exchange["score"] <= 105:
                if direct is None or exchange["score"] < direct["score"]:
                    dprint(
                        f"[MISSION] early accept exchange via {mid}: "
                        f"score={exchange['score']:.2f}"
                    )
                    dprint(f"[MISSION] completed in {time.time() - t0:.2f}s")
                    return _finalize_selected_candidate(
                        exchange,
                        raw_direct_distance,
                        cruise_alt_ft,
                        departure_time_iso,
                    )

    if not candidates:
        dprint("[MISSION] no feasible candidates")
        return None

    best = min(candidates, key=lambda c: c["score"])

    dprint(
        f"[MISSION] best candidate type={best['mission_type']} "
        f"stops={best['stops']} score={best['score']:.2f}"
    )
    dprint(f"[MISSION] completed in {time.time() - t0:.2f}s")

    return _finalize_selected_candidate(best, raw_direct_distance, cruise_alt_ft, departure_time_iso)