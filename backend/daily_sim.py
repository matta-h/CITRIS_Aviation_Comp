from __future__ import annotations

import math
import os
import time
import requests
from datetime import datetime as _datetime
from math import ceil, floor
from typing import Dict, List, Optional, Tuple

from backend.routing_single import NODES
from backend.demand_model import get_demand_for_timeslot
from backend.fleet import PORT_CONFIG

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

# ── Fixed daily costs per site (staff + facility, regardless of flight count) ──
# Source: $216,468 annual infra OPEX ÷ 365 days, scaled by site size.
AIRPORT_FIXED_DAILY_USD = 593.00   # 4 pads, 3 VTOLs  ($216,468/yr ÷ 365)
UC_FIXED_DAILY_3PAD_USD = 440.00   # 3 pads, 2 VTOLs  (~$160k/yr ÷ 365)
UC_FIXED_DAILY_2PAD_USD = 380.00   # 2 pads, 1 VTOL   (~$139k/yr ÷ 365)

UC_NODES = {"UCB", "UCSC", "UCD", "UCM"}
AIRPORT_NODES = {"KSQL", "KNUQ", "KLVK", "KCVH", "KSNS", "KOAR"}

def _pad_capacity() -> Dict[str, int]:
    """Computed fresh each call so runtime PORT_CONFIG changes are reflected."""
    return {
        port: cfg["takeoff_landing_pads"] + cfg["charging_pads"]
        for port, cfg in PORT_CONFIG.items()
    }

ROUTE_BASE = "http://127.0.0.1:8000"


# ── Aircraft state ────────────────────────────────────────────────────────────

class Aircraft:
    def __init__(self, aircraft_id: str, home_port: str) -> None:
        self.id = aircraft_id
        self.home_port = home_port
        self.current_port = home_port   # ground position — only updates on landing
        self.in_flight = False
        self.dest_port: Optional[str] = None
        self.arrival_at_minute = 0      # minute this aircraft touches down
        self.available_at_minute = 360  # available after landing + turnaround (6:00am start)
        self.total_flight_minutes = 0.0
        self.total_flights = 0
        self.total_distance_miles = 0.0


MAX_LOITER_MINUTES = 30
LOITER_STEP_MINUTES = 5


def _ground_count(fleet: List["Aircraft"], port: str) -> int:
    """Aircraft currently on the ground at this port (not in flight)."""
    return sum(1 for a in fleet if a.current_port == port and not a.in_flight)


def _predicted_ground_count(fleet: List["Aircraft"], port: str, at_minute: int) -> int:
    """
    Conservatively estimate how many aircraft will occupy `port` at `at_minute`.
    Counts ground-bound aircraft that haven't been dispatched away yet (we can't
    predict future dispatch decisions, so we assume they remain) plus inbound
    aircraft that will have landed by then.
    """
    count = 0
    for a in fleet:
        if a.in_flight:
            if a.dest_port == port and a.arrival_at_minute <= at_minute:
                count += 1
        else:
            if a.current_port == port:
                count += 1
    return count


def _build_fleet() -> List[Aircraft]:
    fleet: List[Aircraft] = []
    for port_id, cfg in PORT_CONFIG.items():
        for i in range(1, cfg["vtol_count"] + 1):
            fleet.append(Aircraft(f"{port_id}-{i:02d}", port_id))
    return fleet


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minute_to_iso(date: str, minute: int) -> str:
    h = minute // 60
    m = minute % 60
    return f"{date}T{h:02d}:{m:02d}"


def _fixed_daily_cost(port_id: str) -> float:
    """Fixed operating cost for one site for one day, based on current pad/VTOL config."""
    if port_id in AIRPORT_NODES:
        return AIRPORT_FIXED_DAILY_USD
    cfg = PORT_CONFIG.get(port_id, {})
    total_pads = cfg.get("takeoff_landing_pads", 1) + cfg.get("charging_pads", 2)
    vtol_count = cfg.get("vtol_count", 2)
    if total_pads >= 3 and vtol_count >= 2:
        return UC_FIXED_DAILY_3PAD_USD
    return UC_FIXED_DAILY_2PAD_USD


