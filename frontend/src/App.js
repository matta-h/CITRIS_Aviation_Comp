import { useEffect, useMemo, useState, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Tooltip,
  Polyline,
  CircleMarker,
  Circle,
  Polygon
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet-defaulticon-compatibility";
import "leaflet-defaulticon-compatibility/dist/leaflet-defaulticon-compatibility.css";
import RightPanel from "./components/RightPanel";
import BottomToolbar from "./components/BottomToolbar";
import LeftPanel from "./components/LeftPanel";
import { point, featureCollection, buffer, union } from "@turf/turf";
import L from "leaflet";

function milesToMeters(miles) {
  return miles * 1609.34;
}

function routeColor(routeClass) {
  if (routeClass === "green") return "green";
  if (routeClass === "yellow") return "gold";
  if (routeClass === "orange") return "orange";
  if (routeClass === "detour") return "deepskyblue";
  if (routeClass === "field") return "blue";
  return "red";
}

function weatherColor(status) {
  if (status === "good") return "green";
  if (status === "caution") return "gold";
  if (status === "unsafe") return "red";
  return "gray";
}

function populationColor(status) {
  if (status === "very_high") return "#d93025";  // red
  if (status === "high")      return "#f5821f";  // orange
  if (status === "medium")    return "#f5c842";  // yellow
  if (status === "low")       return "#74b87a";  // muted green
  return null; // minimal — don't render
}

function populationRadius(status) {
  if (status === "very_high") return 10;
  if (status === "high")      return 8;
  if (status === "medium")    return 6;
  if (status === "low")       return 4;
  return 0;
}

function gridRadiusFromWind(wind) {
  if (wind == null) return 4;
  if (wind < 5) return 4;
  if (wind < 10) return 6;
  if (wind < 15) return 8;
  return 10;
}

function formatVisibilityMiles(meters) {
  if (meters == null) return "N/A";
  return (meters / 1609.34).toFixed(1);
}

function gridCellRadiusMeters() {
  return 16000;
}

function buildHazardPolygons(points) {
  const unsafePoints = points.filter((p) => p.weather?.status === "unsafe");
  if (unsafePoints.length === 0) return [];

  const radiusKm = 11;
  const bufferedFeatures = unsafePoints.map((p) => {
    const pt = point([p.lon, p.lat]);
    return buffer(pt, radiusKm, { units: "kilometers" });
  });

  if (bufferedFeatures.length === 0) return [];

  let merged = bufferedFeatures[0];
  for (let i = 1; i < bufferedFeatures.length; i++) {
    try {
      const mergedResult = union(featureCollection([merged, bufferedFeatures[i]]));
      if (mergedResult) merged = mergedResult;
    } catch (err) {
      console.warn("Union failed for hazard polygon merge:", err);
    }
  }

  if (!merged || !merged.geometry) return [];

  if (merged.geometry.type === "Polygon") {
    return [merged.geometry.coordinates[0].map(([lon, lat]) => [lat, lon])];
  }

  if (merged.geometry.type === "MultiPolygon") {
    return merged.geometry.coordinates.map((poly) =>
      poly[0].map(([lon, lat]) => [lat, lon])
    );
  }

  return [];
}

function airspaceStyle(feature) {
  const props = feature?.properties || {};

  const rawName = props.name ?? props.NAME ?? props.title ?? props.TITLE ?? "";
  const rawType =
    props.type ?? props.TYPE ?? props.class ?? props.CLASS ??
    props.category ?? props.CATEGORY ?? props.airspace_type ?? props.AIRSPACE_TYPE ?? "";
  const rawLevel =
    props.level ?? props.LEVEL ?? props.airspace_class ?? props.AIRSPACE_CLASS ?? "";

  const name = String(rawName).trim().toUpperCase();
  const type = String(rawType).trim().toUpperCase();
  const level = String(rawLevel).trim().toUpperCase();
  const text = `${name} ${level} ${type}`.trim();

  let color = "green";

  if (text.includes("PROHIBITED") || type === "P") color = "purple";
  else if (text.includes("RESTRICTED") || type === "R") color = "red";
  else if (text.includes("DANGER") || type === "D") color = "orange";
  else if (text.includes("CLASS B")) color = "red";
  else if (text.includes("CLASS C")) color = "orange";
  else if (text.includes("CLASS D")) color = "blue";
  else if (text.includes("CLASS E")) color = "gold";
  else if (text.includes("E2") || text.includes("E3") || text.includes("E4")) color = "gold";
  else if (text.includes("CLASS G")) color = "green";
  else if (type === "B") color = "red";
  else if (type === "C") color = "orange";
  else if (type === "D") color = "blue";
  else if (type.startsWith("E")) color = "gold";
  else if (type === "G") color = "green";

  return { color, fillColor: color, fillOpacity: 0.15, weight: 2 };
}

const evtolIcon = new L.Icon({
  iconUrl: "/evtol.png",
  iconSize: [40, 40],
  iconAnchor: [20, 20],
});

// Per-VTOL map display constants
const VTOL_STATUS_COLORS = {
  available:           "#4caf50",
  taxiing_to_pad:      "#ffb74d",
  in_flight:           "#4fc3f7",
  taxiing_to_charge:   "#ffb74d",
  charging:            "#ff9800",
  queued:              "#ce93d8",
  inoperable:          "#ef5350",
};

const VTOL_STATUS_LABELS = {
  available:           "Available",
  taxiing_to_pad:      "Taxiing to Pad",
  in_flight:           "In Flight",
  taxiing_to_charge:   "Taxiing to Charger",
  charging:            "Charging",
  queued:              "Queued",
  inoperable:          "Inoperable",
};

// Offset pattern: VTOL -01=N, -02=E, -03=S, -04=W (stable regardless of how many are flying)
// ~0.025° ≈ 1.7 mi — invisible at zoom 7 overview, fans out nicely at zoom 9+
const VTOL_PORT_OFFSETS = [
  [ 0.025,  0.000],  // 01 — North
  [ 0.000,  0.035],  // 02 — East
  [-0.025,  0.000],  // 03 — South
  [ 0.000, -0.035],  // 04 — West
];

// ─────────────────────────────────────────────
// Geographic distance between two [lat,lon] points (miles).
// Fast flat-earth approximation — fine for regional scale.
// ─────────────────────────────────────────────
function segmentMiles(p1, p2) {
  const lat = (p1[0] + p2[0]) / 2;
  const mpLat = 69.0;
  const mpLon = 69.0 * Math.cos(lat * Math.PI / 180);
  const dy = (p2[0] - p1[0]) * mpLat;
  const dx = (p2[1] - p1[1]) * mpLon;
  return Math.sqrt(dx * dx + dy * dy);
}

// Cache cumulative arc-lengths per polyline so we don't recompute every tick.
// Key = first point stringified (cheap, unique enough for our use).
const POLY_ARC_CACHE = new Map();

function getArcLengths(polyline) {
  const key = polyline.length + '|' + polyline[0];
  if (POLY_ARC_CACHE.has(key)) return POLY_ARC_CACHE.get(key);

  const arcs = [0];
  for (let i = 1; i < polyline.length; i++) {
    arcs.push(arcs[i - 1] + segmentMiles(polyline[i - 1], polyline[i]));
  }
  POLY_ARC_CACHE.set(key, arcs);
  if (POLY_ARC_CACHE.size > 50) {
    // Evict oldest entry to prevent unbounded growth
    POLY_ARC_CACHE.delete(POLY_ARC_CACHE.keys().next().value);
  }
  return arcs;
}

// ─────────────────────────────────────────────
// Arc-length parameterized interpolation.
// frac 0→1 maps to geographic distance along
// the polyline, not segment count.
// This ensures constant apparent visual speed
// regardless of how densely the polyline is
// sampled in different sections.
// ─────────────────────────────────────────────
function interpolatePosition(polyline, frac) {
  if (!polyline || polyline.length === 0) return [0, 0];
  if (polyline.length === 1) return polyline[0];

  const clamped = Math.max(0, Math.min(1, frac));
  if (clamped <= 0) return polyline[0];
  if (clamped >= 1) return polyline[polyline.length - 1];

  const arcs = getArcLengths(polyline);
  const totalLen = arcs[arcs.length - 1];
  if (totalLen === 0) return polyline[0];

  const target = clamped * totalLen;

  // Binary search for the segment containing `target`
  let lo = 0;
  let hi = arcs.length - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (arcs[mid] <= target) lo = mid;
    else hi = mid;
  }

  const segLen = arcs[hi] - arcs[lo];
  const t = segLen > 0 ? (target - arcs[lo]) / segLen : 0;
  const [lat1, lon1] = polyline[lo];
  const [lat2, lon2] = polyline[hi];
  return [lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t];
}

