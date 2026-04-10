from __future__ import annotations

import os
import json
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import requests
from dotenv import load_dotenv

from backend.constraint_model import Constraint
from backend.airspace import load_airspace

load_dotenv(Path(__file__).with_name(".env"))

FORE_FLIGHT_BASE_URL = "https://aadp.foreflight.com"
AIRSPACES_PATH = "/api/v1/airspaces"
AIRSPACE_SOURCE = "foreflight"  # "foreflight" or "geojson"

# Operating region cache: West, South, East, North
NORCAL_BOUNDS: Tuple[float, float, float, float] = (-124.0, 35.5, -119.0, 39.5)

GLOBAL_AIRSPACE: Optional[List[Constraint]] = None
DEBUG_AIRSPACE = True

GLOBAL_AIRSPACE_GEOJSON: Optional[Dict[str, Any]] = None

def adprint(msg: str) -> None:
    if DEBUG_AIRSPACE:
        print(msg)


def _bbox_to_query(bounds: Tuple[float, float, float, float]) -> str:
    west, south, east, north = bounds
    return f"{west},{south},{east},{north}"


def _parse_altitude_limit(limit_value: Optional[float], reference: Optional[str]) -> Tuple[float, str]:
    ref = (reference or "").strip().upper()

    if ref in {"SFC", "GND", "GROUND"}:
        return 0.0, ref

    if limit_value is None:
        return 999999.0, ref or "UNL"

    try:
        return float(limit_value), ref
    except (TypeError, ValueError):
        return 0.0, ref or ""


def _airspace_mode(properties: Dict[str, Any]) -> str:
    level = str(properties.get("level", "")).upper()
    airspace_type = str(properties.get("airspace_type", "")).upper()
    generic_type = str(properties.get("type", "")).upper()

    hard_tokens = {
        "B", "C", "D",
        "RESTRICTED", "PROHIBITED", "TFR", "NSA", "MOA",
    }

    if level in hard_tokens:
        return "hard"
    if airspace_type in hard_tokens:
        return "hard"
    if generic_type in hard_tokens:
        return "hard"

    return "soft"

def _feature_airspace_class(feature: Dict[str, Any]) -> Optional[str]:
    props = feature.get("properties", {}) or {}

    candidates = [
        str(props.get("level", "")).upper(),
        str(props.get("airspace_type", "")).upper(),
        str(props.get("type", "")).upper(),
    ]
    joined = " | ".join(candidates)

    if "CLASS B" in joined or "CLASS_B" in joined or joined.strip() == "B":
        return "B"
    if "CLASS C" in joined or "CLASS_C" in joined or joined.strip() == "C":
        return "C"
    if "CLASS D" in joined or "CLASS_D" in joined or joined.strip() == "D":
        return "D"
    if "CLASS G" in joined or "CLASS_G" in joined or joined.strip() == "G":
        return "G"

    return None


def _geojson_feature_intersects_bounds(
    feature: Dict[str, Any],
    bounds: Tuple[float, float, float, float],
) -> bool:
    west, south, east, north = bounds
    geom = feature.get("geometry", {}) or {}
    coords = geom.get("coordinates", [])
    geom_type = geom.get("type")

    if geom_type == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                for lon, lat in ring:
                    if south <= lat <= north and west <= lon <= east:
                        return True

    elif geom_type == "Polygon":
        for ring in coords:
            for lon, lat in ring:
                if south <= lat <= north and west <= lon <= east:
                    return True

    return False

def filter_geojson_by_bounds_and_class(
    geojson: Dict[str, Any],
    bounds: Tuple[float, float, float, float],
    allowed_classes: Optional[set[str]] = None,
) -> Dict[str, Any]:
    features = geojson.get("features", [])
    filtered = []

    for feature in features:
        airspace_class = _feature_airspace_class(feature)
        if allowed_classes and airspace_class not in allowed_classes:
            continue
        if _geojson_feature_intersects_bounds(feature, bounds):
            filtered.append(feature)

    adprint(f"[AIRSPACE GEOJSON] returning {len(filtered)} filtered features")

    return {
        "type": "FeatureCollection",
        "features": filtered,
    }

def get_airspace_geojson_for_frontend(
    bounds: Tuple[float, float, float, float],
    allowed_classes: Optional[set[str]] = None,
) -> Dict[str, Any]:
    if AIRSPACE_SOURCE == "foreflight":
        geojson = get_global_airspace_geojson()
        return filter_geojson_by_bounds_and_class(geojson, bounds, allowed_classes)

    elif AIRSPACE_SOURCE == "geojson":
        base = os.path.dirname(__file__)
        path = os.path.join(base, "data", "airspace.geojson")

        with open(path, "r") as f:
            geojson = json.load(f)

        features = []
        for feature in geojson.get("features", []):
            if _geojson_feature_intersects_bounds(feature, bounds):
                features.append(feature)

        adprint(f"[AIRSPACE GEOJSON] returning {len(features)} local geojson features")
        return {
            "type": "FeatureCollection",
            "features": features,
        }

    return {"type": "FeatureCollection", "features": []}

