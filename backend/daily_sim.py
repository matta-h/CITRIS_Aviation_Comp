from __future__ import annotations

import math
import time
import requests
from math import ceil, floor
from typing import Dict, List, Optional, Tuple

from backend.routing_single import NODES
from backend.demand_model import get_demand_for_timeslot

# ── Cost model constants (CITRIS Economic Assessment Model v4) ────────────────

PILOT_HOURLY_RATE_USD = 199.34
# Derived: $122,670/yr * 1.3 burden / 800 flight-hours/yr

ELECTRICITY_PRICE_USD_KWH = 0.2313
# Source: EIA January 2026 California commercial average

ENERGY_KWH_PER_FLIGHT_REFERENCE = 90.0
REFERENCE_DISTANCE_MILES = 28.0
# Source: Excel model, ~100-120 kWh battery with partial charging per avg leg

MAINTENANCE_COST_PER_FLIGHT_USD = 30.34
# Derived: $151,708.50 NASA residual / 5000 annual ops

UC_INFRASTRUCTURE_COST_PER_FLIGHT_USD = 43.29
# Derived: $216,467.60 annual infra OPEX / 5000 annual ops

AIRPORT_INFRASTRUCTURE_COST_PER_FLIGHT_USD = 65.00
# PLACEHOLDER — airports have larger staffing and higher landing fees.
# Needs refinement with actual airport operating cost data.

UC_NODES = {"UCB", "UCSC", "UCD", "UCM"}
AIRPORT_NODES = {"KSQL", "KNUQ", "KLVK", "KCVH", "KSNS", "KOAR"}

ROUTE_BASE = "http://127.0.0.1:8000"


# ── Aircraft state ────────────────────────────────────────────────────────────

class Aircraft:
    def __init__(self, aircraft_id: str, home_port: str) -> None:
        self.id = aircraft_id
        self.home_port = home_port
        self.current_port = home_port
        self.available_at_minute = 360   # 6:00am
        self.total_flight_minutes = 0.0
        self.total_flights = 0
        self.total_distance_miles = 0.0


def _build_fleet() -> List[Aircraft]:
    fleet: List[Aircraft] = []
    for node_id in NODES:
        if node_id in UC_NODES:
            count = 2
        elif node_id in AIRPORT_NODES:
            count = 3
        else:
            continue
        for i in range(1, count + 1):
            fleet.append(Aircraft(f"{node_id}-{i}", node_id))
    return fleet


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minute_to_iso(date: str, minute: int) -> str:
    h = minute // 60
    m = minute % 60
    return f"{date}T{h:02d}:{m:02d}"


def _compute_costs(
    origin: str,
    total_time_minutes: float,
    total_distance_miles: float,
    ticket_price: float,
    passengers: int,
) -> dict:
    cost_pilot = (total_time_minutes / 60.0) * PILOT_HOURLY_RATE_USD

    energy_kwh = ENERGY_KWH_PER_FLIGHT_REFERENCE * (total_distance_miles / REFERENCE_DISTANCE_MILES)
    energy_kwh = max(20.0, min(energy_kwh, 180.0))
    cost_energy = energy_kwh * ELECTRICITY_PRICE_USD_KWH

    cost_maintenance = MAINTENANCE_COST_PER_FLIGHT_USD

    if origin in UC_NODES:
        cost_infra = UC_INFRASTRUCTURE_COST_PER_FLIGHT_USD
    else:
        cost_infra = AIRPORT_INFRASTRUCTURE_COST_PER_FLIGHT_USD

    cost_total = cost_pilot + cost_energy + cost_maintenance + cost_infra
    revenue = passengers * ticket_price
    profit = revenue - cost_total

    return {
        "revenue": round(revenue, 2),
        "cost_pilot": round(cost_pilot, 2),
        "cost_energy": round(cost_energy, 2),
        "cost_maintenance": round(cost_maintenance, 2),
        "cost_infrastructure": round(cost_infra, 2),
        "cost_total": round(cost_total, 2),
        "profit": round(profit, 2),
    }


# ── Main simulation ───────────────────────────────────────────────────────────

