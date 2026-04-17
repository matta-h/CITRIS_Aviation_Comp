from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

from backend.routing_single import NODES
from backend.population_adapter import get_population_grid

MIN_DISTANCE_MILES = 10.0

# Hourly volume multipliers from CITRIS_SIM_INSTRUCTIONS
HOURLY_MULTIPLIERS: Dict[int, float] = {
    6: 0.4,  7: 1.0,  8: 1.8,  9: 1.6,
    10: 1.0, 11: 0.9, 12: 1.1, 13: 0.9,
    14: 0.8, 15: 0.9, 16: 1.4, 17: 1.8,
    18: 1.5, 19: 0.8, 20: 0.4, 21: 0.2,
}

# Fallback for nodes with no nearby LandScan data
DEFAULT_POP_WEIGHT = 0.3

# Max lat/lon distance (~35 miles) for nearest-grid-point lookup
MAX_GRID_SEARCH_DEG = 0.5

# Cache: (node_id, "day"|"night") -> ambient population count
_pop_cache: Dict[Tuple[str, str], float] = {}


def _distance_miles(a: dict, b: dict) -> float:
    ref_lat = (a["lat"] + b["lat"]) / 2.0
    dx = (b["lon"] - a["lon"]) * 69.0 * math.cos(math.radians(ref_lat))
    dy = (b["lat"] - a["lat"]) * 69.0
    return math.hypot(dx, dy)


def _node_pop(node_id: str, time_of_day: str) -> float:
    """
    Return ambient population count at this node from the nearest LandScan
    grid point. Cached after first call. Falls back to DEFAULT_POP_WEIGHT
    if no grid point is within MAX_GRID_SEARCH_DEG.
    """
    key = (node_id, time_of_day)
    if key in _pop_cache:
        return _pop_cache[key]

    node = NODES.get(node_id)
    if node is None:
        _pop_cache[key] = DEFAULT_POP_WEIGHT
        return DEFAULT_POP_WEIGHT

    grid = get_population_grid(time_of_day)
    best_dist = float("inf")
    best_pop: Optional[float] = None

    for pt in grid:
        d = math.hypot(pt["lat"] - node["lat"], pt["lon"] - node["lon"])
        if d < best_dist:
            best_dist = d
            best_pop = float(pt["population"])

    if best_pop is None or best_dist > MAX_GRID_SEARCH_DEG:
        weight = DEFAULT_POP_WEIGHT
    else:
        weight = best_pop

    _pop_cache[key] = weight
    return weight


def get_demand_for_timeslot(
    origin: str,
    dest: str,
    hour: int,
    demand_scale: float = 1.0,
) -> float:
    """
    Returns expected passengers generated for origin->dest in one 15-minute
    time slot. Directional: A->B != B->A.

    Uses a gravity model with LandScan day/night population weights and
    time-of-day directional asymmetry to produce a commuter reversal pattern.
    """
    if origin not in NODES or dest not in NODES:
        return 0.0

    dist = _distance_miles(NODES[origin], NODES[dest])
    if dist < MIN_DISTANCE_MILES:
        return 0.0

    tod = "day" if 8 <= hour < 19 else "night"
    pop_origin = _node_pop(origin, tod)
    pop_dest = _node_pop(dest, tod)

    # Gravity model base (per hour)
    base = demand_scale * math.sqrt(pop_origin * pop_dest) / dist

    # Directional asymmetry by time period
    if 6 <= hour <= 9:
        # Morning: boost FROM high-residential origins toward work destinations
        night_pop = _node_pop(origin, "night")
        day_pop = _node_pop(origin, "day")
        direction_mult = night_pop / (day_pop + 0.01)
    elif 16 <= hour <= 20:
        # Evening: boost FROM high-daytime nodes going home
        day_pop = _node_pop(origin, "day")
        night_pop = _node_pop(origin, "night")
        direction_mult = day_pop / (night_pop + 0.01)
    else:
        direction_mult = 1.0

    # Convert hourly to 15-minute slot
    hourly_mult = HOURLY_MULTIPLIERS.get(hour, 0.2)
    return base * direction_mult * (hourly_mult / 4.0)
