from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional

# ── Configurable parameters ──────────────────────────────────────────
FLEET_PARAMS: dict = {
    "taxi_time_min": 5.0,
    "charge_time_min": 30.0,
    "battery_reserve_pct": 20.0,
    "max_range_miles": 150.0,
}

PORT_CONFIG: dict = {
    # UC campuses: 3 total pads (1 takeoff/landing + 2 charging), 2 VTOLs — 1 pad always free
    "UCSC": {"vtol_count": 2, "takeoff_landing_pads": 1, "charging_pads": 2},
    "UCB":  {"vtol_count": 2, "takeoff_landing_pads": 1, "charging_pads": 2},
    "UCD":  {"vtol_count": 2, "takeoff_landing_pads": 1, "charging_pads": 2},
    "UCM":  {"vtol_count": 2, "takeoff_landing_pads": 1, "charging_pads": 2},
    # Airports: 4 total pads (2 takeoff/landing + 2 charging), 3 VTOLs — 1 pad always free
    "KSQL": {"vtol_count": 3, "takeoff_landing_pads": 2, "charging_pads": 2},
    "KNUQ": {"vtol_count": 3, "takeoff_landing_pads": 2, "charging_pads": 2},
    "KLVK": {"vtol_count": 3, "takeoff_landing_pads": 2, "charging_pads": 2},
    "KCVH": {"vtol_count": 3, "takeoff_landing_pads": 2, "charging_pads": 2},
    "KSNS": {"vtol_count": 3, "takeoff_landing_pads": 2, "charging_pads": 2},
    "KOAR": {"vtol_count": 3, "takeoff_landing_pads": 2, "charging_pads": 2},
}

# ── Fleet state ──────────────────────────────────────────────────────
# Each VTOL is a dict with a sorted list of scheduled events.
# Event types: taxiing_to_pad | in_flight | taxiing_to_charge | charging
FLEET: dict[str, dict] = {}


def _make_vtol(vtol_id: str, home_port: str) -> dict:
    return {
        "id": vtol_id,
        "home_port": home_port,
        "current_port": home_port,
        "battery_pct": 100.0,
        "events": [],
    }


def _init_fleet() -> None:
    FLEET.clear()
    for port_id, config in PORT_CONFIG.items():
        for i in range(1, config["vtol_count"] + 1):
            vtol_id = f"{port_id}-{i:02d}"
            FLEET[vtol_id] = _make_vtol(vtol_id, port_id)


_init_fleet()


# ── ISO time helpers ─────────────────────────────────────────────────
def _parse_iso(iso: str) -> datetime:
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return datetime.fromisoformat(iso[:16])


def _add_minutes(iso: str, minutes: float) -> str:
    return (_parse_iso(iso) + timedelta(minutes=minutes)).isoformat(timespec="minutes")


def _diff_minutes(iso_start: str, iso_end: str) -> float:
    return (_parse_iso(iso_end) - _parse_iso(iso_start)).total_seconds() / 60.0


# ── Battery helpers ──────────────────────────────────────────────────
def battery_cost_pct(distance_miles: float) -> float:
    return (distance_miles / FLEET_PARAMS["max_range_miles"]) * 100.0


def _battery_at(vtol: dict, current_iso: str) -> float:
    """Real-time battery %, interpolating during in_flight and charging events."""
    for ev in vtol["events"]:
        if ev["start_iso"] <= current_iso < ev["end_iso"]:
            bstart = ev.get("battery_start")
            bend = ev.get("battery_end")
            if bstart is None:
                break
            # in_flight and charging interpolate linearly; all others are constant
            if ev["type"] in ("in_flight", "charging"):
                duration = _diff_minutes(ev["start_iso"], ev["end_iso"])
                elapsed = _diff_minutes(ev["start_iso"], current_iso)
                frac = min(elapsed / duration, 1.0) if duration > 0 else 1.0
                return round(bstart + frac * (bend - bstart), 1)
            return round(bstart, 1)
    return vtol["battery_pct"]


# ── State queries at a given sim time ────────────────────────────────
def _status_at(vtol: dict, current_iso: str) -> str:
    for ev in vtol["events"]:
        if ev["start_iso"] <= current_iso < ev["end_iso"]:
            return ev["type"]
    return "available"


def _location_at(vtol: dict, current_iso: str) -> Optional[str]:
    for ev in vtol["events"]:
        if ev["start_iso"] <= current_iso < ev["end_iso"]:
            return ev.get("port")  # None = in transit
    return vtol["current_port"]