def run_daily_simulation(
    date: str,
    ticket_price: float = 100.0,
    demand_scale: float = 1.0,
    start_hour: int = 6,
    end_hour: int = 22,
) -> dict:
    sim_start_wall = time.time()

    fleet = _build_fleet()
    node_ids = list(NODES.keys())

    # Accumulated demand for every directed pair
    demand_acc: Dict[Tuple[str, str], float] = {
        (a, b): 0.0
        for a in node_ids
        for b in node_ids
        if a != b
    }

    flight_log: List[dict] = []
    cancelled_by_origin: Dict[str, int] = {n: 0 for n in node_ids}
    flight_id_counter = 0

    # Per-hour weather cache: hour_key ("2024-02-15T08") -> full weather dict
    weather_hour_cache: Dict[str, dict] = {}

    def _weather_status(node_id: str, iso_time: str) -> str:
        hour_key = iso_time[:13]
        if hour_key not in weather_hour_cache:
            try:
                resp = requests.get(
                    f"{ROUTE_BASE}/weather",
                    params={"target_time": iso_time},
                    timeout=5,
                )
                weather_hour_cache[hour_key] = resp.json() if resp.ok else {}
            except Exception:
                weather_hour_cache[hour_key] = {}
        node_data = weather_hour_cache.get(hour_key, {}).get(node_id, {})
        return node_data.get("status", "unknown")

    start_minute = start_hour * 60
    end_minute = end_hour * 60

    # ── 15-minute time steps ──────────────────────────────────────────────────
    for current_minute in range(start_minute, end_minute, 15):
        hour = current_minute // 60
        current_iso = _minute_to_iso(date, current_minute)

        # Step 1: accumulate demand for all pairs
        for (origin, dest) in demand_acc:
            demand_acc[(origin, dest)] += get_demand_for_timeslot(
                origin, dest, hour, demand_scale
            )

        # Step 2: dispatch loop — process each origin, sorted by demand descending
        dispatched_this_step: set = set()

        for origin in node_ids:
            eligible = [
                (dest, demand_acc[(origin, dest)])
                for dest in node_ids
                if dest != origin and demand_acc[(origin, dest)] >= 1.0
            ]
            if not eligible:
                continue

            eligible.sort(key=lambda x: x[1], reverse=True)

            for dest, acc_demand in eligible:
                # Find available aircraft at this origin not yet used this step
                candidates = [
                    a for a in fleet
                    if a.current_port == origin
                    and a.available_at_minute <= current_minute
                    and a.id not in dispatched_this_step
                ]
                if not candidates:
                    break

                aircraft = min(candidates, key=lambda a: a.available_at_minute)

                # Call /route
                try:
                    resp = requests.get(
                        f"{ROUTE_BASE}/route",
                        params={
                            "start": origin,
                            "end": dest,
                            "departure_time": current_iso,
                        },
                        timeout=30,
                    )
                except Exception as exc:
                    print(f"[SIM] {current_iso[11:16]} {origin}->{dest} network error: {exc}")
                    cancelled_by_origin[origin] += 1
                    demand_acc[(origin, dest)] = 0.0
                    continue

                if resp.status_code == 404:
                    print(f"[SIM] {current_iso[11:16]} {origin}->{dest} cancelled (no feasible route)")
                    cancelled_by_origin[origin] += 1
                    demand_acc[(origin, dest)] = 0.0
                    continue

                if not resp.ok:
                    print(f"[SIM] {current_iso[11:16]} {origin}->{dest} error {resp.status_code}")
                    cancelled_by_origin[origin] += 1
                    demand_acc[(origin, dest)] = 0.0
                    continue

                route = resp.json()
                total_time_min = float(route.get("total_time_minutes", 0.0))
                total_dist_mi = float(route.get("total_distance_miles", 0.0))
                exchange_required = bool(route.get("exchange_required", False))
                exchange_stops = route.get("exchange_stops") or []
                exchange_stop = exchange_stops[0] if exchange_stops else None
                route_class = route.get("route_class", "unknown")

                passengers = max(1, min(4, int(floor(acc_demand))))
                turnaround = 20 + (15 if total_dist_mi > 60 else 0)

                aircraft.available_at_minute = current_minute + ceil(total_time_min) + turnaround
                aircraft.current_port = dest
                aircraft.total_flight_minutes += total_time_min
                aircraft.total_flights += 1
                aircraft.total_distance_miles += total_dist_mi

                demand_acc[(origin, dest)] = max(0.0, demand_acc[(origin, dest)] - passengers)
                dispatched_this_step.add(aircraft.id)

                arrival_iso = _minute_to_iso(date, current_minute + ceil(total_time_min))
                wx_status = _weather_status(origin, current_iso)
                financials = _compute_costs(origin, total_time_min, total_dist_mi, ticket_price, passengers)

                flight_id_counter += 1
                record = {
                    "flight_id": flight_id_counter,
                    "origin": origin,
                    "destination": dest,
                    "departure_time_iso": current_iso,
                    "arrival_time_iso": arrival_iso,
                    "total_time_minutes": round(total_time_min, 2),
                    "total_distance_miles": round(total_dist_mi, 2),
                    "passengers": passengers,
                    "route_class": route_class,
                    "was_exchange": exchange_required,
                    "exchange_stop": exchange_stop,
                    "weather_status_origin": wx_status,
                    "aircraft_id": aircraft.id,
                    # Fields needed for frontend animation
                    "route_snapshot": {
                        "polyline": route.get("polyline"),
                        "legs": route.get("legs"),
                        "total_time_minutes": round(total_time_min, 2),
                        "total_distance_miles": round(total_dist_mi, 2),
                        "route_class": route_class,
                        "exchange_required": exchange_required,
                        "exchange_stops": exchange_stops,
                        "selection_notes": route.get("selection_notes") or {},
                    },
                    **financials,
                }
                flight_log.append(record)

                print(
                    f"[SIM] {current_iso[11:16]} {origin}->{dest} dispatched  "
                    f"{passengers} pax  {total_dist_mi:.1f} mi  {total_time_min:.0f} min  "
                    f"profit ${financials['profit']:.2f}"
                )

    # ── Summaries ─────────────────────────────────────────────────────────────
    site_summaries = _build_site_summaries(
        flight_log, fleet, cancelled_by_origin, start_hour, end_hour
    )
    network_summary = _build_network_summary(
        flight_log, site_summaries, cancelled_by_origin
    )

    return {
        "date": date,
        "parameters": {"ticket_price": ticket_price, "demand_scale": demand_scale},
        "flight_log": flight_log,
        "site_summaries": site_summaries,
        "network_summary": network_summary,
        "simulation_duration_seconds": round(time.time() - sim_start_wall, 2),
    }


