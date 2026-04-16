from __future__ import annotations

import math
import heapq
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.geometry import point_in_polygon
from backend.airspace_legacy import load_airspace
from backend.geometry import (segment_hits_zone)
from backend.weather_grid import get_cached_weather_grid
from backend.weather import add_minutes_iso
from backend.routing_single import (
    NODES,
    MAX_LEG_MILES,
    scaled_hazard_radius_miles,
    distance_between,
    to_local_miles,
)
from backend.population_adapter import build_population_penalty_zones

FIELD_STEP_MILES = 4
FIELD_NEIGHBOR_RADIUS_MILES = 10
AIRPORT_CONNECT_RADIUS_MILES = 15.0

HARD_BUFFER_FACTOR = 1.15
SOFT_BUFFER_FACTOR = 0.90

EFFECTIVE_AIRSPEED_MPH = 120.0
TRANSFER_TIME_MIN = 30.0
TIME_TIE_THRESHOLD_MIN = 5.0
AIRSPACE_CACHE = load_airspace()

USE_LEGACY_STATIC_OBSTACLES = False
LEGACY_NO_FLY_ZONES = []
LEGACY_SLOW_ZONES = []

FIELD_GRAPH_CACHE = {}
FIELD_GRAPH_CACHE_MAX = 12

# Population penalty zones — cached by time-of-day (day/night).
# Loaded once from TIF on first routing call, stable across sim dates.
_POPULATION_ZONES_CACHE: Dict[str, List[dict]] = {}

def _get_population_zones(target_time_iso: str) -> List[dict]:
    """
    Return cached population soft zones, keyed by day/night.
    Returns [] immediately if the pre-load hasn't finished yet,
    so routing is never blocked waiting for the TIF.
    Day = 06:00–19:59, Night = 20:00–05:59.
    """
    try:
        hour = datetime.fromisoformat(target_time_iso).hour
    except Exception:
        hour = 12

    tod = "day" if 6 <= hour < 20 else "night"

    if tod not in _POPULATION_ZONES_CACHE:
        # Check if the grid is already loaded by population_adapter
        from backend.population_adapter import _DAY_GRID, _NIGHT_GRID
        grid_ready = _DAY_GRID if tod == "day" else _NIGHT_GRID

        if grid_ready is None:
            # Pre-load not done yet — skip penalty zones for this call
            print(f"[POPULATION] Grid not ready yet, skipping zones for this route")
            return []

        try:
            _POPULATION_ZONES_CACHE[tod] = build_population_penalty_zones(tod)
        except Exception as exc:
            print(f"[POPULATION] Failed to build penalty zones: {exc}")
            _POPULATION_ZONES_CACHE[tod] = []

    return _POPULATION_ZONES_CACHE[tod]

def point_in_zone(lat, lon, zone):
    if zone.get("geometry", "circle") == "circle":
        return point_in_circle(lat, lon, zone)
    elif zone.get("geometry") == "polygon":
        poly = zone["points"]
        return point_in_polygon(lat, lon, poly)
    return False

def edge_hits_hard_zone(a: dict, b: dict, zone: dict) -> bool:
    if zone.get("geometry", "circle") == "circle":
        return segment_hits_zone(a, b, zone, radius_scale=HARD_BUFFER_FACTOR)
    return segment_hits_zone(a, b, zone)

def can_connect(a: dict, b: dict, hard_zones: list[dict], max_edge_miles: float) -> bool:
    dist = distance_between(a, b)
    if dist > max_edge_miles:
        return False
    return not any(edge_hits_hard_zone(a, b, z) for z in hard_zones)

def build_weather_hazard_zones(target_time_iso: str) -> tuple[list[dict], list[dict]]:
    grid = get_cached_weather_grid(target_time_iso) or []
    hard = []
    soft = []

    for point in grid:
        wx = point.get("weather", {})
        status = wx.get("status")
        if status == "unsafe":
            hard.append({
                "name": "Unsafe weather",
                "geometry": "circle",
                "lat": point["lat"],
                "lon": point["lon"],
                "radius_miles": 9.0,
                "mode": "hard",
                "hazard_type": "weather",
            })
        elif status == "caution":
            soft.append({
                "name": "Caution weather",
                "geometry": "circle",
                "lat": point["lat"],
                "lon": point["lon"],
                "radius_miles": 7.0,
                "mode": "soft",
                "hazard_type": "weather",
                "penalty": 10.0,
            })

    return hard, soft


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
    r = scaled_hazard_radius_miles(zone["radius_miles"]) * HARD_BUFFER_FACTOR
    return math.hypot(x - cx, y - cy) <= r

