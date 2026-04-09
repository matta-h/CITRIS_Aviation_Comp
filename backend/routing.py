from __future__ import annotations

import math
import heapq
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.weather_history import fetch_weather_for_nodes
from backend.weather_grid import get_cached_weather_grid
from backend.weather import add_minutes_iso
from backend.routing import (
    NODES,
    NO_FLY_ZONES,
    SLOW_ZONES,
    MAX_LEG_MILES,
    CRUISE_SPEED_MPH,
    HAZARD_SETTINGS,
    scaled_hazard_radius_miles,
    distance_between,
    to_local_miles,
    point_to_segment_distance_miles,
)

FIELD_STEP_MILES = 8.0
FIELD_NEIGHBOR_RADIUS_MILES = 16.0
AIRPORT_CONNECT_RADIUS_MILES = 20.0

def build_weather_hazard_zones(target_time_iso: str) -> List[dict]:
    grid = get_cached_weather_grid(target_time_iso)
    zones: List[dict] = []
    for point in grid:
        wx = point.get("weather", {})
        status = wx.get("status")
        if status not in ("caution", "unsafe"):
            continue
        zones.append({
            "name": f"Weather {status}",
            "lat": point["lat"],
            "lon": point["lon"],
            "radius_miles": 7.0,
            "mode": status,
            "hazard_type": "weather",
        })
    return zones

def map_bounds_from_nodes(buffer_deg: float = 0.35) -> Tuple[float, float, float, float]:
    lats = [n["lat"] for n in NODES.values()]
    lons = [n["lon"] for n in NODES.values()]
    return (
        min(lats) - buffer_deg,
        max(lats) + buffer_deg,
        min(lons) - buffer_deg,
        max(lons) + buffer_deg,
    )

def miles_per_degree(ref_lat: float) -> Tuple[float, float]:
    return 69.0, 69.0 * math.cos(math.radians(ref_lat))

def point_in_circle(lat: float, lon: float, zone: dict) -> bool:
    ref_lat = (lat + zone["lat"]) / 2.0
    x, y = to_local_miles(lat, lon, ref_lat)
    cx, cy = to_local_miles(zone["lat"], zone["lon"], ref_lat)
    r = scaled_hazard_radius_miles(zone["radius_miles"])
    return math.hypot(x - cx, y - cy) <= r

def edge_hits_circle(a: dict, b: dict, zone: dict) -> bool:
    return edge_intersects_point_pair(a["lat"], a["lon"], b["lat"], b["lon"], zone)

def edge_intersects_point_pair(lat1: float, lon1: float, lat2: float, lon2: float, zone: dict) -> bool:
    ref_lat = (lat1 + lat2 + zone["lat"]) / 3.0
    x1, y1 = to_local_miles(lat1, lon1, ref_lat)
    x2, y2 = to_local_miles(lat2, lon2, ref_lat)
    px, py = to_local_miles(zone["lat"], zone["lon"], ref_lat)
    d = point_to_segment_distance_miles(px, py, x1, y1, x2, y2)
    r = scaled_hazard_radius_miles(zone["radius_miles"])
    return d <= r

def all_hard_zones(weather_zones: List[dict]) -> List[dict]:
    hard = list(NO_FLY_ZONES)
    for z in weather_zones:
        if z["mode"] == "unsafe":
            hard.append(z)
    return hard

def all_soft_zones(weather_zones: List[dict]) -> List[dict]:
    soft = list(SLOW_ZONES)
    for z in weather_zones:
        if z["mode"] == "caution":
            soft.append(z)
    return soft