def _airspace_severity(properties: Dict[str, Any]) -> float:
    mode = _airspace_mode(properties)
    return 1.0 if mode == "hard" else 0.5


def _feature_name(properties: Dict[str, Any]) -> str:
    return (
        properties.get("airspace_type")
        or properties.get("level")
        or properties.get("id")
        or "Unnamed Airspace"
    )


def _feature_to_constraints(feature: Dict[str, Any]) -> List[Constraint]:
    geometry = feature.get("geometry", {}) or {}
    properties = feature.get("properties", {}) or {}

    geom_type = geometry.get("type")
    coords = geometry.get("coordinates", [])

    if geom_type != "MultiPolygon":
        return []

    lower_ft, lower_ref = _parse_altitude_limit(
        properties.get("lower_limit"),
        properties.get("lower_limit_reference"),
    )
    upper_ft, upper_ref = _parse_altitude_limit(
        properties.get("upper_limit"),
        properties.get("upper_limit_reference"),
    )

    constraints: List[Constraint] = []

    for poly in coords:
        if not poly:
            continue

        outer_ring = poly[0]
        if not outer_ring:
            continue

        polygon_points = [(coord[1], coord[0]) for coord in outer_ring]

        constraints.append(
            Constraint(
                name=_feature_name(properties),
                constraint_type="airspace",
                mode=_airspace_mode(properties),
                geometry_type="polygon",
                polygon_points=polygon_points,
                floor_alt_ft=lower_ft,
                ceiling_alt_ft=upper_ft,
                severity=_airspace_severity(properties),
                metadata={
                    "source": "foreflight",
                    "feature_id": properties.get("id"),
                    "airspace_type": properties.get("airspace_type"),
                    "level": properties.get("level"),
                    "type": properties.get("type"),
                    "lower_limit": properties.get("lower_limit"),
                    "lower_limit_reference": lower_ref,
                    "upper_limit": properties.get("upper_limit"),
                    "upper_limit_reference": upper_ref,
                    "time_code": properties.get("time_code"),
                    "center_fix": properties.get("center_fix"),
                    "center_fix_type": properties.get("center_fix_type"),
                    "multiple_code": properties.get("multiple_code"),
                    "notes": properties.get("notes", []),
                },
            )
        )

    return constraints


def fetch_airspace_constraints(
    bounds: Tuple[float, float, float, float],
    api_key: Optional[str] = None,
    page_size: int = 100,
) -> List[Constraint]:
    api_key = api_key or os.getenv("FORE_FLIGHT_API_KEY")
    if not api_key:
        raise ValueError("Missing ForeFlight API key. Set FORE_FLIGHT_API_KEY or pass api_key.")

    url = f"{FORE_FLIGHT_BASE_URL}{AIRSPACES_PATH}"
    headers = {"x-api-key": api_key}

    page_token: Optional[str] = None
    constraints: List[Constraint] = []

    adprint(f"[AIRSPACE API] request bounds={bounds} page_size={page_size}")

    while True:
        params = {
            "bounding_box": _bbox_to_query(bounds),
            "page_size": str(page_size),
        }
        if page_token:
            params["page_token"] = page_token

        adprint(f"[AIRSPACE API] page_token={page_token}")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        payload = response.json()
        features = payload.get("features", [])
        metadata = payload.get("metadata", {}) or {}

        adprint(f"[AIRSPACE API] received {len(features)} features")

        for feature in features:
            constraints.extend(_feature_to_constraints(feature))

        page_token = metadata.get("page_token")
        adprint(f"[AIRSPACE API] next page_token={page_token}")
        if not page_token:
            break

    adprint(f"[AIRSPACE API] total constraints={len(constraints)}")
    return constraints


def get_global_airspace() -> List[Constraint]:
    global GLOBAL_AIRSPACE

    if GLOBAL_AIRSPACE is None:
        if AIRSPACE_SOURCE == "foreflight":
            adprint("[AIRSPACE API] loading NorCal/global airspace...")
            GLOBAL_AIRSPACE = fetch_airspace_constraints(NORCAL_BOUNDS)
            adprint(f"[AIRSPACE API] loaded {len(GLOBAL_AIRSPACE)} total NorCal constraints")

        elif AIRSPACE_SOURCE == "geojson":
            adprint("[AIRSPACE GEOJSON] loading local geojson airspace...")
            zones = load_airspace()

            constraints: List[Constraint] = []
            for z in zones:
                constraints.append(
                    Constraint(
                        name=z.get("name", "airspace"),
                        constraint_type="airspace",
                        mode=z.get("mode", "hard"),
                        geometry_type="polygon",
                        polygon_points=z.get("points", []),
                        floor_alt_ft=0.0,
                        ceiling_alt_ft=999999.0,
                        severity=1.0,
                        metadata={
                            "source": "geojson",
                            "hazard_type": z.get("hazard_type", "airspace"),
                            "type": "RPD",
                        },
                    )
                )

            GLOBAL_AIRSPACE = constraints
            adprint(f"[AIRSPACE GEOJSON] loaded {len(GLOBAL_AIRSPACE)} total geojson constraints")

        else:
            raise ValueError(f"Unknown AIRSPACE_SOURCE: {AIRSPACE_SOURCE}")

    return GLOBAL_AIRSPACE