def _flight_id_at(vtol: dict, current_iso: str) -> Optional[str]:
    for ev in vtol["events"]:
        if ev["start_iso"] <= current_iso < ev["end_iso"]:
            return ev.get("flight_id")
    return None


def _next_free_iso(vtol: dict) -> Optional[str]:
    return vtol["events"][-1]["end_iso"] if vtol["events"] else None


def _is_free_by(vtol: dict, iso: str) -> bool:
    free = _next_free_iso(vtol)
    return free is None or free <= iso


# ── Pad conflict check ───────────────────────────────────────────────
def _pad_available(port_id: str, window_start: str, window_end: str) -> bool:
    if port_id not in PORT_CONFIG:
        return True
    pad_count = PORT_CONFIG[port_id]["takeoff_landing_pads"]
    conflicts = 0
    for vtol in FLEET.values():
        for ev in vtol["events"]:
            if ev.get("port") == port_id and ev["type"] in ("taxiing_to_pad",):
                if ev["start_iso"] < window_end and ev["end_iso"] > window_start:
                    conflicts += 1
    return conflicts < pad_count


# ── Assign VTOL to a flight ──────────────────────────────────────────
def assign_vtol(
    origin_port: str,
    departure_iso: str,
    arrival_iso: str,
    distance_miles: float,
    flight_id: str,
    destination_port: str,
    exchange_info: Optional[dict] = None,
) -> Optional[str]:
    """
    Assign the best available VTOL at origin_port.
    Schedules taxi/flight/charge events.

    exchange_info (optional): {
        "stop_port": str,
        "leg1_arrival_iso": str,
        "leg2_departure_iso": str,
        "leg1_dist": float,
        "leg2_dist": float,
    }
    When provided, the in_flight event is split into leg1 / ground_stop / leg2
    so battery is frozen during the ground stop at the exchange airport.

    Returns vtol_id, or None if no VTOL can be assigned.
    """
    taxi_min = FLEET_PARAMS["taxi_time_min"]
    charge_min = FLEET_PARAMS["charge_time_min"]
    reserve = FLEET_PARAMS["battery_reserve_pct"]
    cost = battery_cost_pct(distance_miles)

    taxi_start_iso = _add_minutes(departure_iso, -taxi_min)

    candidates = [
        v for v in FLEET.values()
        if v["current_port"] == origin_port
        and _is_free_by(v, taxi_start_iso)
        and v["battery_pct"] - cost >= reserve
    ]

    if not candidates:
        return None

    if not _pad_available(origin_port, taxi_start_iso, departure_iso):
        return None

    best = max(candidates, key=lambda v: v["battery_pct"])
    pre_flight_battery = best["battery_pct"]
    new_battery = round(pre_flight_battery - cost, 2)

    best["events"].append({
        "type": "taxiing_to_pad",
        "start_iso": taxi_start_iso,
        "end_iso": departure_iso,
        "flight_id": flight_id,
        "port": origin_port,
        "battery_start": pre_flight_battery,
        "battery_end": pre_flight_battery,
    })

    if exchange_info:
        # Split into leg1 → ground_stop → leg2 so battery freezes at exchange stop.
        leg1_cost = round(battery_cost_pct(exchange_info["leg1_dist"]), 2)
        leg2_cost = round(battery_cost_pct(exchange_info["leg2_dist"]), 2)
        battery_after_leg1 = round(pre_flight_battery - leg1_cost, 2)
        battery_after_leg2 = round(battery_after_leg1 - leg2_cost, 2)

        best["events"].append({
            "type": "in_flight",
            "start_iso": departure_iso,
            "end_iso": exchange_info["leg1_arrival_iso"],
            "flight_id": flight_id,
            "port": None,
            "from_port": origin_port,
            "to_port": exchange_info["stop_port"],
            "battery_start": pre_flight_battery,
            "battery_end": battery_after_leg1,
        })
        best["events"].append({
            "type": "ground_stop",
            "start_iso": exchange_info["leg1_arrival_iso"],
            "end_iso": exchange_info["leg2_departure_iso"],
            "flight_id": flight_id,
            "port": exchange_info["stop_port"],
            "battery_start": battery_after_leg1,
            "battery_end": battery_after_leg1,
        })
        best["events"].append({
            "type": "in_flight",
            "start_iso": exchange_info["leg2_departure_iso"],
            "end_iso": arrival_iso,
            "flight_id": flight_id,
            "port": None,
            "from_port": exchange_info["stop_port"],
            "to_port": destination_port,
            "battery_start": battery_after_leg1,
            "battery_end": battery_after_leg2,
        })
    else:
        best["events"].append({
            "type": "in_flight",
            "start_iso": departure_iso,
            "end_iso": arrival_iso,
            "flight_id": flight_id,
            "port": None,
            "from_port": origin_port,
            "to_port": destination_port,
            "battery_start": pre_flight_battery,
            "battery_end": new_battery,
        })

    taxi_done_iso = _add_minutes(arrival_iso, taxi_min)
    best["events"].append({
        "type": "taxiing_to_charge",
        "start_iso": arrival_iso,
        "end_iso": taxi_done_iso,
        "flight_id": flight_id,
        "port": destination_port,
        "battery_start": new_battery,
        "battery_end": new_battery,
    })

    if new_battery < 100.0:
        charge_duration = ((100.0 - new_battery) / 100.0) * charge_min
        charge_done_iso = _add_minutes(taxi_done_iso, charge_duration)
        best["events"].append({
            "type": "charging",
            "start_iso": taxi_done_iso,
            "end_iso": charge_done_iso,
            "flight_id": None,
            "port": destination_port,
            "battery_start": new_battery,
            "battery_end": 100.0,
        })
        best["battery_pct"] = 100.0
    else:
        best["battery_pct"] = new_battery

    best["current_port"] = destination_port
    best["events"].sort(key=lambda e: e["start_iso"])

    return best["id"]


