from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal, List, Tuple, Dict, Any

ConstraintMode = Literal["hard", "soft"]
ConstraintType = Literal["weather", "airspace", "terrain", "population"]
GeometryType = Literal["circle", "polygon"]


@dataclass
class Constraint:
    name: str
    constraint_type: ConstraintType
    mode: ConstraintMode

    # 2D geometry
    geometry_type: GeometryType
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None
    radius_miles: Optional[float] = None
    polygon_points: Optional[List[Tuple[float, float]]] = None  # [(lat, lon), ...]

    # 2.5D structure
    floor_alt_ft: float = 0.0
    ceiling_alt_ft: float = 999999.0

    severity: float = 1.0
    metadata: Optional[Dict[str, Any]] = None