// ─────────────────────────────────────────────
// Compute flight status string
// ─────────────────────────────────────────────
function computeFlightStatus(flight, elapsedMinutes) {
  if (elapsedMinutes < 0) return "waiting_departure";

  const totalMinutes = flight.routeData?.total_time_minutes || 1;
  if (elapsedMinutes >= totalMinutes) return "arrived";

  if (!flight.isExchange) return "enroute";

  const leg1Min = flight.leg1Minutes || 0;
  const exchangeMin = flight.exchangeDelayMinutes || 30;

  if (elapsedMinutes <= leg1Min) return "enroute_leg1";
  if (elapsedMinutes <= leg1Min + exchangeMin) return "turnaround";
  return "enroute_leg2";
}

// ─────────────────────────────────────────────
// Replicate altitude_profile.py's altitude_at_distance
// entirely on the frontend. This is necessary because
// the backend returns profiles with only 2 points
// (start/end of the simplified polyline), giving no
// climb/cruise/descent shape.
//
// Parameters match altitude_profile.py defaults:
//   cruise_alt_ft      = 4500
//   climb_distance_miles  = 2.0
//   descent_distance_miles = 2.0
//   vertical_transition_miles = 0.15
// ─────────────────────────────────────────────
const VERTICAL_TRANSITION_MILES = 0.15;  // matches altitude_profile.py
const CRUISE_ALT_FT      = 4500.0;
const CLIMB_DIST_MILES   = 4.0;   // Joby S4: ~4 min climb at 750 fpm, ~4 mi forward
const DESCENT_DIST_MILES = 4.0;   // symmetric
const CRUISE_SPEED_MPH   = 120.0;

// Vertiport elevations ft — mirrors mission_planner.py VERTIPORT_ELEVATION_FT
const VERTIPORT_ELEVATION_FT = {
  UCSC: 784.0,
  UCB:  328.0,
  UCD:  120.0,
  UCM:  260.0,
  KSQL:  7.0,
  KNUQ: 30.0,
  KLVK: 371.0,
  KCVH: 223.0,
  KSNS:  79.0,
  KOAR: 135.0,
};

function vertiportElevation(nodeId) {
  return VERTIPORT_ELEVATION_FT[nodeId] ?? 0.0;
}

function altitudeAtDistance(distMiles, totalDistMiles, originAltFt, destAltFt) {
  if (totalDistMiles <= 0) return originAltFt;

  const cruiseAlt = CRUISE_ALT_FT;
  const vt = VERTICAL_TRANSITION_MILES; // 0.15 mi
  const climbDist  = CLIMB_DIST_MILES;  // 4.0 mi
  const descentDist = DESCENT_DIST_MILES; // 4.0 mi

  const depTransAlt = Math.min(cruiseAlt, originAltFt + 1500.0);
  const arrTransAlt = Math.min(cruiseAlt, destAltFt + 1500.0);

  const distFromEnd = totalDistMiles - distMiles;

  // Departure vertical VTOL lift
  if (distMiles < vt) {
    const frac = Math.max(0, Math.min(1, distMiles / vt));
    return originAltFt + frac * (depTransAlt - originAltFt);
  }

  // Forward climb to cruise
  if (distMiles < climbDist) {
    const frac = Math.max(0, Math.min(1,
      (distMiles - vt) / Math.max(climbDist - vt, 1e-6)));
    return depTransAlt + frac * (cruiseAlt - depTransAlt);
  }

  // Arrival vertical VTOL descent
  if (distFromEnd < vt) {
    const frac = Math.max(0, Math.min(1, distFromEnd / vt));
    return destAltFt + frac * (arrTransAlt - destAltFt);
  }

  // Descent from cruise
  if (distFromEnd < descentDist) {
    const frac = Math.max(0, Math.min(1,
      (distFromEnd - vt) / Math.max(descentDist - vt, 1e-6)));
    return arrTransAlt + frac * (cruiseAlt - arrTransAlt);
  }

  return cruiseAlt;
}