# ── Fleet snapshot ───────────────────────────────────────────────────
def get_fleet_snapshot(current_iso: Optional[str] = None) -> list:
    if current_iso is None:
        current_iso = datetime.now().isoformat(timespec="minutes")

    result = []
    for vtol in FLEET.values():
        status = _status_at(vtol, current_iso)
        port = _location_at(vtol, current_iso)
        battery = _battery_at(vtol, current_iso)
        flight_id = _flight_id_at(vtol, current_iso)

        from_port = to_port = None
        if status == "in_flight":
            for ev in vtol["events"]:
                if ev["type"] == "in_flight" and ev["start_iso"] <= current_iso < ev["end_iso"]:
                    from_port = ev.get("from_port")
                    to_port = ev.get("to_port")
                    break

        result.append({
            "id": vtol["id"],
            "home_port": vtol["home_port"],
            "current_port": port if port is not None else vtol["current_port"],
            "status": status,
            "battery_pct": battery,
            "flight_id": flight_id,
            "busy_until": _next_free_iso(vtol),
            "from_port": from_port,
            "to_port": to_port,
        })

    return sorted(result, key=lambda v: v["id"])


# ── Params API ───────────────────────────────────────────────────────
def get_fleet_params() -> dict:
    return {
        "fleet_params": dict(FLEET_PARAMS),
        "port_config": {k: dict(v) for k, v in PORT_CONFIG.items()},
    }


def update_fleet_params(params: dict) -> dict:
    if "fleet_params" in params:
        for key in ("taxi_time_min", "charge_time_min", "battery_reserve_pct", "max_range_miles"):
            if key in params["fleet_params"]:
                FLEET_PARAMS[key] = float(params["fleet_params"][key])

    if "port_config" in params:
        for port_id, config in params["port_config"].items():
            if port_id in PORT_CONFIG:
                for k in ("takeoff_landing_pads", "charging_pads"):
                    if k in config:
                        PORT_CONFIG[port_id][k] = int(config[k])
                if "vtol_count" in config:
                    PORT_CONFIG[port_id]["vtol_count"] = int(config["vtol_count"])
        _sync_fleet()

    return get_fleet_params()


def _sync_fleet() -> None:
    for port_id, config in PORT_CONFIG.items():
        desired = config["vtol_count"]
        # Add missing VTOLs
        for i in range(1, desired + 1):
            vtol_id = f"{port_id}-{i:02d}"
            if vtol_id not in FLEET:
                FLEET[vtol_id] = _make_vtol(vtol_id, port_id)
        # Remove excess VTOLs
        i = desired + 1
        while True:
            vtol_id = f"{port_id}-{i:02d}"
            if vtol_id not in FLEET:
                break
            del FLEET[vtol_id]
            i += 1


def reset_fleet() -> None:
    _init_fleet()
