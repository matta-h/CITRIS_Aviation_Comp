from __future__ import annotations
import math
from typing import List, Tuple

def miles_per_degree(ref_lat: float) -> Tuple[float, float]:
    return 69.0, 69.0 * math.cos(math.radians(ref_lat))

def to_local_miles(lat: float, lon: float, ref_lat: float) -> Tuple[float, float]:
    mpd_lat, mpd_lon = miles_per_degree(ref_lat)
    return lon * mpd_lon, lat * mpd_lat

def point_to_segment_distance(px, py, x1, y1, x2, y2) -> float:
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx = x1 + t * dx
    cy = y1 + t * dy
    return math.hypot(px - cx, py - cy)

def segment_intersects_circle(a, b, zone, radius_scale=1.0) -> bool:
    ref_lat = (a["lat"] + b["lat"] + zone["lat"]) / 3.0
    x1, y1 = to_local_miles(a["lat"], a["lon"], ref_lat)
    x2, y2 = to_local_miles(b["lat"], b["lon"], ref_lat)
    cx, cy = to_local_miles(zone["lat"], zone["lon"], ref_lat)
    d = point_to_segment_distance(cx, cy, x1, y1, x2, y2)
    return d <= zone["radius_miles"] * radius_scale

def point_in_polygon(x: float, y: float, poly: List[Tuple[float, float]]) -> bool:
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        hit = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        )
        if hit:
            inside = not inside
        j = i
    return inside

def segments_intersect(p1, p2, q1, q2) -> bool:
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    o1 = orient(p1, p2, q1)
    o2 = orient(p1, p2, q2)
    o3 = orient(q1, q2, p1)
    o4 = orient(q1, q2, p2)
    return (o1 == 0 or o2 == 0 or (o1 > 0) != (o2 > 0)) and \
           (o3 == 0 or o4 == 0 or (o3 > 0) != (o4 > 0))

def segment_intersects_polygon(a, b, zone, buffer_miles=0.0) -> bool:
    pts = zone["points"]
    ref_lat = (a["lat"] + b["lat"] + sum(p[0] for p in pts) / len(pts)) / 3.0

    ax, ay = to_local_miles(a["lat"], a["lon"], ref_lat)
    bx, by = to_local_miles(b["lat"], b["lon"], ref_lat)
    poly = [to_local_miles(lat, lon, ref_lat) for lat, lon in pts]

    if point_in_polygon(ax, ay, poly) or point_in_polygon(bx, by, poly):
        return True

    for i in range(len(poly)):
        p1 = poly[i]
        p2 = poly[(i + 1) % len(poly)]
        if segments_intersect((ax, ay), (bx, by), p1, p2):
            return True

    return False

def segment_hits_zone(a, b, zone, radius_scale=1.0):
    geom = zone.get("geometry", "circle")

    if geom == "circle":
        return segment_intersects_circle(a, b, zone, radius_scale=radius_scale)
    elif geom == "polygon":
        return segment_intersects_polygon(a, b, zone)

    return False