def build_field_points(target_time_iso: str) -> List[dict]:
    lat_min, lat_max, lon_min, lon_max = map_bounds_from_nodes()
    ref_lat = (lat_min + lat_max) / 2.0
    mpd_lat, mpd_lon = miles_per_degree(ref_lat)

    lat_step = FIELD_STEP_MILES / mpd_lat
    lon_step = FIELD_STEP_MILES / mpd_lon

    weather_zones = build_weather_hazard_zones(target_time_iso)
    hard_zones = all_hard_zones(weather_zones)

    points: List[dict] = []
    lat = lat_min
    pid = 0
    while lat <= lat_max:
        lon = lon_min
        while lon <= lon_max:
            blocked = any(point_in_circle(lat, lon, z) for z in hard_zones)
            if not blocked:
                points.append({
                    "id": f"F{pid}",
                    "lat": lat,
                    "lon": lon,
                    "type": "field",
                })
                pid += 1
            lon += lon_step
        lat += lat_step

    return points

def soft_cost_for_edge(a: dict, b: dict, soft_zones: List[dict]) -> float:
    extra = 0.0
    for z in soft_zones:
        if edge_hits_circle(a, b, z):
            if z["hazard_type"] == "weather":
                extra += HAZARD_SETTINGS["caution_penalty"]
            else:
                extra += z.get("penalty", 10.0)
    return extra

def can_connect(a: dict, b: dict, hard_zones: List[dict], max_edge_miles: float) -> bool:
    dist = distance_between(a, b)
    if dist > max_edge_miles:
        return False
    for z in hard_zones:
        if edge_hits_circle(a, b, z):
            return False
    return True

def build_field_graph(target_time_iso: str) -> Dict[str, List[dict]]:
    weather_zones = build_weather_hazard_zones(target_time_iso)
    hard_zones = all_hard_zones(weather_zones)
    soft_zones = all_soft_zones(weather_zones)

    field_points = build_field_points(target_time_iso)
    airports = [
        {"id": k, "lat": v["lat"], "lon": v["lon"], "type": "airport"}
        for k, v in NODES.items()
    ]
    all_points = airports + field_points

    graph: Dict[str, List[dict]] = {p["id"]: [] for p in all_points}

    for i in range(len(all_points)):
        for j in range(i + 1, len(all_points)):
            a = all_points[i]
            b = all_points[j]

            max_edge = FIELD_NEIGHBOR_RADIUS_MILES
            if a["type"] == "airport" or b["type"] == "airport":
                max_edge = AIRPORT_CONNECT_RADIUS_MILES
            if a["type"] == "airport" and b["type"] == "airport":
                max_edge = MAX_LEG_MILES

            if not can_connect(a, b, hard_zones, max_edge):
                continue

            dist = distance_between(a, b)
            cost = dist + soft_cost_for_edge(a, b, soft_zones)

            graph[a["id"]].append({"to": b["id"], "distance_miles": dist, "cost": cost})
            graph[b["id"]].append({"to": a["id"], "distance_miles": dist, "cost": cost})

    return graph

def shortest_path_field(start: str, end: str, departure_time_iso: Optional[str] = None) -> Optional[dict]:
    if departure_time_iso is None:
        departure_time_iso = datetime.now().replace(second=0, microsecond=0).isoformat(timespec="minutes")

    graph = build_field_graph(departure_time_iso)
    if start not in graph or end not in graph:
        return None

    pq = [(0.0, start, [start], [])]
    best: Dict[str, float] = {}

    while pq:
        total_cost, current, path_nodes, path_edges = heapq.heappop(pq)

        if current in best and best[current] <= total_cost:
            continue
        best[current] = total_cost

        if current == end:
            total_distance = sum(e["distance_miles"] for e in path_edges)
            total_minutes = (total_distance / CRUISE_SPEED_MPH) * 60.0
            return {
                "path": path_nodes,
                "edges": path_edges,
                "departure_time": departure_time_iso,
                "arrival_time": add_minutes_iso(departure_time_iso, total_minutes),
                "total_distance_miles": round(total_distance, 2),
                "total_cost": round(total_cost, 2),
                "num_legs": len(path_edges),
                "total_time_minutes": round(total_minutes, 1),
            }

        for edge in graph[current]:
            nxt = edge["to"]
            if nxt in path_nodes:
                continue
            heapq.heappush(
                pq,
                (total_cost + edge["cost"], nxt, path_nodes + [nxt], path_edges + [edge])
            )

    return None