# ── Site summaries ────────────────────────────────────────────────────────────

def _build_site_summaries(
    flight_log: List[dict],
    fleet: List[Aircraft],
    cancelled_by_origin: Dict[str, int],
    start_hour: int,
    end_hour: int,
) -> dict:
    operating_minutes = (end_hour - start_hour) * 60
    summaries = {}

    for node_id in NODES:
        departures = [f for f in flight_log if f["origin"] == node_id]
        arrivals = [f for f in flight_log if f["destination"] == node_id]
        site_aircraft = [a for a in fleet if a.home_port == node_id]
        n_aircraft = len(site_aircraft)

        total_flight_min = sum(a.total_flight_minutes for a in site_aircraft)
        utilization = (
            total_flight_min / (n_aircraft * operating_minutes)
            if n_aircraft > 0 and operating_minutes > 0 else 0.0
        )

        # Top routes from this origin
        route_stats: Dict[str, Dict] = {}
        for f in departures:
            d = f["destination"]
            if d not in route_stats:
                route_stats[d] = {"flight_count": 0, "total_pax": 0}
            route_stats[d]["flight_count"] += 1
            route_stats[d]["total_pax"] += f["passengers"]

        top_routes = sorted(
            [
                {
                    "destination": d,
                    "flight_count": v["flight_count"],
                    "avg_pax": round(v["total_pax"] / v["flight_count"], 2),
                }
                for d, v in route_stats.items()
            ],
            key=lambda x: x["flight_count"],
            reverse=True,
        )

        avg_pax = (
            sum(f["passengers"] for f in departures) / len(departures)
            if departures else 0.0
        )
        gross_revenue = sum(f["revenue"] for f in departures)
        total_cost = sum(f["cost_total"] for f in departures)

        summaries[node_id] = {
            "total_departures": len(departures),
            "total_arrivals": len(arrivals),
            "total_passengers_departed": sum(f["passengers"] for f in departures),
            "total_passengers_arrived": sum(f["passengers"] for f in arrivals),
            "gross_revenue": round(gross_revenue, 2),
            "total_pilot_cost": round(sum(f["cost_pilot"] for f in departures), 2),
            "total_energy_cost": round(sum(f["cost_energy"] for f in departures), 2),
            "total_maintenance_cost": round(sum(f["cost_maintenance"] for f in departures), 2),
            "total_infrastructure_cost": round(sum(f["cost_infrastructure"] for f in departures), 2),
            "total_cost": round(total_cost, 2),
            "net_profit": round(gross_revenue - total_cost, 2),
            "avg_load_factor": round(avg_pax / 4.0, 3),
            "fleet_utilization": round(utilization, 4),
            "cancelled_flights": cancelled_by_origin.get(node_id, 0),
            "top_routes": top_routes,
            "aircraft_positions_at_eod": [
                {
                    "aircraft_id": a.id,
                    "current_port": a.current_port,
                    "is_away_from_home": a.current_port != a.home_port,
                }
                for a in site_aircraft
            ],
        }

    return summaries


