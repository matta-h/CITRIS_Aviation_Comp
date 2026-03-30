from __future__ import annotations

import requests
import math
import heapq
from backend.weather import fetch_weather_for_nodes, weather_penalty
from typing import Dict, List, Optional, Tuple

# -------------------------------------------------
# Finalized real-world nodes
# capacity = simultaneous operating pads for now
# parking = optional future storage count
# -------------------------------------------------
NODES: Dict[str, dict] = {
    "UCB": {
        "name": "UC Berkeley",
        "lat": 37.875158,
        "lon": -122.261472,
        "type": "uc",
        "capacity": 1,
        "parking": 1,
    },
    "UCD": {
        "name": "UC Davis",
        "lat": 38.539703,
        "lon": -121.758061,
        "type": "uc",
        "capacity": 1,
        "parking": 1,
    },
    "UCSC": {
        "name": "UC Santa Cruz",
        "lat": 36.999100,
        "lon": -122.063486,
        "type": "uc",
        "capacity": 1,
        "parking": 1,
    },
    "UCM": {
        "name": "UC Merced",
        "lat": 37.369886,
        "lon": -120.415594,
        "type": "uc",
        "capacity": 1,
        "parking": 1,
    },
    "KSQL": {
        "name": "San Carlos Airport",
        "lat": 37.512517,
        "lon": -122.248736,
        "type": "airport",
        "capacity": 2,
        "parking": 4,
    },
    "KNUQ": {
        "name": "Moffett Federal Airfield",
        "lat": 37.407217,
        "lon": -122.048822,
        "type": "airport",
        "capacity": 3,
        "parking": 6,
    },
    "KLVK": {
        "name": "Livermore Municipal Airport",
        "lat": 37.694697,
        "lon": -121.829808,
        "type": "airport",
        "capacity": 4,
        "parking": 8,
    },
    "KCVH": {
        "name": "Hollister Municipal Airport",
        "lat": 36.891033,
        "lon": -121.403344,
        "type": "airport",
        "capacity": 3,
        "parking": 6,
    },
    "KSNS": {
        "name": "Salinas Municipal Airport",
        "lat": 36.665964,
        "lon": -121.610133,
        "type": "airport",
        "capacity": 3,
        "parking": 6,
    },
    "KOAR": {
        "name": "Marina Municipal Airport",
        "lat": 36.677764,
        "lon": -121.758731,
        "type": "airport",
        "capacity": 2,
        "parking": 4,
    },
}

# -------------------------------------------------
# Routing assumptions
# -------------------------------------------------
SHORT_HOP_THRESHOLD = 15.0
SHORT_HOP_PENALTY = 4.0

MAX_LEG_MILES = 85.0

RISK_WEIGHTS = {
    "green": 1.00,
    "yellow": 1.10,
    "orange": 1.20,
}

# Penalize each connection so fewer-stop routes are preferred
STOP_PENALTY = 20

# -------------------------------------------------
# Static obstacle zones
# radius in miles
# -------------------------------------------------
NO_FLY_ZONES = [
    {
        "name": "SF Bay Core Avoidance",
        "lat": 37.68,
        "lon": -122.22,
        "radius_miles": 10.0,
    },
    {
        "name": "Monterey Bay Avoidance",
        "lat": 36.92,
        "lon": -121.95,
        "radius_miles": 8.0,
    },
]

SLOW_ZONES = [
    {
        "name": "Diablo Corridor Caution",
        "lat": 37.55,
        "lon": -121.85,
        "radius_miles": 12.0,
        "penalty": 18.0,
    },
    {
        "name": "South Bay Caution",
        "lat": 37.35,
        "lon": -121.95,
        "radius_miles": 10.0,
        "penalty": 12.0,
    },
]

def to_local_miles(lat: float, lon: float, ref_lat: float) -> Tuple[float, float]:
    """
    Convert lat/lon to approximate local Cartesian miles.
    Good enough for regional obstacle checks.
    """
    miles_per_deg_lat = 69.0
    miles_per_deg_lon = 69.0 * math.cos(math.radians(ref_lat))
    x = lon * miles_per_deg_lon
    y = lat * miles_per_deg_lat
    return x, y


def point_to_segment_distance_miles(
    px: float, py: float,
    x1: float, y1: float,
    x2: float, y2: float
) -> float:
    dx = x2 - x1
    dy = y2 - y1

    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)

    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))

    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    return math.hypot(px - closest_x, py - closest_y)


def edge_intersects_circle(node_a: dict, node_b: dict, zone: dict) -> bool:
    ref_lat = (node_a["lat"] + node_b["lat"] + zone["lat"]) / 3.0

    x1, y1 = to_local_miles(node_a["lat"], node_a["lon"], ref_lat)
    x2, y2 = to_local_miles(node_b["lat"], node_b["lon"], ref_lat)
    px, py = to_local_miles(zone["lat"], zone["lon"], ref_lat)

    d = point_to_segment_distance_miles(px, py, x1, y1, x2, y2)
    return d <= zone["radius_miles"]