// Returns { altFt, speedMph, distanceMiles } — all computed from first principles.
function computeFlightTelemetry(flight, elapsedMinutes) {
  if (elapsedMinutes < 0 || elapsedMinutes === null) {
    return { altFt: vertiportElevation(flight.start), speedMph: 0, distanceMiles: 0 };
  }

  const status = computeFlightStatus(flight, elapsedMinutes);

  if (status === "waiting_departure") {
    return { altFt: vertiportElevation(flight.start), speedMph: 0, distanceMiles: null };
  }
  if (status === "arrived") {
    return { altFt: vertiportElevation(flight.end), speedMph: 0, distanceMiles: null };
  }
  if (status === "turnaround") {
    const exchangeId = flight.routeData?.exchange_stop ?? flight.routeData?.exchange_stops?.[0];
    return { altFt: vertiportElevation(exchangeId), speedMph: 0, distanceMiles: null };
  }

  const isLeg2      = status === "enroute_leg2";
  const leg1Min     = flight.leg1Minutes || 0;
  const leg2Min     = flight.leg2Minutes || 0;
  const exchangeMin = flight.exchangeDelayMinutes || 30;

  const leg1Dist = flight.routeData?.legs?.[0]?.distance_miles ?? 0;
  const leg2Dist = flight.routeData?.legs?.[1]?.distance_miles ?? 0;

  const legElapsed   = isLeg2 ? elapsedMinutes - leg1Min - exchangeMin : elapsedMinutes;
  const legTotalMin  = isLeg2 ? leg2Min
    : (flight.isExchange ? leg1Min : (flight.routeData?.total_time_minutes || 1));
  const legTotalDist = isLeg2 ? leg2Dist
    : (flight.isExchange ? leg1Dist : (flight.routeData?.total_distance_miles || 1));

  const legTimeFrac  = legTotalMin > 0 ? Math.max(0, Math.min(legElapsed / legTotalMin, 1)) : 1;
  const legDistMiles = legTimeFrac * legTotalDist;
  const distFromEnd  = legTotalDist - legDistMiles;

  // Determine origin/destination node IDs for this leg
  const originId = isLeg2
    ? (flight.routeData?.exchange_stop ?? flight.routeData?.exchange_stops?.[0] ?? flight.start)
    : flight.start;
  const destId = isLeg2
    ? flight.end
    : (flight.routeData?.exchange_stop ?? flight.routeData?.exchange_stops?.[0] ?? flight.end);

  const originAlt = vertiportElevation(originId);
  const destAlt   = vertiportElevation(destId);

  const altFt = altitudeAtDistance(legDistMiles, legTotalDist, originAlt, destAlt);

  // Speed: ramps up during climb phase, ramps down during descent phase
  let speedMph;
  if (legDistMiles < VERTICAL_TRANSITION_MILES) {
    // VTOL vertical lift: near-zero horizontal speed
    speedMph = Math.round((legDistMiles / VERTICAL_TRANSITION_MILES) * 20);
  } else if (legDistMiles < CLIMB_DIST_MILES) {
    // Forward climb: accelerate 20→120 mph
    const frac = (legDistMiles - VERTICAL_TRANSITION_MILES) / (CLIMB_DIST_MILES - VERTICAL_TRANSITION_MILES);
    speedMph = Math.round(20 + frac * (CRUISE_SPEED_MPH - 20));
  } else if (distFromEnd < VERTICAL_TRANSITION_MILES) {
    // VTOL vertical descent: near-zero horizontal speed
    speedMph = Math.round((distFromEnd / VERTICAL_TRANSITION_MILES) * 20);
  } else if (distFromEnd < DESCENT_DIST_MILES) {
    // Approach descent: decelerate 120→20 mph
    const frac = (distFromEnd - VERTICAL_TRANSITION_MILES) / (DESCENT_DIST_MILES - VERTICAL_TRANSITION_MILES);
    speedMph = Math.round(20 + frac * (CRUISE_SPEED_MPH - 20));
  } else {
    speedMph = CRUISE_SPEED_MPH;
  }

  return { altFt: Math.round(altFt), speedMph, distanceMiles: legDistMiles };
}
//
// Model:
//   • polyline encodes distance (not time)
//   • for exchange flights, leg1 occupies
//     [0, leg1PolyEndFrac] of the polyline,
//     leg2 occupies [leg1PolyEndFrac, 1]
//   • vertical phase: first/last VERTICAL_TRANSITION_MILES
//     of each leg, aircraft stays at fixed lat/lon
// ─────────────────────────────────────────────
function computeFlightPositionAltitudeAware(flight, elapsedMinutes) {
  const poly = flight.routeData?.polyline || [];
  if (poly.length < 2) return null;

  const status = computeFlightStatus(flight, elapsedMinutes);

  // ── Terminal / ground states — no math needed ──
  if (status === "arrived")           return poly[poly.length - 1];
  if (status === "waiting_departure") return poly[0];
  if (status === "turnaround") {
    return flight.exchangeStopPosition ?? interpolatePosition(poly, leg1PolyEndFracFor(flight));
  }

  // ── Shared leg geometry ──
  const leg1Dist = flight.routeData?.legs?.[0]?.distance_miles ?? 0;
  const leg2Dist = flight.routeData?.legs?.[1]?.distance_miles ?? 0;
  const totalDist = (leg1Dist + leg2Dist) || flight.routeData?.total_distance_miles || 1;
  const leg1PolyEndFrac = flight.isExchange ? (leg1Dist / totalDist) : 1;

  const leg1Min     = flight.leg1Minutes || 0;
  const leg2Min     = flight.leg2Minutes || 0;
  const exchangeMin = flight.exchangeDelayMinutes || 30;

  const isLeg2     = status === "enroute_leg2";
  const legElapsed = isLeg2 ? elapsedMinutes - leg1Min - exchangeMin : elapsedMinutes;
  const legTotalMin = isLeg2 ? leg2Min
    : (flight.isExchange ? leg1Min : (flight.routeData?.total_time_minutes || 1));
  const legTotalDist = isLeg2 ? leg2Dist
    : (flight.isExchange ? leg1Dist : totalDist);

  // Progress within this leg: 0→1 based on time
  const legTimeFrac = legTotalMin > 0
    ? Math.max(0, Math.min(legElapsed / legTotalMin, 1))
    : 1;

  // Distance along this leg in miles
  const legDistMiles = legTimeFrac * legTotalDist;
  const distFromLegEnd = legTotalDist - legDistMiles;



  // ── Vertical departure: freeze at this leg's origin ──
  if (legDistMiles < VERTICAL_TRANSITION_MILES) {
    if (isLeg2 && flight.exchangeStopPosition) return flight.exchangeStopPosition;
    return poly[0];
  }

  // ── Vertical arrival: freeze at this leg's destination ──
  if (distFromLegEnd < VERTICAL_TRANSITION_MILES) {
    if (!isLeg2 && flight.isExchange && flight.exchangeStopPosition) {
      return flight.exchangeStopPosition;
    }
    return poly[poly.length - 1];
  }

  // ── Normal forward flight ──
  // Map legTimeFrac onto the correct slice of the combined polyline.
  let polyFrac;
  if (!flight.isExchange) {
    polyFrac = legTimeFrac;
  } else if (!isLeg2) {
    // Leg 1: 0→leg1PolyEndFrac
    polyFrac = legTimeFrac * leg1PolyEndFrac;
  } else {
    // Leg 2: leg1PolyEndFrac→1
    polyFrac = leg1PolyEndFrac + legTimeFrac * (1 - leg1PolyEndFrac);
  }

  return interpolatePosition(poly, Math.max(0, Math.min(polyFrac, 1)));
}

