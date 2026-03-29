from __future__ import annotations

import math
import heapq
from typing import Dict, List, Optional, Tuple

# -------------------------------------------------
# Finalized real-world nodes
# -------------------------------------------------
NODES: Dict[str, dict] = {
    "UCB": {"name": "UC Berkeley", "lat": 37.875158, "lon": -122.261472, "type": "uc"},
    "UCD": {"name": "UC Davis", "lat": 38.539703, "lon": -121.758061, "type": "uc"},
    "UCSC": {"name": "UC Santa Cruz", "lat": 36.999100, "lon": -122.063486, "type": "uc"},
    "UCM": {"name": "UC Merced", "lat": 37.369886, "lon": -120.415594, "type": "uc"},
    "KSQL": {"name": "San Carlos Airport", "lat": 37.512517, "lon": -122.248736, "type": "airport"},
    "KNUQ": {"name": "Moffett Federal Airfield", "lat": 37.407217, "lon": -122.048822, "type": "airport"},
    "KLVK": {"name": "Livermore Municipal Airport", "lat": 37.694697, "lon": -121.829808, "type": "airport"},
    "KCVH": {"name": "Hollister Municipal Airport", "lat": 36.891033, "lon": -121.403344, "type": "airport"},
    "KSNS": {"name": "Salinas Municipal Airport", "lat": 36.665964, "lon": -121.610133, "type": "airport"},
    "KOAR": {"name": "Marina Municipal Airport", "lat": 36.677764, "lon": -121.758731, "type": "airport"},
}

# -------------------------------------------------
# Routing assumptions
# -------------------------------------------------
MAX_LEG_MILES = 80.0

# You can tune these later
RISK_WEIGHTS = {
    "green": 1.00,
    "yellow": 1.20,
    "orange": 1.50,
}

# -------------------------------------------------
# Manual edge classes for now
# Later these can come from terrain/weather/airspace
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
    """
    Great-circle distance in miles.
    """
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
# Graph construction
# -------------------------------------------------
def build_graph() -> Dict[str, List[dict]]:
    graph: Dict[str, List[dict]] = {node_id: [] for node_id in NODES}

    node_ids = list(NODES.keys())
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            a = node_ids[i]
            b = node_ids[j]

            rclass = route_class(a, b)
            if rclass is None:
                continue

            dist = distance_between(NODES[a], NODES[b])
            if dist > MAX_LEG_MILES:
                continue

            cost = dist * RISK_WEIGHTS[rclass]

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

GRAPH = build_graph()

# -------------------------------------------------
# Shortest path
# -------------------------------------------------
def shortest_path(start: str, end: str) -> Optional[dict]:
    if start not in GRAPH or end not in GRAPH:
        return None

    pq: List[Tuple[float, str, List[str]]] = [(0.0, start, [])]
    visited = set()

    while pq:
        total_cost, current, path = heapq.heappop(pq)

        if current in visited:
            continue
        visited.add(current)

        path = path + [current]

        if current == end:
            legs = []
            total_distance = 0.0

            for i in range(len(path) - 1):
                a = path[i]
                b = path[i + 1]
                edge = next(e for e in GRAPH[a] if e["to"] == b)
                legs.append({
                    "from": a,
                    "to": b,
                    "distance_miles": round(edge["distance_miles"], 2),
                    "route_class": edge["route_class"],
                })
                total_distance += edge["distance_miles"]

            return {
                "path": path,
                "legs": legs,
                "total_distance_miles": round(total_distance, 2),
                "total_cost": round(total_cost, 2),
            }

        for edge in GRAPH[current]:
            neighbor = edge["to"]
            if neighbor not in visited:
                heapq.heappush(pq, (total_cost + edge["cost"], neighbor, path))

    return None

if __name__ == "__main__":
    print("Feasible graph:")
    for node_id, edges in GRAPH.items():
        print(f"\n{node_id}:")
        for e in edges:
            print(f"  -> {e['to']}: {e['distance_miles']:.2f} mi, {e['route_class']}")

    print("\nExample route UCD -> UCM")
    result = shortest_path("UCD", "UCM")
    print(result)