def no_fly_hit(node_a: dict, node_b: dict) -> Optional[dict]:
    for zone in NO_FLY_ZONES:
        if edge_intersects_circle(node_a, node_b, zone):
            return zone
    return None


def slow_zone_penalty(node_a: dict, node_b: dict) -> float:
    total = 0.0
    for zone in SLOW_ZONES:
        if edge_intersects_circle(node_a, node_b, zone):
            total += zone["penalty"]
    return total

# -------------------------------------------------
# Manual edge classes for now
# -------------------------------------------------
GREEN_EDGES = {
    tuple(sorted(("UCSC", "KOAR"))),
    tuple(sorted(("UCSC", "KSNS"))),
    tuple(sorted(("UCSC", "KCVH"))),
    tuple(sorted(("KOAR", "KSNS"))),
    tuple(sorted(("KOAR", "KCVH"))),
    tuple(sorted(("KSNS", "KCVH"))),
}

YELLOW_EDGES = {
    tuple(sorted(("UCB", "UCD"))),
    tuple(sorted(("UCB", "KLVK"))),
    tuple(sorted(("UCD", "KLVK"))),
    tuple(sorted(("KLVK", "UCM"))),
    tuple(sorted(("KLVK", "KCVH"))),
    tuple(sorted(("KCVH", "UCM"))),
    tuple(sorted(("UCB", "KSQL"))),
    tuple(sorted(("KLVK", "KNUQ"))),
    tuple(sorted(("KSQL", "KNUQ"))),
}

ORANGE_EDGES = {
    tuple(sorted(("UCB", "KNUQ"))),
    tuple(sorted(("KSQL", "UCSC"))),
    tuple(sorted(("KNUQ", "UCSC"))),
    tuple(sorted(("KNUQ", "KCVH"))),
    tuple(sorted(("KSQL", "KLVK"))),
}

def edge_key(a: str, b: str) -> Tuple[str, str]:
    return tuple(sorted((a, b)))

def route_class(a: str, b: str) -> Optional[str]:
    key = edge_key(a, b)
    if key in GREEN_EDGES:
        return "green"
    if key in YELLOW_EDGES:
        return "yellow"
    if key in ORANGE_EDGES:
        return "orange"
    return None

# -------------------------------------------------
# Real geographic distance
# -------------------------------------------------
def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_miles = 3958.7613

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_miles * c

def distance_between(node_a: dict, node_b: dict) -> float:
    return haversine_miles(node_a["lat"], node_a["lon"], node_b["lat"], node_b["lon"])

# -------------------------------------------------
# Detour routing
# -------------------------------------------------
def generate_detour_nodes(a: dict, b: dict, zone: dict):
    """
    Create 2 detour point pairs around a circular obstacle.
    Uses local-mile coordinates, then converts back to lat/lon.
    """

    ref_lat = (a["lat"] + b["lat"] + zone["lat"]) / 3.0

    ax, ay = to_local_miles(a["lat"], a["lon"], ref_lat)
    bx, by = to_local_miles(b["lat"], b["lon"], ref_lat)
    cx, cy = to_local_miles(zone["lat"], zone["lon"], ref_lat)

    r = zone["radius_miles"]
    offset = 0.45  # radians
    detours = []

    angle_a = math.atan2(ay - cy, ax - cx)
    angle_b = math.atan2(by - cy, bx - cx)

    miles_per_deg_lat = 69.0
    miles_per_deg_lon = 69.0 * math.cos(math.radians(ref_lat))

    def local_to_latlon(x: float, y: float) -> dict:
        return {
            "lat": y / miles_per_deg_lat,
            "lon": x / miles_per_deg_lon,
        }

    for direction in [1, -1]:
        theta1 = angle_a + direction * offset
        theta2 = angle_b - direction * offset

        p1x = cx + (r * 1.2) * math.cos(theta1)
        p1y = cy + (r * 1.2) * math.sin(theta1)

        p2x = cx + (r * 1.2) * math.cos(theta2)
        p2y = cy + (r * 1.2) * math.sin(theta2)

        p1 = local_to_latlon(p1x, p1y)
        p2 = local_to_latlon(p2x, p2y)

        detours.append((p1, p2))

    return detours

# -------------------------------------------------
# Graph construction
# -------------------------------------------------
def classify_edge(a: str, b: str, dist: float) -> str:
    """
    Temporary classification until obstacle/weather layers are added.
    For now, direct edges are allowed if within range.
    """
    # You can refine this later with terrain/water/airspace checks.
    if dist <= 40:
        return "green"
    if dist <= 65:
        return "yellow"
    return "orange"