def build_field_points(target_time_iso: str) -> List[dict]:
    lat_min, lat_max, lon_min, lon_max = map_bounds_from_nodes()
    ref_lat = (lat_min + lat_max) / 2.0
    mpd_lat, mpd_lon = miles_per_degree(ref_lat)

    lat_step = FIELD_STEP_MILES / mpd_lat
    lon_step = FIELD_STEP_MILES / mpd_lon

    weather_hard, weather_soft = build_weather_hazard_zones(target_time_iso)
    airspace = AIRSPACE_CACHE
    hard_zones = list(LEGACY_NO_FLY_ZONES if USE_LEGACY_STATIC_OBSTACLES else []) + weather_hard + airspace

    points: List[dict] = []
    lat = lat_min
    pid = 0
    while lat <= lat_max:
        lon = lon_min
        while lon <= lon_max:
            blocked = any(point_in_zone(lat, lon, z) for z in hard_zones)
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

def soft_penalty_minutes_for_edge(
    a: dict,
    b: dict,
    soft_zones: List[dict],
    flight_time_min: float,
) -> float:
    extra = 0.0
    sample_ts = [0.2, 0.4, 0.6, 0.8]

    for z in soft_zones:
        zone_penalty = 0.0

        for t in sample_ts:
            lat = a["lat"] + t * (b["lat"] - a["lat"])
            lon = a["lon"] + t * (b["lon"] - a["lon"])

            ref_lat = (lat + z["lat"]) / 2.0
            x, y = to_local_miles(lat, lon, ref_lat)
            cx, cy = to_local_miles(z["lat"], z["lon"], ref_lat)

            dist_to_center = math.hypot(x - cx, y - cy)
            r = scaled_hazard_radius_miles(z["radius_miles"]) * SOFT_BUFFER_FACTOR

            sample_penalty = 0.0

            if dist_to_center < r:
                if z["hazard_type"] == "weather":
                    sample_penalty = 0.45 * flight_time_min
                else:
                    sample_penalty = 0.2 * flight_time_min

            elif dist_to_center < r * 1.2:
                proximity = (r * 1.2 - dist_to_center) / (r * 0.2)
                proximity = max(0.0, min(1.0, proximity))

                if z["hazard_type"] == "weather":
                    sample_penalty = proximity * 0.2 * flight_time_min
                else:
                    sample_penalty = proximity * 0.1 * flight_time_min

            zone_penalty = max(zone_penalty, sample_penalty)

        extra += zone_penalty

    return min(extra, 1.5 * flight_time_min)

def simplify_polyline_with_hard_and_soft_zones(polyline, hard_zones, soft_zones):
    if len(polyline) <= 2:
        return polyline

    simplified = [polyline[0]]
    i = 0

    while i < len(polyline) - 1:
        best_j = i + 1

        for j in range(len(polyline) - 1, i, -1):
            a = {"lat": polyline[i][0], "lon": polyline[i][1]}
            b = {"lat": polyline[j][0], "lon": polyline[j][1]}

            blocked = False
            for z in hard_zones:
                if edge_hits_hard_zone(a, b, z):
                    blocked = True
                    break
            if blocked:
                continue

            # Do not allow simplification to create a shortcut that cuts deeply through soft zones
            seg_dist = distance_between(a, b)
            seg_time_min = (seg_dist / EFFECTIVE_AIRSPEED_MPH) * 60.0
            soft_penalty = soft_penalty_minutes_for_edge(a, b, soft_zones, seg_time_min)
            if soft_penalty > 6.0:
                continue

            best_j = j
            break

        simplified.append(polyline[best_j])
        i = best_j

    return simplified