def _constraint_intersects_bounds(
    constraint: Constraint,
    bounds: Tuple[float, float, float, float],
) -> bool:
    west, south, east, north = bounds

    if constraint.geometry_type == "circle":
        if constraint.center_lat is None or constraint.center_lon is None:
            return False
        return south <= constraint.center_lat <= north and west <= constraint.center_lon <= east

    if constraint.geometry_type == "polygon" and constraint.polygon_points:
        for lat, lon in constraint.polygon_points:
            if south <= lat <= north and west <= lon <= east:
                return True

    return False


def filter_constraints_by_bounds(
    constraints: List[Constraint],
    bounds: Tuple[float, float, float, float],
) -> List[Constraint]:
    filtered = [c for c in constraints if _constraint_intersects_bounds(c, bounds)]
    adprint(f"[AIRSPACE API] filtered to {len(filtered)} constraints for bounds={bounds}")
    return filtered


def fetch_airspace_geojson(
    bounds: Tuple[float, float, float, float],
    api_key: Optional[str] = None,
    page_size: int = 100,
) -> Dict[str, Any]:
    api_key = api_key or os.getenv("FORE_FLIGHT_API_KEY")
    if not api_key:
        raise ValueError("Missing ForeFlight API key. Set FORE_FLIGHT_API_KEY or pass api_key.")

    url = f"{FORE_FLIGHT_BASE_URL}{AIRSPACES_PATH}"
    headers = {"x-api-key": api_key}

    all_features = []
    page_token: Optional[str] = None

    while True:
        params = {
            "bounding_box": _bbox_to_query(bounds),
            "page_size": str(page_size),
        }
        if page_token:
            params["page_token"] = page_token

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        payload = response.json()
        all_features.extend(payload.get("features", []))

        metadata = payload.get("metadata", {}) or {}
        page_token = metadata.get("page_token")
        if not page_token:
            break

    return {
        "type": "FeatureCollection",
        "features": all_features,
        "metadata": {"page_token": None},
    }

def _polygon_centroid(points: List[Tuple[float, float]]) -> Tuple[float, float]:
    if not points:
        return 0.0, 0.0
    lat = sum(p[0] for p in points) / len(points)
    lon = sum(p[1] for p in points) / len(points)
    return lat, lon


def _max_radius_miles(points: List[Tuple[float, float]], center: Tuple[float, float]) -> float:
    import math

    if not points:
        return 0.0

    clat, clon = center
    ref_lat = clat
    miles_per_deg_lat = 69.0
    miles_per_deg_lon = 69.0 * math.cos(math.radians(ref_lat))

    cx = clon * miles_per_deg_lon
    cy = clat * miles_per_deg_lat

    rmax = 0.0
    for lat, lon in points:
        x = lon * miles_per_deg_lon
        y = lat * miles_per_deg_lat
        rmax = max(rmax, math.hypot(x - cx, y - cy))
    return rmax


def classify_overlay_type(constraint: Constraint) -> Optional[str]:
    metadata = constraint.metadata or {}

    candidates = [
        str(metadata.get("level", "")).upper(),
        str(metadata.get("airspace_type", "")).upper(),
        str(metadata.get("type", "")).upper(),
        str(constraint.name).upper(),
    ]

    joined = " | ".join(candidates)

    if "CLASS B" in joined or "CLASS_B" in joined or joined.strip() == "B":
        return "B"
    if "CLASS C" in joined or "CLASS_C" in joined or joined.strip() == "C":
        return "C"
    if "CLASS D" in joined or "CLASS_D" in joined or joined.strip() == "D":
        return "D"
    if "CLASS G" in joined or "CLASS_G" in joined or joined.strip() == "G":
        return "G"

    return None

def build_frontend_airspace_overlays(bounds: Tuple[float, float, float, float]) -> List[dict]:
    constraints = filter_constraints_by_bounds(get_global_airspace(), bounds)
    overlays: List[dict] = []

    print(f"[AIRSPACE OVERLAYS] input constraints={len(constraints)}")

    for c in constraints:
        overlay_class = classify_overlay_type(c)
        if overlay_class is None:
            continue

        if c.geometry_type == "polygon" and c.polygon_points:
            center = _polygon_centroid(c.polygon_points)
            radius = _max_radius_miles(c.polygon_points, center)

            overlays.append({
                "name": c.name,
                "class": overlay_class,
                "shape": "circle",
                "center_lat": center[0],
                "center_lon": center[1],
                "radius_miles": round(min(radius, 25.0), 2),
                "floor_alt_ft": c.floor_alt_ft,
                "ceiling_alt_ft": c.ceiling_alt_ft,
                "metadata": c.metadata,
            })

    print(f"[AIRSPACE OVERLAYS] returning overlays={len(overlays)}")
    if overlays:
        print(f"[AIRSPACE OVERLAYS] sample={overlays[0]}")

    return overlays