def build_graph() -> Dict[str, List[dict]]:
    graph: Dict[str, List[dict]] = {node_id: [] for node_id in NODES}

    weather_data = fetch_weather_for_nodes(NODES)

    node_ids = list(NODES.keys())
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            a = node_ids[i]
            b = node_ids[j]

            dist = distance_between(NODES[a], NODES[b])

            if dist > MAX_LEG_MILES:
                continue

            rclass = classify_edge(a, b, dist)
            hit_zone = no_fly_hit(NODES[a], NODES[b])

            if hit_zone is not None:
                detour_paths = generate_detour_nodes(NODES[a], NODES[b], hit_zone)

                for p1, p2 in detour_paths:
                    d1 = distance_between(NODES[a], p1)
                    d2 = distance_between(p1, p2)
                    d3 = distance_between(p2, NODES[b])

                    total_dist = d1 + d2 + d3

                    if total_dist > MAX_LEG_MILES * 1.5:
                        continue

                    wx_a = weather_data.get(a, {})
                    wx_b = weather_data.get(b, {})

                    penalty_a = weather_penalty(wx_a)
                    penalty_b = weather_penalty(wx_b)

                    if penalty_a == float("inf") or penalty_b == float("inf"):
                        continue

                    weather_cost = penalty_a + penalty_b
                    cost = total_dist * 1.3 + weather_cost

                    graph[a].append({
                        "to": b,
                        "distance_miles": total_dist,
                        "route_class": "detour",
                        "cost": cost,
                        "via": [p1, p2],
                    })

                    graph[b].append({
                        "to": a,
                        "distance_miles": total_dist,
                        "route_class": "detour",
                        "cost": cost,
                        "via": [p2, p1],
                    })

                continue

            short_hop_penalty = SHORT_HOP_PENALTY if dist < SHORT_HOP_THRESHOLD else 0.0
            obstacle_penalty = slow_zone_penalty(NODES[a], NODES[b])

            wx_a = weather_data.get(a, {})
            wx_b = weather_data.get(b, {})

            penalty_a = weather_penalty(wx_a)
            penalty_b = weather_penalty(wx_b)

            if penalty_a == float("inf") or penalty_b == float("inf"):
                continue

            weather_cost = penalty_a + penalty_b

            cost = (
                dist * RISK_WEIGHTS[rclass]
                + short_hop_penalty
                + obstacle_penalty
                + weather_cost
            )

            graph[a].append({
                "to": b,
                "distance_miles": dist,
                "route_class": rclass,
                "cost": cost,
            })
            graph[b].append({
                "to": a,
                "distance_miles": dist,
                "route_class": rclass,
                "cost": cost,
            })

    return graph

# -------------------------------------------------
# Shortest path
# -------------------------------------------------
def shortest_path(start: str, end: str) -> Optional[dict]:
    graph = build_graph()

    if start not in graph or end not in graph:
        return None

    pq: List[Tuple[float, str, List[str]]] = [(0.0, start, [])]
    best_cost = {}

    while pq:
        total_cost, current, path = heapq.heappop(pq)

        if current in best_cost and best_cost[current] <= total_cost:
            continue
        best_cost[current] = total_cost

        path = path + [current]

        if current == end:
            legs = []
            total_distance = 0.0

            for i in range(len(path) - 1):
                a = path[i]
                b = path[i + 1]
                edge = next(e for e in graph[a] if e["to"] == b)

                leg = {
                    "from": a,
                    "to": b,
                    "distance_miles": round(edge["distance_miles"], 2),
                    "route_class": edge["route_class"],
                }

                if "via" in edge:
                    leg["via"] = edge["via"]

                legs.append(leg)
                total_distance += edge["distance_miles"]

            return {
                "path": path,
                "legs": legs,
                "total_distance_miles": round(total_distance, 2),
                "total_cost": round(total_cost, 2),
                "num_legs": len(path) - 1,
            }

        for edge in graph[current]:
            neighbor = edge["to"]
            extra_cost = edge["cost"]

            if current != start:
                extra_cost += STOP_PENALTY

            heapq.heappush(pq, (total_cost + extra_cost, neighbor, path))

    return None

if __name__ == "__main__":
    graph = build_graph()
    print("Feasible graph:")
    print(f"MAX_LEG_MILES = {MAX_LEG_MILES}")
    print(f"STOP_PENALTY = {STOP_PENALTY}")

    for node_id, edges in graph.items():
        print(f"\n{node_id}:")
        for e in edges:
            print(
                f"  -> {e['to']}: "
                f"{e['distance_miles']:.2f} mi, "
                f"{e['route_class']}, "
                f"cost={e['cost']:.2f}"
            )

    print("\nExample route UCB -> UCD")
    print(shortest_path("UCB", "UCD"))