def build_field_graph(target_time_iso: str):

    cache_key = target_time_iso[:13]  # cache by hour, e.g. 2024-02-05T08

    if cache_key in FIELD_GRAPH_CACHE:
        return FIELD_GRAPH_CACHE[cache_key]

    weather_hard, weather_soft = build_weather_hazard_zones(target_time_iso)
    airspace = AIRSPACE_CACHE
    population_soft = _get_population_zones(target_time_iso)

    hard_zones = list(LEGACY_NO_FLY_ZONES if USE_LEGACY_STATIC_OBSTACLES else []) + weather_hard + airspace
    soft_zones = list(LEGACY_SLOW_ZONES if USE_LEGACY_STATIC_OBSTACLES else []) + weather_soft + population_soft

    field_points = build_field_points(target_time_iso)
    airports = [
        {"id": k, "lat": v["lat"], "lon": v["lon"], "type": "airport"}
        for k, v in NODES.items()
    ]
    all_points = airports + field_points
    point_lookup = {p["id"]: p for p in all_points}

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
            flight_time_min = (dist / EFFECTIVE_AIRSPEED_MPH) * 60.0
            cost = flight_time_min + soft_penalty_minutes_for_edge(a, b, soft_zones, flight_time_min)

            graph[a["id"]].append({
                "from": a["id"],
                "to": b["id"],
                "distance_miles": dist,
                "flight_time_min": flight_time_min,   # 👈 ADD THIS LINE
                "cost": cost,
                "route_class": "field",
                "hazards": [],
            })

            graph[b["id"]].append({
                "from": b["id"],
                "to": a["id"],
                "distance_miles": dist,
                "flight_time_min": flight_time_min,   # 👈 ADD THIS LINE
                "cost": cost,
                "route_class": "field",
                "hazards": [],
            })

    if len(FIELD_GRAPH_CACHE) >= FIELD_GRAPH_CACHE_MAX:
        FIELD_GRAPH_CACHE.pop(next(iter(FIELD_GRAPH_CACHE)))

    FIELD_GRAPH_CACHE[cache_key] = (graph, point_lookup)
    return graph, point_lookup

def compress_path_nodes(path_nodes: List[str]) -> List[str]:
    """
    Keep only meaningful mission nodes for display:
    - always keep first and last
    - keep any real network node in NODES
    - drop intermediate field nodes like F1234
    """
    if not path_nodes:
        return []

    compressed = [path_nodes[0]]

    for node_id in path_nodes[1:-1]:
        if node_id in NODES:
            if compressed[-1] != node_id:
                compressed.append(node_id)

    if compressed[-1] != path_nodes[-1]:
        compressed.append(path_nodes[-1])

    return compressed


def compress_legs_for_display(path_edges: List[dict]) -> List[dict]:
    """
    Merge consecutive field edges into larger display legs.
    Keep detailed polyline separately; this is only for UI readability.
    """
    if not path_edges:
        return []

    merged = []
    current = None

    def node_type(node_id: str) -> str:
        return "network" if node_id in NODES else "field"

    for edge in path_edges:
        edge_from_type = node_type(edge["from"])
        edge_to_type = node_type(edge["to"])

        if current is None:
            current = {
                "from": edge["from"],
                "to": edge["to"],
                "distance_miles": edge["distance_miles"],
                "route_class": edge.get("route_class", "field"),
                "hazards": list(edge.get("hazards", [])),
            }
            continue

        # Merge if we are still traveling through field nodes
        if current["to"] not in NODES and edge["from"] == current["to"]:
            current["to"] = edge["to"]
            current["distance_miles"] += edge["distance_miles"]
            current["hazards"].extend(edge.get("hazards", []))
        else:
            current["distance_miles"] = round(current["distance_miles"], 2)
            merged.append(current)
            current = {
                "from": edge["from"],
                "to": edge["to"],
                "distance_miles": edge["distance_miles"],
                "route_class": edge.get("route_class", "field"),
                "hazards": list(edge.get("hazards", [])),
            }

    if current is not None:
        current["distance_miles"] = round(current["distance_miles"], 2)
        merged.append(current)

    return merged