def _compute_costs(
    total_time_minutes: float,
    total_distance_miles: float,
    ticket_price: float,
    passengers: int,
    pilot_enabled: bool = True,
) -> dict:
    """Per-flight variable costs only (energy + maintenance + optional pilot)."""
    cost_pilot = (total_time_minutes / 60.0) * PILOT_HOURLY_RATE_USD if pilot_enabled else 0.0

    energy_kwh = ENERGY_KWH_PER_FLIGHT_REFERENCE * (total_distance_miles / REFERENCE_DISTANCE_MILES)
    energy_kwh = max(20.0, min(energy_kwh, 180.0))
    cost_energy = energy_kwh * ELECTRICITY_PRICE_USD_KWH

    cost_maintenance = MAINTENANCE_COST_PER_FLIGHT_USD

    cost_total = cost_pilot + cost_energy + cost_maintenance
    revenue = passengers * ticket_price
    profit = revenue - cost_total

    return {
        "revenue": round(revenue, 2),
        "cost_pilot": round(cost_pilot, 2),
        "cost_energy": round(cost_energy, 2),
        "cost_maintenance": round(cost_maintenance, 2),
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
    pilot_enabled: bool = True,
    battery_min_pct: float = 20.0,
    turnaround_base_minutes: int = 20,
    min_passengers: int = 1,
) -> dict:
    sim_start_wall = time.time()

    pad_capacity = _pad_capacity()
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

        # Step 0: process landings — update current_port for any aircraft that
        # has now touched down (arrival_at_minute has passed)
        for a in fleet:
            if a.in_flight and a.arrival_at_minute <= current_minute:
                a.current_port = a.dest_port
                a.in_flight = False
                a.dest_port = None

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
                if dest != origin and demand_acc[(origin, dest)] >= min_passengers
            ]
            if not eligible:
                continue

            eligible.sort(key=lambda x: x[1], reverse=True)

            for dest, acc_demand in eligible:
                # Find aircraft on the ground at origin, turnaround complete, not yet used this step
                candidates = [
                    a for a in fleet
                    if a.current_port == origin
                    and not a.in_flight
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

                # Skip dispatch if route would drain battery below minimum
                from backend.fleet import battery_cost_pct
                if battery_cost_pct(total_dist_mi) > (100.0 - battery_min_pct):
                    print(
                        f"[SIM] {current_iso[11:16]} {origin}->{dest} skipped "
                        f"(battery infeasible at {total_dist_mi:.1f} mi)"
                    )
                    demand_acc[(origin, dest)] = 0.0
                    continue

                passengers = max(min_passengers, min(4, int(floor(acc_demand))))
                turnaround = turnaround_base_minutes + (15 if total_dist_mi > 60 else 0)
                base_arrival_minute = current_minute + ceil(total_time_min)

                # ── Loiter if destination is predicted to be full at arrival ──
                cap = pad_capacity.get(dest, 4)
                loiter_minutes = 0
                arrival_minute = base_arrival_minute
                while loiter_minutes < MAX_LOITER_MINUTES:
                    if _predicted_ground_count(fleet, dest, arrival_minute) < cap:
                        break
                    loiter_minutes += LOITER_STEP_MINUTES
                    arrival_minute = base_arrival_minute + loiter_minutes

                if loiter_minutes >= MAX_LOITER_MINUTES and \
                        _predicted_ground_count(fleet, dest, arrival_minute) >= cap:
                    print(
                        f"[SIM] {current_iso[11:16]} {origin}->{dest} cancelled "
                        f"(dest full, max loiter {MAX_LOITER_MINUTES} min exceeded)"
                    )
                    cancelled_by_origin[origin] += 1
                    demand_acc[(origin, dest)] = 0.0
                    continue

                if loiter_minutes > 0:
                    print(
                        f"[SIM] {current_iso[11:16]} {origin}->{dest} loitering "
                        f"{loiter_minutes} min (dest {dest} at capacity)"
                    )

                total_time_min_with_loiter = total_time_min + loiter_minutes

                # Aircraft leaves the origin pad immediately but doesn't
                # occupy the destination pad until it physically lands.
                aircraft.in_flight = True
                aircraft.dest_port = dest
                aircraft.arrival_at_minute = arrival_minute
                aircraft.available_at_minute = arrival_minute + turnaround
                aircraft.total_flight_minutes += total_time_min_with_loiter
                aircraft.total_flights += 1
                aircraft.total_distance_miles += total_dist_mi

                demand_acc[(origin, dest)] = max(0.0, demand_acc[(origin, dest)] - passengers)
                dispatched_this_step.add(aircraft.id)

                arrival_iso = _minute_to_iso(date, arrival_minute)
                wx_status = _weather_status(origin, current_iso)
                # Pilot cost billed for loiter time too (still airborne)
                financials = _compute_costs(total_time_min_with_loiter, total_dist_mi, ticket_price, passengers, pilot_enabled)

                flight_id_counter += 1
                record = {
                    "flight_id": flight_id_counter,
                    "origin": origin,
                    "destination": dest,
                    "departure_time_iso": current_iso,
                    "arrival_time_iso": arrival_iso,
                    "total_time_minutes": round(total_time_min_with_loiter, 2),
                    "total_distance_miles": round(total_dist_mi, 2),
                    "loiter_minutes": loiter_minutes,
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

                loiter_str = f" (+{loiter_minutes}min loiter)" if loiter_minutes else ""
                print(
                    f"[SIM] {current_iso[11:16]} {origin}->{dest} dispatched  "
                    f"{passengers} pax  {total_dist_mi:.1f} mi  "
                    f"{total_time_min_with_loiter:.0f} min{loiter_str}  "
                    f"profit ${financials['profit']:.2f}"
                )

    # ── Summaries ─────────────────────────────────────────────────────────────
    fixed_daily_costs = {port_id: _fixed_daily_cost(port_id) for port_id in PORT_CONFIG}

    site_summaries = _build_site_summaries(
        flight_log, fleet, cancelled_by_origin, start_hour, end_hour, fixed_daily_costs
    )
    network_summary = _build_network_summary(
        flight_log, site_summaries, cancelled_by_origin, fixed_daily_costs
    )

    result = {
        "date": date,
        "parameters": {
            "ticket_price": ticket_price,
            "demand_scale": demand_scale,
            "pilot_enabled": pilot_enabled,
            "battery_min_pct": battery_min_pct,
            "turnaround_base_minutes": turnaround_base_minutes,
            "min_passengers": min_passengers,
        },
        "flight_log": flight_log,
        "site_summaries": site_summaries,
        "network_summary": network_summary,
        "simulation_duration_seconds": round(time.time() - sim_start_wall, 2),
    }

    _write_sim_report(result)
    return result


# ── Report writer ─────────────────────────────────────────────────────────────

_OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs")


def _write_sim_report(result: dict) -> None:
    os.makedirs(_OUTPUTS_DIR, exist_ok=True)

    date        = result["date"]
    params      = result["parameters"]
    net         = result["network_summary"]
    sites       = result["site_summaries"]
    flight_log  = result["flight_log"]
    run_secs    = result["simulation_duration_seconds"]

    # Filename encodes the key parameters for easy comparison
    pilot_tag   = "piloted" if params["pilot_enabled"] else "autonomous"
    fname = (
        f"{date}_price{int(params['ticket_price'])}"
        f"_demand{params['demand_scale']}"
        f"_{pilot_tag}"
        f"_minpax{params['min_passengers']}"
        f"_{_datetime.now().strftime('%H%M%S')}"
        ".txt"
    )
    path = os.path.join(_OUTPUTS_DIR, fname)

    lines: List[str] = []
    w = lines.append  # shorthand

    def sep(char="─", width=64):
        w(char * width)

    sep("═")
    w(f"  CITRIS eVTOL NETWORK SIMULATION REPORT")
    w(f"  Date: {date}   Generated: {_datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sep("═")

    # ── Parameters ──────────────────────────────────────────────────
    w("")
    w("SIMULATION PARAMETERS")
    sep()
    w(f"  Ticket price          : ${params['ticket_price']:.2f}")
    w(f"  Demand scale          : {params['demand_scale']}")
    w(f"  Pilot enabled         : {'Yes' if params['pilot_enabled'] else 'No (autonomous)'}")
    w(f"  Min battery reserve   : {params['battery_min_pct']}%")
    w(f"  Min passengers/flight : {params['min_passengers']}")
    w(f"  Turnaround base time  : {params['turnaround_base_minutes']} min")

    # ── Vertiport config (snapshot at run time) ──────────────────────
    w("")
    w("VERTIPORT CONFIGURATION")
    sep()
    w(f"  {'Site':<8} {'Total Pads':>10} {'VTOLs':>7}")
    sep("-")
    for port_id, cfg in sorted(PORT_CONFIG.items()):
        total_pads = cfg["takeoff_landing_pads"] + cfg["charging_pads"]
        w(f"  {port_id:<8} {total_pads:>10} {cfg['vtol_count']:>7}")

    # ── Network summary ──────────────────────────────────────────────
    w("")
    w("NETWORK SUMMARY")
    sep()
    w(f"  Total flights         : {net['total_flights_network']}")
    w(f"  Total passengers      : {net['total_passengers_network']}")
    w(f"  Cancelled flights     : {net['total_cancelled_network']}")
    w(f"  Total revenue         : ${net['total_revenue_network']:,.2f}")
    w(f"  Variable cost (flights): ${net['total_variable_cost_network']:,.2f}")
    w(f"  Fixed daily cost      : ${net['total_fixed_cost_network']:,.2f}")
    w(f"  Total cost            : ${net['total_cost_network']:,.2f}")
    w(f"  Net profit/loss       : ${net['total_profit_network']:,.2f}")
    be = net.get("break_even_ticket_price")
    w(f"  Break-even ticket     : ${be:.2f}" if be else "  Break-even ticket     : N/A")
    if net.get("busiest_route"):
        br = net["busiest_route"]
        w(f"  Busiest route         : {br['origin']} → {br['destination']} ({br['flight_count']} flights)")
    dp = net.get("demand_pattern_summary", {})
    w(f"  Morning flights (6-10): {dp.get('morning_flights', 0)}")
    w(f"  Midday flights (10-16): {dp.get('midday_flights', 0)}")
    w(f"  Evening flights(16-22): {dp.get('evening_flights', 0)}")
    w(f"  Profitable sites      : {', '.join(net['profitable_sites']) or 'None'}")
    w(f"  Unprofitable sites    : {', '.join(net['unprofitable_sites']) or 'None'}")

    # ── Per-site breakdown ───────────────────────────────────────────
    w("")
    w("PER-SITE BREAKDOWN")
    sep()
    hdr = f"  {'Site':<6} {'Dep':>4} {'Arr':>4} {'Pax':>5} {'Revenue':>10} {'VarCost':>9} {'FixCost':>9} {'Profit':>10} {'Util%':>6} {'Cancel':>7}"
    w(hdr)
    sep("-")
    for site_id in sorted(sites):
        s = sites[site_id]
        util_pct = round(s["fleet_utilization"] * 100, 1)
        w(
            f"  {site_id:<6}"
            f" {s['total_departures']:>4}"
            f" {s['total_arrivals']:>4}"
            f" {s['total_passengers_departed']:>5}"
            f" {s['gross_revenue']:>10,.0f}"
            f" {s['total_variable_cost']:>9,.0f}"
            f" {s['fixed_daily_cost']:>9,.0f}"
            f" {s['net_profit']:>10,.0f}"
            f" {util_pct:>5.1f}%"
            f" {s['cancelled_flights']:>7}"
        )

    # ── Overcrowding / loiter events ─────────────────────────────────
    loitered = [f for f in flight_log if f.get("loiter_minutes", 0) > 0]
    w("")
    w("CONGESTION / LOITER EVENTS")
    sep()
    if loitered:
        w(f"  {len(loitered)} flight(s) required loitering:")
        dest_counts: Dict[str, int] = {}
        total_loiter_min = 0
        for f in loitered:
            dest_counts[f["destination"]] = dest_counts.get(f["destination"], 0) + 1
            total_loiter_min += f["loiter_minutes"]
        for dest, count in sorted(dest_counts.items(), key=lambda x: -x[1]):
            w(f"    {dest}: {count} loiter event(s)")
        w(f"  Total loiter time     : {total_loiter_min} min")
        w(f"  Avg loiter per event  : {total_loiter_min / len(loitered):.1f} min")
    else:
        w("  No loitering required — all vertiports had capacity on arrival.")

    # ── Top routes ───────────────────────────────────────────────────
    w("")
    w("TOP ROUTES (by flight count)")
    sep()
    route_counts: Dict[str, dict] = {}
    for f in flight_log:
        key = f"{f['origin']}→{f['destination']}"
        if key not in route_counts:
            route_counts[key] = {"count": 0, "pax": 0, "profit": 0.0}
        route_counts[key]["count"]  += 1
        route_counts[key]["pax"]    += f["passengers"]
        route_counts[key]["profit"] += f["profit"]
    top = sorted(route_counts.items(), key=lambda x: -x[1]["count"])[:15]
    w(f"  {'Route':<16} {'Flights':>7} {'Pax':>6} {'Profit':>10}")
    sep("-")
    for route, s in top:
        w(f"  {route:<16} {s['count']:>7} {s['pax']:>6} {s['profit']:>10,.0f}")

    # ── Narrative ────────────────────────────────────────────────────
    w("")
    w("NARRATIVE")
    sep()
    for sentence in net.get("narrative", "").split(". "):
        if sentence.strip():
            w(f"  {sentence.strip()}.")
    w("")
    w(f"  Simulation completed in {run_secs:.1f}s")
    sep("═")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[SIM] Report saved → {path}")


# ── Site summaries ────────────────────────────────────────────────────────────

def _build_site_summaries(
    flight_log: List[dict],
    fleet: List[Aircraft],
    cancelled_by_origin: Dict[str, int],
    start_hour: int,
    end_hour: int,
    fixed_daily_costs: Dict[str, float],
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
        variable_cost = sum(f["cost_total"] for f in departures)
        fixed_cost = fixed_daily_costs.get(node_id, 0.0)
        total_cost = variable_cost + fixed_cost

        summaries[node_id] = {
            "total_departures": len(departures),
            "total_arrivals": len(arrivals),
            "total_passengers_departed": sum(f["passengers"] for f in departures),
            "total_passengers_arrived": sum(f["passengers"] for f in arrivals),
            "gross_revenue": round(gross_revenue, 2),
            "total_pilot_cost": round(sum(f["cost_pilot"] for f in departures), 2),
            "total_energy_cost": round(sum(f["cost_energy"] for f in departures), 2),
            "total_maintenance_cost": round(sum(f["cost_maintenance"] for f in departures), 2),
            "fixed_daily_cost": round(fixed_cost, 2),
            "total_variable_cost": round(variable_cost, 2),
            "total_cost": round(total_cost, 2),
            "net_profit": round(gross_revenue - total_cost, 2),
            "avg_load_factor": round(avg_pax / 4.0, 3),
            "fleet_utilization": round(utilization, 4),
            "cancelled_flights": cancelled_by_origin.get(node_id, 0),
            "top_routes": top_routes,
            "aircraft_positions_at_eod": [
                {
                    "aircraft_id": a.id,
                    "current_port": a.dest_port if a.in_flight else a.current_port,
                    "in_flight_at_eod": a.in_flight,
                    "is_away_from_home": (a.dest_port if a.in_flight else a.current_port) != a.home_port,
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
    fixed_daily_costs: Dict[str, float],
) -> dict:
    total_flights = len(flight_log)
    total_pax = sum(f["passengers"] for f in flight_log)
    total_revenue = sum(f["revenue"] for f in flight_log)
    total_variable_cost = sum(f["cost_total"] for f in flight_log)
    total_fixed_cost = sum(fixed_daily_costs.values())
    total_cost = total_variable_cost + total_fixed_cost
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
        "total_variable_cost_network": round(total_variable_cost, 2),
        "total_fixed_cost_network": round(total_fixed_cost, 2),
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
