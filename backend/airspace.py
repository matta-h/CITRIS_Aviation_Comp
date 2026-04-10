from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional


OPENAIR_FILENAME = "us_asp_v2.txt"


def _parse_dms_token(deg_str: str, min_str: str, sec_str: str, hemi: str) -> float:
    deg = float(deg_str)
    minute = float(min_str)
    sec = float(sec_str)
    value = deg + minute / 60.0 + sec / 3600.0

    hemi = hemi.upper().strip()
    if hemi in {"S", "W"}:
        value *= -1.0
    return value


def _parse_openair_dp(line: str) -> Optional[List[float]]:
    """
    Parses:
    DP 37:32:49 N 122:12:15 W
    Returns [lat, lon]
    """
    m = re.match(
        r"^DP\s+(\d+):(\d+):(\d+(?:\.\d+)?)\s+([NS])\s+(\d+):(\d+):(\d+(?:\.\d+)?)\s+([EW])$",
        line.strip(),
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    lat = _parse_dms_token(m.group(1), m.group(2), m.group(3), m.group(4))
    lon = _parse_dms_token(m.group(5), m.group(6), m.group(7), m.group(8))
    return [lat, lon]


def _normalize_altitude(text: str) -> Dict[str, Any]:
    """
    Parses examples like:
    1500ft AMSL
    SFC
    GND
    FL180
    UNL
    """
    raw = (text or "").strip()
    upper = raw.upper()

    if not raw:
        return {"raw": "", "value_ft": None, "reference": None}

    if upper in {"SFC", "GND", "GROUND"}:
        return {"raw": raw, "value_ft": 0.0, "reference": upper}

    if upper in {"UNL", "UNLIMITED"}:
        return {"raw": raw, "value_ft": None, "reference": upper}

    fl_match = re.match(r"^FL\s*(\d+)$", upper)
    if fl_match:
        fl = float(fl_match.group(1))
        return {"raw": raw, "value_ft": fl * 100.0, "reference": "FL"}

    ft_match = re.match(r"^(-?\d+(?:\.\d+)?)\s*FT\s*(.*)$", upper)
    if ft_match:
        return {
            "raw": raw,
            "value_ft": float(ft_match.group(1)),
            "reference": ft_match.group(2).strip() or "FT",
        }

    return {"raw": raw, "value_ft": None, "reference": None}


def _class_to_mode(ac: str, name: str) -> str:
    text = f"{ac} {name}".upper()

    hard_tokens = [
        "P", "PROHIBITED",
        "R", "RESTRICTED",
        "DANGER",
        "TFR",
        "NSA",
        "MOA",
    ]

    for token in hard_tokens:
        if token in text:
            return "hard"

    return "soft"


def _finalize_block(block: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    points = block.get("points", [])
    if len(points) < 3:
        return None

    # close polygon if not already closed
    if points[0] != points[-1]:
        points.append(points[0])

    lower = _normalize_altitude(block.get("lower_raw", ""))
    upper = _normalize_altitude(block.get("upper_raw", ""))

    ac = (block.get("ac") or "").strip().upper()
    name = (block.get("name") or "airspace").strip()

    return {
        "name": name,
        "geometry": "polygon",
        "points": points,  # [lat, lon]
        "mode": _class_to_mode(ac, name),
        "hazard_type": "airspace",
        "class": ac,
        "lower_raw": lower["raw"],
        "upper_raw": upper["raw"],
        "lower_ft": lower["value_ft"],
        "upper_ft": upper["value_ft"],
        "lower_ref": lower["reference"],
        "upper_ref": upper["reference"],
    }


def load_airspace() -> List[Dict[str, Any]]:
    """
    Parses an OpenAIR v2 file into normalized polygon airspace records.

    Recognized fields:
    AC = class/type
    AN = name
    AL = lower altitude
    AH = upper altitude
    DP = polygon point
    """
    base = os.path.dirname(__file__)
    path = os.path.join(base, "data", OPENAIR_FILENAME)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    zones: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("*"):
            continue

        if line.startswith("AC "):
            if current is not None:
                zone = _finalize_block(current)
                if zone is not None:
                    zones.append(zone)

            current = {
                "ac": line[3:].strip(),
                "name": "",
                "lower_raw": "",
                "upper_raw": "",
                "points": [],
            }
            continue

        if current is None:
            continue

        if line.startswith("AN "):
            current["name"] = line[3:].strip()
            continue

        if line.startswith("AL "):
            current["lower_raw"] = line[3:].strip()
            continue

        if line.startswith("AH "):
            current["upper_raw"] = line[3:].strip()
            continue

        if line.startswith("DP "):
            pt = _parse_openair_dp(line)
            if pt is not None:
                current["points"].append(pt)
            continue

        # ignore other OpenAIR lines for now:
        # AY, V X=, DC, DB, DA, etc.

    if current is not None:
        zone = _finalize_block(current)
        if zone is not None:
            zones.append(zone)

    return zones