def _run_field_search(
    graph,
    point_lookup,
    start: str,
    end: str,
    departure_time_iso: str,
    allow_airport_transfers: bool,
) -> Optional[dict]:
    pq = [(0.0, start, [start], [])]
    best: Dict[str, float] = {}

    while pq:
        total_cost, current, path_nodes, path_edges = heapq.heappop(pq)

        if current in best and best[current] <= total_cost:
            continue
        best[current] = total_cost

        if current == end:
            total_distance = sum(e["distance_miles"] for e in path_edges)
            cumulative_minutes = sum(e["flight_time_min"] for e in path_edges)

            display_path = compress_path_nodes(path_nodes)
            display_legs = compress_legs_for_display(path_edges)

            raw_polyline = [
                [point_lookup[node_id]["lat"], point_lookup[node_id]["lon"]]
                for node_id in path_nodes
            ]

            weather_hard, weather_soft = build_weather_hazard_zones(departure_time_iso)
            airspace = AIRSPACE_CACHE
            population_soft = _get_population_zones(departure_time_iso)

            hard_zones = list(LEGACY_NO_FLY_ZONES if USE_LEGACY_STATIC_OBSTACLES else []) + weather_hard + airspace
            # Population zones inform graph cost but NOT polyline simplification —
            # including them there is O(n² × zones) and causes hangs on large grids.
            soft_zones_for_simplify = list(LEGACY_SLOW_ZONES if USE_LEGACY_STATIC_OBSTACLES else []) + weather_soft

            polyline = simplify_polyline_with_hard_and_soft_zones(
                raw_polyline,
                hard_zones,
                soft_zones_for_simplify,
            )

            return {
                "path": display_path,
                "raw_path": path_nodes,
                "polyline": polyline,
                "raw_polyline": raw_polyline,
                "legs": display_legs,
                "raw_legs": path_edges,
                "departure_time": departure_time_iso,
                "arrival_time": add_minutes_iso(departure_time_iso, cumulative_minutes),
                "total_distance_miles": round(total_distance, 2),
                "total_cost": round(total_cost, 2),
                "num_legs": len(display_legs),
                "total_time_minutes": round(cumulative_minutes, 1),
            }

        for edge in graph[current]:
            nxt = edge["to"]
            if nxt in path_nodes:
                continue

            # Do not allow intermediate airport swaps in the first pass
            if nxt in NODES and nxt not in {start, end} and not allow_airport_transfers:
                continue

            extra_cost = edge["cost"]

            if nxt in NODES and nxt not in {start, end}:
                if not allow_airport_transfers:
                    continue
                extra_cost += TRANSFER_TIME_MIN

            turn_penalty = 0.0
            if path_edges:
                prev = path_edges[-1]

                a1 = point_lookup[prev["from"]]
                a2 = point_lookup[prev["to"]]
                b2 = point_lookup[edge["to"]]

                v1x = a2["lon"] - a1["lon"]
                v1y = a2["lat"] - a1["lat"]
                v2x = b2["lon"] - a2["lon"]
                v2y = b2["lat"] - a2["lat"]

                mag1 = math.hypot(v1x, v1y)
                mag2 = math.hypot(v2x, v2y)

                if mag1 > 0 and mag2 > 0:
                    cos_theta = (v1x * v2x + v1y * v2y) / (mag1 * mag2)
                    cos_theta = max(-1.0, min(1.0, cos_theta))
                    angle_deg = math.degrees(math.acos(cos_theta))

                    if angle_deg > 45:
                        turn_penalty = 0.05
                    if angle_deg > 90:
                        turn_penalty = 0.15

            heapq.heappush(
                pq,
                (
                    total_cost + extra_cost + turn_penalty,
                    nxt,
                    path_nodes + [nxt],
                    path_edges + [edge],
                )
            )
    return None

def shortest_path_field(start: str, end: str, departure_time_iso: Optional[str] = None) -> Optional[dict]:
    if departure_time_iso is None:
        departure_time_iso = datetime.now().replace(second=0, microsecond=0).isoformat(timespec="minutes")

    graph, point_lookup = build_field_graph(departure_time_iso)
    if start not in graph or end not in graph:
        return None

    # First try: no intermediate airport transfers
    result = _run_field_search(
        graph, point_lookup, start, end, departure_time_iso,
        allow_airport_transfers=False
    )
    if result is not None:
        return result

    # Fallback: allow transfers if direct field routing fails
    return _run_field_search(
        graph, point_lookup, start, end, departure_time_iso,
        allow_airport_transfers=True
    )