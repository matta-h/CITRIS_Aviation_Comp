from __future__ import annotations

from typing import Dict, List, Optional

from backend.routing_single import NODES, distance_between
from backend.routing import shortest_path_field

MAX_DIRECT_MISSION_MILES = 85.0
EFFECTIVE_AIRSPEED_MPH = 120.0
EXCHANGE_DELAY_MIN = 30.0


def flight_time_minutes(distance_miles: float) -> float:
    return (distance_miles / EFFECTIVE_AIRSPEED_MPH) * 60.0


def build_direct_candidate(start: str, end: str, departure_time_iso: str) -> Optional[dict]:
    route = shortest_path_field(start, end, departure_time_iso)
    if not route:
        return None

    return {
        "mission_type": "direct",
        "stops": [start, end],
        "route": route,
        "num_exchanges": 0,
        "score": route["total_time_minutes"],
        "exchange_required": False,
    }


def build_exchange_candidate(
    start: str,
    exchange: str,
    end: str,
    departure_time_iso: str,
) -> Optional[dict]:
    leg1 = shortest_path_field(start, exchange, departure_time_iso)
    if not leg1:
        return None

    leg2 = shortest_path_field(exchange, end, departure_time_iso)
    if not leg2:
        return None

    total_distance = leg1["total_distance_miles"] + leg2["total_distance_miles"]
    total_time = leg1["total_time_minutes"] + leg2["total_time_minutes"] + EXCHANGE_DELAY_MIN

    combined_polyline = leg1["polyline"] + leg2["polyline"][1:]
    combined_raw_polyline = leg1["raw_polyline"] + leg2["raw_polyline"][1:]
    combined_path = leg1["path"] + leg2["path"][1:]
    combined_legs = leg1["legs"] + leg2["legs"]

    return {
        "mission_type": "exchange",
        "stops": [start, exchange, end],
        "route": {
            "path": combined_path,
            "polyline": combined_polyline,
            "raw_polyline": combined_raw_polyline,
            "legs": combined_legs,
            "total_distance_miles": round(total_distance, 2),
            "total_time_minutes": round(total_time, 1),
            "total_cost": round(total_time, 2),
            "num_legs": len(combined_legs),
            "exchange_stop": exchange,
        },
        "num_exchanges": 1,
        "score": total_time,
        "exchange_required": True,
    }


def candidate_exchange_nodes(start: str, end: str) -> List[str]:
    candidates = []
    for node_id in NODES.keys():
        if node_id in {start, end}:
            continue
        candidates.append(node_id)
    return candidates


def plan_mission(start: str, end: str, departure_time_iso: str) -> Optional[dict]:
    raw_direct_distance = distance_between(NODES[start], NODES[end])

    candidates: List[dict] = []

    # Direct allowed only if raw direct distance is under 85 mi
    if raw_direct_distance < MAX_DIRECT_MISSION_MILES:
        direct = build_direct_candidate(start, end, departure_time_iso)
        if direct:
            candidates.append(direct)

    # Exchange candidates always allowed, but become mandatory at >= 85 mi
    for mid in candidate_exchange_nodes(start, end):
        exchange = build_exchange_candidate(start, mid, end, departure_time_iso)
        if exchange:
            candidates.append(exchange)

    if not candidates:
        return None

    best = min(candidates, key=lambda c: c["score"])
    best_route = best["route"]

    return {
        **best_route,
        "selected_mission_type": best["mission_type"],
        "exchange_required": best["exchange_required"],
        "exchange_stops": best["stops"][1:-1],
        "score": round(best["score"], 2),
        "raw_direct_distance_miles": round(raw_direct_distance, 2),
    }