# ── Network summary ───────────────────────────────────────────────────────────

def _build_network_summary(
    flight_log: List[dict],
    site_summaries: dict,
    cancelled_by_origin: Dict[str, int],
) -> dict:
    total_flights = len(flight_log)
    total_pax = sum(f["passengers"] for f in flight_log)
    total_revenue = sum(f["revenue"] for f in flight_log)
    total_cost = sum(f["cost_total"] for f in flight_log)
    total_profit = total_revenue - total_cost
    total_cancelled = sum(cancelled_by_origin.values())

    profitable = [p for p, s in site_summaries.items() if s["net_profit"] > 0]
    unprofitable = [p for p, s in site_summaries.items() if s["net_profit"] <= 0]
    break_even = (total_cost / total_pax) if total_pax > 0 else None

    # Busiest route
    route_counts: Dict[Tuple[str, str], int] = {}
    for f in flight_log:
        key = (f["origin"], f["destination"])
        route_counts[key] = route_counts.get(key, 0) + 1
    busiest = None
    if route_counts:
        best = max(route_counts, key=lambda k: route_counts[k])
        busiest = {
            "origin": best[0],
            "destination": best[1],
            "flight_count": route_counts[best],
        }

    # Demand pattern
    def _hour(f: dict) -> int:
        return int(f["departure_time_iso"][11:13])

    morning_flights = sum(1 for f in flight_log if 6 <= _hour(f) < 10)
    midday_flights = sum(1 for f in flight_log if 10 <= _hour(f) < 16)
    evening_flights = sum(1 for f in flight_log if 16 <= _hour(f) < 22)

    # Plain-language narrative
    narrative = _build_narrative(
        total_flights, total_pax, total_profit, morning_flights,
        midday_flights, evening_flights, busiest, profitable,
        break_even, site_summaries,
    )

    return {
        "total_flights_network": total_flights,
        "total_passengers_network": total_pax,
        "total_revenue_network": round(total_revenue, 2),
        "total_cost_network": round(total_cost, 2),
        "total_profit_network": round(total_profit, 2),
        "total_cancelled_network": total_cancelled,
        "profitable_sites": profitable,
        "unprofitable_sites": unprofitable,
        "break_even_ticket_price": round(break_even, 2) if break_even else None,
        "busiest_route": busiest,
        "demand_pattern_summary": {
            "morning_flights": morning_flights,
            "midday_flights": midday_flights,
            "evening_flights": evening_flights,
        },
        "narrative": narrative,
    }


def _build_narrative(
    total_flights: int,
    total_pax: int,
    total_profit: float,
    morning: int,
    midday: int,
    evening: int,
    busiest: Optional[dict],
    profitable: List[str],
    break_even: Optional[float],
    site_summaries: dict,
) -> str:
    if total_flights == 0:
        return "No flights were dispatched. Try increasing demand_scale or checking weather conditions."

    parts = []

    morning_pct = round(100 * morning / total_flights) if total_flights > 0 else 0
    evening_pct = round(100 * evening / total_flights) if total_flights > 0 else 0
    parts.append(
        f"Morning commute (6-10am) accounted for {morning_pct}% of daily flights "
        f"({morning} flights); evening reversal (4-10pm) was {evening_pct}% ({evening} flights)."
    )

    if busiest:
        parts.append(
            f"The {busiest['origin']}\u2192{busiest['destination']} route was the busiest "
            f"with {busiest['flight_count']} departures."
        )

    avg_pax_per_flight = round(total_pax / total_flights, 1) if total_flights > 0 else 0
    parts.append(
        f"Network carried {total_pax} passengers across {total_flights} flights "
        f"(avg {avg_pax_per_flight} pax/flight)."
    )

    if profitable:
        parts.append(f"{len(profitable)} site(s) were profitable: {', '.join(profitable)}.")
    else:
        parts.append("No sites were profitable at the current ticket price.")

    if break_even is not None:
        parts.append(f"Network break-even ticket price: ${break_even:.2f}.")

    if total_profit > 0:
        parts.append(f"Total network profit: ${total_profit:,.2f}.")
    else:
        parts.append(f"Total network loss: ${abs(total_profit):,.2f}.")

    return " ".join(parts)
