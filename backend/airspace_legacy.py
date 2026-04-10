import json
import os

def load_airspace():
    base = os.path.dirname(__file__)
    path = os.path.join(base, "data", "airspace.geojson")

    with open(path, "r") as f:
        data = json.load(f)

    zones = []

    for feature in data["features"]:
        geom = feature["geometry"]

        # 🔥 FILTER FIRST (THIS IS THE FIX)
        if feature["properties"].get("type") not in ["R", "P", "D"]:
            continue

        # Only care about polygons
        if geom["type"] == "Polygon":
            polygon_sets = [geom["coordinates"][0]]
        elif geom["type"] == "MultiPolygon":
            polygon_sets = [poly[0] for poly in geom["coordinates"]]
        else:
            continue

        for coords in polygon_sets:
            points = [[lat, lon] for lon, lat in coords]
            zones.append({
                "name": feature["properties"].get("name", "airspace"),
                "geometry": "polygon",
                "points": points,
                "mode": "hard",
                "hazard_type": "airspace"
            })

    return zones