// Small helper used by turnaround snap — avoids repeating leg geometry.
function leg1PolyEndFracFor(flight) {
  const leg1Dist = flight.routeData?.legs?.[0]?.distance_miles ?? 0;
  const leg2Dist = flight.routeData?.legs?.[1]?.distance_miles ?? 0;
  const totalDist = (leg1Dist + leg2Dist) || 1;
  return leg1Dist / totalDist;
}

function App() {
  const [airspaceGeojson, setAirspaceGeojson] = useState(null);
  const [airspaceSource, setAirspaceSource] = useState("openair");
  const [showAirspace, setShowAirspace] = useState(true);
  const [nodes, setNodes] = useState([]);
  const [selectedStart, setSelectedStart] = useState(null);
  const [selectedEnd, setSelectedEnd] = useState(null);
  const [routeRequestTime, setRouteRequestTime] = useState(null);
  const [pendingStart, setPendingStart] = useState("");
  const [pendingEnd, setPendingEnd] = useState("");
  const [pendingDepartureTime, setPendingDepartureTime] = useState(""); // "HH:MM" local time
  const [activeFlights, setActiveFlights] = useState([]);
  const [routeData, setRouteData] = useState(null);
  const [error, setError] = useState("");
  const [isRouting, setIsRouting] = useState(false);
  const [weather, setWeather] = useState({});
  const [obstacles, setObstacles] = useState({ no_fly_zones: [], slow_zones: [] });
  const [weatherGrid, setWeatherGrid] = useState([]);
  const [gridTime, setGridTime] = useState("2024-01-15T08:00");
  const [requestedGridTime, setRequestedGridTime] = useState(null);
  const [showWeatherGrid] = useState(true);
  const [showHazardRegions, setShowHazardRegions] = useState(true);
  const [showGridPoints, setShowGridPoints] = useState(true);
  const [selectedType, setSelectedType] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedDate, setSelectedDate] = useState("2024-01-15");
  const [startHour, setStartHour] = useState(6);
  const [endHour, setEndHour] = useState(22);
  const [currentTimeMinutes, setCurrentTimeMinutes] = useState(8 * 60);
  const [isPreloading, setIsPreloading] = useState(false);
  const [showWeather, setShowWeather] = useState(true);
  const [showPopulation, setShowPopulation] = useState(false);
  const [showFlights, setShowFlights] = useState(true);
  const [populationGrid, setPopulationGrid] = useState([]);
  const [populationLoaded, setPopulationLoaded] = useState(false);
  const [fleet, setFleet] = useState([]);

  // ── Sim clock controls ──────────────────────
  const [isPlaying, setIsPlaying] = useState(false);
  const [simSpeed, setSimSpeed] = useState(1);
  const simIntervalRef = useRef(null);
  const pendingDepartureMinutesRef = useRef(null);

  // Refs are the authoritative source for the interval callback.
  // State is only used for UI rendering.
  const isPlayingRef = useRef(false);
  const simSpeedRef  = useRef(1);
  const endHourRef   = useRef(endHour);

  // Keep endHourRef in sync (simSpeed ref is updated in handleSetSimSpeed below)
  useEffect(() => { endHourRef.current = endHour; }, [endHour]);

  // Expose a setter that updates both ref and state atomically
  const handleSetPlaying = (val) => {
    isPlayingRef.current = val;   // ref updates synchronously — interval sees it immediately
    setIsPlaying(val);            // state update triggers button re-render
  };

  const handleSetSimSpeed = (val) => {
    simSpeedRef.current = val;
    setSimSpeed(val);
  };

  // Single stable interval — reads exclusively from refs, never recreated
  useEffect(() => {
    simIntervalRef.current = setInterval(() => {
      if (!isPlayingRef.current) return;
      setCurrentTimeMinutes((prev) => {
        const next = prev + simSpeedRef.current;
        if (next >= endHourRef.current * 60) {
          isPlayingRef.current = false;
          setIsPlaying(false);
          return endHourRef.current * 60;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(simIntervalRef.current);
  }, []); // mount only — never recreated

  // ── Initialize / preload ────────────────────
  const handleInitialize = () => {
    if (!selectedDate) return;
    setIsPreloading(true);

    fetch("http://127.0.0.1:8000/weather-grid-day-preload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: selectedDate, start_hour: startHour, end_hour: endHour }),
    })
      .then((res) => {
        if (!res.ok) throw new Error("Pre-cache failed");
        return res.json();
      })
      .then(() => {
        const initialIso = `${selectedDate}T${String(startHour).padStart(2, "0")}:00`;
        setCurrentTimeMinutes(startHour * 60);
        setRequestedGridTime(initialIso);
      })
      .catch((err) => console.warn("Preload failed", err))
      .finally(() => setIsPreloading(false));
  };

  // ── Data fetching ───────────────────────────
  useEffect(() => {
    fetch(`http://127.0.0.1:8000/set-airspace-source?source=${airspaceSource}`)
      .then(() => fetch("http://127.0.0.1:8000/airspace-geojson"))
      .then((res) => res.json())
      .then((data) => setAirspaceGeojson(data))
      .catch(() => setAirspaceGeojson(null));
  }, [airspaceSource]);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/obstacles")
      .then((res) => res.json())
      .then((data) =>
        setObstacles({
          no_fly_zones: data?.no_fly_zones ?? [],
          slow_zones: data?.slow_zones ?? [],
        })
      )
      .catch(() => setObstacles({ no_fly_zones: [], slow_zones: [] }));

    fetch("http://127.0.0.1:8000/nodes")
      .then((res) => res.json())
      .then((data) => {
        const nodeArray = Object.entries(data).map(([id, val]) => ({ id, ...val }));
        setNodes(nodeArray);
      })
      .catch(() => setError("Failed to load nodes from backend."));
  }, []);

  // ── Route fetch → create flight ─────────────
  useEffect(() => {
    if (!selectedStart || !selectedEnd || !routeRequestTime) return;

    const url = `http://127.0.0.1:8000/route?start=${selectedStart}&end=${selectedEnd}&departure_time=${encodeURIComponent(routeRequestTime)}`;
    setIsRouting(true);
    setError("");

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("No feasible route found.");
        return res.json();
      })
      .then((data) => {
        const leg1Minutes =
          Array.isArray(data?.legs) && data.legs[0]?.distance_miles != null
            ? (data.legs[0].distance_miles / 120) * 60
            : 0;
        const leg2Minutes =
          Array.isArray(data?.legs) && data.legs[1]?.distance_miles != null
            ? (data.legs[1].distance_miles / 120) * 60
            : 0;

        // Use the departure time the user requested, or fall back to current sim time
        const chosenDepartureMinutes =
          pendingDepartureMinutesRef.current !== null
            ? pendingDepartureMinutesRef.current
            : currentTimeMinutes;
        pendingDepartureMinutesRef.current = null;

        // Format HH:MM for display
        const fmtTime = (totalMinutes) => {
          const h = Math.floor(totalMinutes / 60) % 24;
          const m = Math.round(totalMinutes % 60);
          return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
        };

        const flightDurationMinutes = data?.total_time_minutes ?? 0;
        const arrivalMinutes = chosenDepartureMinutes + flightDurationMinutes;

        const newFlight = {
          id: `flight-${Date.now()}`,
          start: selectedStart,
          end: selectedEnd,
          routeData: data,

          // UI display
          risk:
            data?.route_class === "orange"
              ? "High"
              : data?.route_class === "yellow" || data?.route_class === "detour"
                ? "Medium"
                : "Low",
          distanceText: data?.total_distance_miles
            ? `${Number(data.total_distance_miles).toFixed(1)} mi`
            : "—",
          etaText:
            data?.total_time_minutes != null
              ? `${Math.round(data.total_time_minutes)} min`
              : "—",
          departureLabel: fmtTime(chosenDepartureMinutes),
          arrivalLabel: fmtTime(arrivalMinutes),

          // VTOL assignment
          vtolId: data?.vtol_id ?? null,
          vtolBatteryCostPct: data?.vtol_battery_cost_pct ?? null,

          // Sim state
          departureTimeMinutes: chosenDepartureMinutes,
          isExchange: Array.isArray(data?.legs) && data.legs.length > 1,
          exchangeDelayMinutes: data?.selection_notes?.exchange_delay_min ?? 30,
          leg1Minutes,
          leg2Minutes,

          // Exact coordinates of the exchange stop so the marker snaps
          // to the real node position during the ground delay rather than
          // interpolating to a polyline fraction that may be slightly off.
          exchangeStopPosition: (() => {
            const stopId = data?.exchange_stops?.[0];
            const stopNode = stopId ? nodeMap[stopId] : null;
            return stopNode ? [stopNode.lat, stopNode.lon] : null;
          })(),
        };

        setRouteData(data);
        setSelectedType("flight");
        setSelectedNode(null);
        setActiveFlights((prev) => [newFlight, ...prev]);
        setError("");
        setIsRouting(false);

        // Refresh fleet to reflect newly assigned VTOL
        const currentIso = requestedGridTime ?? gridTime;
        fetch(`http://127.0.0.1:8000/fleet?current_time=${encodeURIComponent(currentIso)}`)
          .then((res) => res.json())
          .then((d) => setFleet(Array.isArray(d) ? d : []))
          .catch(() => {});
      })
      .catch((err) => {
        setRouteData(null);
        setError(err.message || "Failed to fetch route.");
        setIsRouting(false);
      });
  }, [selectedStart, selectedEnd, routeRequestTime]);

  // ── Update flight positions from sim clock ──
  useEffect(() => {
    setActiveFlights((prevFlights) =>
      prevFlights.map((flight) => {
        const elapsedMinutes = currentTimeMinutes - flight.departureTimeMinutes;
        const currentPosition = computeFlightPositionAltitudeAware(flight, elapsedMinutes);
        const status = computeFlightStatus(flight, elapsedMinutes);
        const totalMinutes = flight.routeData?.total_time_minutes || 1;
        const progress = elapsedMinutes < 0
          ? 0
          : Math.min(elapsedMinutes / totalMinutes, 1);
        const telemetry = computeFlightTelemetry(flight, elapsedMinutes);

        return { ...flight, currentPosition, status, progress, telemetry };
      })
    );
  }, [currentTimeMinutes]);

  // ── Sync grid time with clock ───────────────
  useEffect(() => {
    const hours = Math.floor(currentTimeMinutes / 60);
    const minutes = currentTimeMinutes % 60;
    const iso = `${selectedDate}T${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
    setRequestedGridTime(iso);
  }, [currentTimeMinutes, selectedDate]);

  // Debounce weather fetches — only fire 600ms after the clock stops changing.
  // This prevents a flood of API calls during playback.
  useEffect(() => {
    const effectiveWeatherTime = requestedGridTime ?? gridTime;
    const timer = setTimeout(() => {
      fetch(`http://127.0.0.1:8000/weather?target_time=${encodeURIComponent(effectiveWeatherTime)}`)
        .then((res) => res.json())
        .then((data) => setWeather(data ?? {}))
        .catch(() => setWeather({}));
    }, 600);
    return () => clearTimeout(timer);
  }, [gridTime, requestedGridTime]);

  useEffect(() => {
    if (!showWeatherGrid || !requestedGridTime) return;
    const timer = setTimeout(() => {
      fetch(`http://127.0.0.1:8000/weather-grid?target_time=${encodeURIComponent(requestedGridTime)}`)
        .then((res) => {
          if (!res.ok) throw new Error("Weather fetch failed");
          return res.json();
        })
        .then((data) => setWeatherGrid(Array.isArray(data) ? data : []))
        .catch(() => setWeatherGrid([]));
    }, 600);
    return () => clearTimeout(timer);
  }, [requestedGridTime, showWeatherGrid]);

  // ── Population grid — lazy loaded once when first toggled on ──
  // The TIF sampling is slow so we do it once and cache in state.
  // time_of_day derived from current sim clock hour.
  useEffect(() => {
    if (!showPopulation || populationLoaded) return;

    const hour = Math.floor(currentTimeMinutes / 60);
    const tod = (hour >= 6 && hour < 20) ? "day" : "night";

    fetch(`http://127.0.0.1:8000/population-grid?time_of_day=${tod}`)
      .then((res) => {
        if (!res.ok) throw new Error("Population fetch failed");
        return res.json();
      })
      .then((data) => {
        setPopulationGrid(Array.isArray(data) ? data : []);
        setPopulationLoaded(true);
      })
      .catch((err) => {
        console.warn("Population grid failed:", err);
        setPopulationGrid([]);
      });
  }, [showPopulation, populationLoaded]);
  // ── Fleet polling — debounced with sim clock ────────────────────
  useEffect(() => {
    const timer = setTimeout(() => {
      const currentIso = requestedGridTime ?? gridTime;
      fetch(`http://127.0.0.1:8000/fleet?current_time=${encodeURIComponent(currentIso)}`)
        .then((res) => res.json())
        .then((data) => setFleet(Array.isArray(data) ? data : []))
        .catch(() => {});
    }, 800);
    return () => clearTimeout(timer);
  }, [requestedGridTime, gridTime]);

  const nodeMap = useMemo(() => {
    const map = {};
    nodes.forEach((node) => { map[node.id] = node; });
    return map;
  }, [nodes]);

  // Parked VTOLs: all fleet entries that are NOT in_flight, with computed map position.
  // Offset determined by VTOL number (last 2 digits of ID) so position is stable.
  const parkedVtols = useMemo(() => {
    return (fleet ?? [])
      .filter((v) => v.status !== "in_flight")
      .map((v) => {
        const port = v.current_port;
        const node = nodeMap[port];
        if (!node) return null;
        const vtolNum = parseInt(v.id.slice(-2), 10) - 1; // 0-indexed
        const [dlat, dlon] = VTOL_PORT_OFFSETS[vtolNum % VTOL_PORT_OFFSETS.length];
        return { ...v, position: [node.lat + dlat, node.lon + dlon] };
      })
      .filter(Boolean);
  }, [fleet, nodeMap]);

  const routeSegments = useMemo(() => {
    if (!routeData || !routeData.legs) return [];
    return routeData.legs
      .map((leg) => {
        const fromNode = nodeMap[leg.from];
        const toNode = nodeMap[leg.to];
        if (!fromNode || !toNode) return null;
        const positions = [[fromNode.lat, fromNode.lon]];
        if (Array.isArray(leg.via)) {
          leg.via.forEach((p) => {
            if (p?.lat != null && p?.lon != null) positions.push([p.lat, p.lon]);
          });
        }
        positions.push([toNode.lat, toNode.lon]);
        return {
          positions,
          routeClass: leg.route_class,
          from: leg.from,
          to: leg.to,
          distance: leg.distance_miles,
          viaCount: Array.isArray(leg.via) ? leg.via.length : 0,
        };
      })
      .filter(Boolean);
  }, [routeData, nodeMap]);

  // ── Handlers ────────────────────────────────
  const handleNodeSelect = (nodeId) => {
    const node = nodeMap[nodeId] || null;
    setSelectedType("port");
    setSelectedNode(node);
  };

  const handleCreateFlight = () => {
    if (!pendingStart || !pendingEnd || pendingStart === pendingEnd) return;

    // If the user typed a departure time, parse it into minutes and build an ISO string.
    // Otherwise fall back to the current sim clock time.
    let departureMinutes = currentTimeMinutes;
    let requestTime = requestedGridTime ?? gridTime;

    if (pendingDepartureTime) {
      const [hStr, mStr] = pendingDepartureTime.split(":");
      const h = parseInt(hStr, 10);
      const m = parseInt(mStr || "0", 10);
      if (!isNaN(h) && !isNaN(m)) {
        departureMinutes = h * 60 + m;
        requestTime = `${selectedDate}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
      }
    }

    // Stash the chosen departure minutes so the flight object gets the right value
    // (the route useEffect runs asynchronously, so we pass it via a ref)
    pendingDepartureMinutesRef.current = departureMinutes;

    setSelectedStart(pendingStart);
    setSelectedEnd(pendingEnd);
    setRouteRequestTime(requestTime);
    setPendingStart("");
    setPendingEnd("");
    setPendingDepartureTime("");
    setError("");
  };

  const [selectedFlightId, setSelectedFlightId] = useState(null);

  const handleSelectFlight = (flight) => {
    setSelectedType("flight");
    setSelectedNode(null);
    setSelectedFlightId(flight.id);
    setRouteData(flight.routeData || null);
  };

  // Always pull live telemetry from the updating activeFlights array
  const selectedFlight = activeFlights.find((f) => f.id === selectedFlightId) || null;

  const handleDeleteFlight = (flightId) => {
    setActiveFlights((prev) => prev.filter((f) => f.id !== flightId));
  };

  const clearSelection = () => {
    setSelectedStart(null);
    setSelectedEnd(null);
    setRouteRequestTime(null);
    setRouteData(null);
    setError("");
  };

  // ── Render ──────────────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", width: "100%" }}>
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <LeftPanel
          nodes={nodes}
          activeFlights={activeFlights}
          fleet={fleet}
          pendingStart={pendingStart}
          pendingEnd={pendingEnd}
          setPendingStart={setPendingStart}
          setPendingEnd={setPendingEnd}
          pendingDepartureTime={pendingDepartureTime}
          setPendingDepartureTime={setPendingDepartureTime}
          onCreateFlight={handleCreateFlight}
          onSelectFlight={handleSelectFlight}
          onDeleteFlight={handleDeleteFlight}
        />

        <div style={{ flex: 1, position: "relative" }}>
          <MapContainer
            center={[37.5, -121.5]}
            zoom={7}
            style={{ height: "100%", width: "100%" }}
          >
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

            {/* No-fly zones */}
            {(obstacles?.no_fly_zones ?? []).map((zone, idx) => (
              <Circle
                key={`nfz-${idx}`}
                center={[zone.lat, zone.lon]}
                radius={milesToMeters(zone.radius_miles)}
                pathOptions={{ color: "red", fillColor: "red", fillOpacity: 0.2, weight: 2 }}
              >
                <Popup><b>{zone.name}</b><br />No-fly zone</Popup>
              </Circle>
            ))}

            {/* Slow zones */}
            {(obstacles?.slow_zones ?? []).map((zone, idx) => (
              <Circle
                key={`slow-${idx}`}
                center={[zone.lat, zone.lon]}
                radius={milesToMeters(zone.radius_miles)}
                pathOptions={{ color: "orange", fillColor: "yellow", fillOpacity: 0.15, weight: 2 }}
              >
                <Popup>
                  <b>{zone.name}</b><br />
                  Slow / caution zone<br />
                  Penalty: {zone.penalty}
                </Popup>
              </Circle>
            ))}

            {/* ── Active flight markers (in-flight eVTOL icon) ── */}
            {showFlights &&
              activeFlights.map((flight) => {
                const pos = flight.currentPosition;
                if (!pos || !Array.isArray(pos) || pos.length < 2) return null;

                return (
                  <Marker key={flight.id} position={pos} icon={evtolIcon}>
                    <Tooltip permanent={false} direction="top" offset={[0, -24]}>
                      {flight.vtolId && <><b>{flight.vtolId}</b><br /></>}
                      <b>{flight.start} → {flight.end}</b><br />
                      Status: {flight.status}<br />
                      Progress: {(flight.progress * 100).toFixed(0)}%<br />
                      Altitude: {flight.telemetry?.altFt != null ? `${Math.round(flight.telemetry.altFt).toLocaleString()} ft` : "—"}<br />
                      Speed: {flight.telemetry?.speedMph != null ? `${flight.telemetry.speedMph} mph` : "—"}<br />
                      Battery: {flight.vtolBatteryCostPct != null ? `−${flight.vtolBatteryCostPct.toFixed(0)}% this leg` : "—"}
                    </Tooltip>
                  </Marker>
                );
              })}

            {/* ── Parked VTOL markers ── */}
            {showFlights &&
              parkedVtols.map((vtol) => {
                const color = VTOL_STATUS_COLORS[vtol.status] ?? "#90caf9";
                const label = VTOL_STATUS_LABELS[vtol.status] ?? vtol.status;
                return (
                  <CircleMarker
                    key={`vtol-${vtol.id}`}
                    center={vtol.position}
                    radius={6}
                    pathOptions={{
                      color: "#001533",
                      fillColor: color,
                      fillOpacity: 0.9,
                      weight: 1.5,
                    }}
                  >
                    <Tooltip direction="top" offset={[0, -10]} opacity={0.97}>
                      <b>{vtol.id}</b><br />
                      {label}<br />
                      Battery: {vtol.battery_pct.toFixed(0)}%<br />
                      Port: {vtol.current_port}
                      {vtol.from_port && vtol.to_port && (
                        <><br />{vtol.from_port} → {vtol.to_port}</>
                      )}
                    </Tooltip>
                  </CircleMarker>
                );
              })}

            {/* ── Route polylines (most recently selected flight) ── */}
            {routeData?.raw_polyline && routeData.raw_polyline.length > 1 && (
              <Polyline
                positions={routeData.raw_polyline}
                pathOptions={{ color: "gray", weight: 2, opacity: 0.75, dashArray: "6,8" }}
              />
            )}
            {routeData?.polyline && routeData.polyline.length > 1 && (
              <Polyline
                positions={routeData.polyline}
                pathOptions={{ color: "blue", weight: 5, opacity: 0.5 }}
              >
                <Popup><b>Field Route</b><br />Continuous path (field-based routing)</Popup>
              </Polyline>
            )}

            {/* ── Weather grid points ── */}
            {showGridPoints &&
              weatherGrid.map((pt, idx) => {
                const wx = pt.weather || {};
                const statusColor = weatherColor(wx.status);
                const wind = wx.wind_speed_mph;
                return (
                  <CircleMarker
                    key={`grid-${idx}`}
                    center={[pt.lat, pt.lon]}
                    radius={gridRadiusFromWind(wind)}
                    pathOptions={{ color: statusColor, fillColor: statusColor, fillOpacity: 0.35, weight: 1 }}
                  >
                    <Tooltip direction="top" offset={[0, -8]} opacity={0.95} sticky>
                      <b>Weather Grid Point</b><br />
                      Lat: {pt.lat.toFixed(3)}<br />
                      Lon: {pt.lon.toFixed(3)}<br />
                      Time: {wx.forecast_time ?? "N/A"}<br />
                      Status: {wx.status ?? "unknown"}<br />
                      Wind: {wx.wind_speed_mph ?? "N/A"} mph<br />
                      Gusts: {wx.wind_gusts_mph ?? "N/A"} mph<br />
                      Precip: {wx.precipitation_mm ?? "N/A"} mm
                    </Tooltip>
                  </CircleMarker>
                );
              })}

            {/* ── Population density grid ── */}
            {showPopulation &&
              populationGrid.map((pt, idx) => {
                const color = populationColor(pt.status);
                if (!color) return null; // skip "minimal" cells

                const r = populationRadius(pt.status);
                return (
                  <CircleMarker
                    key={`pop-${idx}`}
                    center={[pt.lat, pt.lon]}
                    radius={r}
                    pathOptions={{
                      color,
                      fillColor: color,
                      fillOpacity: 0.45,
                      weight: 0,
                    }}
                  >
                    <Tooltip direction="top" offset={[0, -8]} opacity={0.95} sticky>
                      <b>Population Density</b><br />
                      Density tier: {pt.status}<br />
                      Ambient pop / cell: {pt.population.toLocaleString()}<br />
                      Source: LandScan USA 2021
                    </Tooltip>
                  </CircleMarker>
                );
              })}

            {/* ── Hazard polygons ── */}
            {showHazardRegions &&
              buildHazardPolygons(weatherGrid).map((poly, idx) => (
                <Polygon
                  key={`hazard-poly-${idx}`}
                  positions={poly}
                  pathOptions={{ color: "red", fillColor: "red", fillOpacity: 0.12, weight: 2 }}
                >
                  <Popup><b>Hazard Region</b><br />Merged unsafe-weather influence region.</Popup>
                </Polygon>
              ))}

            {/* ── Airspace ── */}
            {showAirspace &&
              airspaceGeojson?.features?.map((feature, idx) => {
                const geom = feature.geometry;
                const props = feature.properties || {};

                const popupText = (
                  <Tooltip direction="top" offset={[0, -8]} opacity={0.95} sticky>
                    <b>
                      {String(
                        props.name ?? props.NAME ?? props.airspace_type ?? props.AIRSPACE_TYPE ??
                        props.level ?? props.LEVEL ?? props.type ?? props.TYPE ??
                        props.class ?? props.CLASS ?? "Airspace"
                      )}
                    </b><br />
                    Level: {props.level ?? props.LEVEL ?? props.airspace_class ?? props.class ?? props.type ?? "N/A"}<br />
                    Lower: {props.lower_limit ?? props.lower ?? props.floor ?? props.base ?? "N/A"}<br />
                    Upper: {props.upper_limit ?? props.upper ?? props.ceiling ?? props.top ?? "N/A"}
                  </Tooltip>
                );

                if (geom.type === "Polygon") {
                  const positions = geom.coordinates.map((ring) =>
                    ring.map(([lon, lat]) => [lat, lon])
                  );
                  return (
                    <Polygon key={`airspace-poly-${idx}`} positions={positions} pathOptions={airspaceStyle(feature)}>
                      {popupText}
                    </Polygon>
                  );
                }

                if (geom.type === "MultiPolygon") {
                  return geom.coordinates.map((poly, polyIdx) => {
                    const positions = poly.map((ring) => ring.map(([lon, lat]) => [lat, lon]));
                    return (
                      <Polygon key={`airspace-mpoly-${idx}-${polyIdx}`} positions={positions} pathOptions={airspaceStyle(feature)}>
                        {popupText}
                      </Polygon>
                    );
                  });
                }

                return null;
              })}

            {/* ── Node markers ── */}
            {nodes.map((node) => {
              const isStart = node.id === selectedStart;
              const isEnd = node.id === selectedEnd;
              const wx = weather[node.id];
              const wxColor = weatherColor(wx?.status);

              return (
                <div key={node.id}>
                  <Marker
                    position={[node.lat, node.lon]}
                    eventHandlers={{ click: () => handleNodeSelect(node.id) }}
                  >
                    <Tooltip direction="top" offset={[0, -8]} opacity={0.95} sticky>
                      <b>{node.id}</b><br />
                      {node.name}<br />
                      Type: {node.type}<br /><br />
                      <b>Weather</b><br />
                      Status: {wx?.status ?? "loading"}<br />
                      Wind: {wx?.wind_speed_mph ?? "N/A"} mph<br />
                      Gusts: {wx?.wind_gusts_mph ?? "N/A"} mph<br />
                      Visibility: {formatVisibilityMiles(wx?.visibility_m)} mi<br />
                      Precip: {wx?.precipitation_mm ?? "N/A"} mm
                    </Tooltip>
                  </Marker>

                  <CircleMarker
                    center={[node.lat, node.lon]}
                    radius={9}
                    pathOptions={{ color: wxColor, weight: 3, fillOpacity: 0 }}
                  />

                  {(isStart || isEnd) && (
                    <CircleMarker
                      center={[node.lat, node.lon]}
                      radius={14}
                      pathOptions={{ color: isStart ? "green" : "red", weight: 3, fillOpacity: 0 }}
                    />
                  )}
                </div>
              );
            })}
          </MapContainer>

          {isPreloading && (
            <div
              style={{
                position: "absolute", inset: 0, background: "rgba(0,0,0,0.45)",
                display: "flex", alignItems: "center", justifyContent: "center",
                zIndex: 1000, color: "white", fontSize: "28px", fontWeight: "bold",
                letterSpacing: "0.5px", pointerEvents: "all",
              }}
            >
              Pre-caching data...
            </div>
          )}

          {isRouting && (
            <div
              style={{
                position: "absolute", bottom: 16, left: "50%", transform: "translateX(-50%)",
                background: "rgba(10,45,99,0.92)", color: "white", padding: "10px 20px",
                borderRadius: "10px", zIndex: 999, fontWeight: "bold", fontSize: "14px",
              }}
            >
              Computing route...
            </div>
          )}

          {error && (
            <div
              style={{
                position: "absolute", bottom: 16, left: "50%", transform: "translateX(-50%)",
                background: "rgba(180,30,30,0.92)", color: "white", padding: "10px 20px",
                borderRadius: "10px", zIndex: 999, fontWeight: "bold", fontSize: "14px",
              }}
            >
              {error}
            </div>
          )}
        </div>

        <RightPanel
          selectedType={selectedType}
          selectedNode={selectedNode}
          routeData={routeData}
          selectedFlight={selectedFlight}
          weather={weather}
        />
      </div>

      <BottomToolbar
        initialize={handleInitialize}
        isPreloading={isPreloading}
        selectedDate={selectedDate}
        setSelectedDate={setSelectedDate}
        startHour={startHour}
        setStartHour={setStartHour}
        endHour={endHour}
        setEndHour={setEndHour}
        currentTimeMinutes={currentTimeMinutes}
        setCurrentTimeMinutes={setCurrentTimeMinutes}
        showWeather={showWeather}
        setShowWeather={setShowWeather}
        showPopulation={showPopulation}
        setShowPopulation={setShowPopulation}
        showFlights={showFlights}
        setShowFlights={setShowFlights}
        showHazardRegions={showHazardRegions}
        setShowHazardRegions={setShowHazardRegions}
        // Sim clock controls
        isPlaying={isPlaying}
        setIsPlaying={handleSetPlaying}
        simSpeed={simSpeed}
        setSimSpeed={handleSetSimSpeed}
      />
    </div>
  );
}

export default App;