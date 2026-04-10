import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  CircleMarker,
  Circle,
  Polygon
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet-defaulticon-compatibility";
import "leaflet-defaulticon-compatibility/dist/leaflet-defaulticon-compatibility.css";
import { point, featureCollection, buffer, union } from "@turf/turf";

function milesToMeters(miles) {
  return miles * 1609.34;
}

function routeColor(routeClass) {
  if (routeClass === "green") return "green";
  if (routeClass === "yellow") return "gold";
  if (routeClass === "orange") return "orange";
  if (routeClass === "detour") return "deepskyblue";
  if (routeClass === "field") return "blue"; // or green, your choice
  return "red";
}

function weatherColor(status) {
  if (status === "good") return "green";
  if (status === "caution") return "gold";
  if (status === "unsafe") return "red";
  return "gray";
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

function hazardFillColor(status) {
  if (status === "unsafe") return "red";
  if (status === "caution") return "orange";
  return null;
}

function gridCellRadiusMeters() {
  return 16000; // about 10 miles
}

function buildHazardPolygons(points) {
  const unsafePoints = points.filter((p) => p.weather?.status === "unsafe");

  if (unsafePoints.length === 0) return [];

  // Each grid point represents a local area, not just a single exact point.
  // Your grid spacing is about 0.2 degrees, so using about half that spacing
  // as the radius gives each hazard point an area of influence.
  const radiusKm = 11; // ~6.8 miles, roughly half the grid spacing

  const bufferedFeatures = unsafePoints.map((p) => {
    const pt = point([p.lon, p.lat]);
    return buffer(pt, radiusKm, { units: "kilometers" });
  });

  if (bufferedFeatures.length === 0) return [];

  let merged = bufferedFeatures[0];

  for (let i = 1; i < bufferedFeatures.length; i++) {
    try {
      const mergedResult = union(featureCollection([merged, bufferedFeatures[i]]));
      if (mergedResult) {
        merged = mergedResult;
      }
    } catch (err) {
      console.warn("Union failed for hazard polygon merge:", err);
    }
  }

  if (!merged || !merged.geometry) return [];

  if (merged.geometry.type === "Polygon") {
    return [
      merged.geometry.coordinates[0].map(([lon, lat]) => [lat, lon])
    ];
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
  const text = `${props.level || ""} ${props.airspace_type || ""} ${props.type || ""}`.toUpperCase();

  let color = "green";
  if (text.includes("CLASS B") || text.trim() === "B") color = "red";
  else if (text.includes("CLASS C") || text.trim() === "C") color = "orange";
  else if (text.includes("CLASS D") || text.trim() === "D") color = "blue";
  else if (text.includes("CLASS G") || text.trim() === "G") color = "green";

  return {
    color,
    fillColor: color,
    fillOpacity: 0.08,
    weight: 2,
  };
}

function App() {
  const [airspaceGeojson, setAirspaceGeojson] = useState(null);
  const [airspaceOverlays, setAirspaceOverlays] = useState([null]);
  const [showAirspace, setShowAirspace] = useState(true);
  const [nodes, setNodes] = useState([]);
  const [selectedStart, setSelectedStart] = useState(null);
  const [selectedEnd, setSelectedEnd] = useState(null);
  const [routeData, setRouteData] = useState(null);
  const [error, setError] = useState("");
  const [isRouting, setIsRouting] = useState(false);
  const [weather, setWeather] = useState({});
  const [obstacles, setObstacles] = useState({
    no_fly_zones: [],
    slow_zones: [],
  });
  const [weatherGrid, setWeatherGrid] = useState([]);
  const [gridTime, setGridTime] = useState("2024-01-15T08:00");
  const [requestedGridTime, setRequestedGridTime] = useState(null);
  const [showWeatherGrid] = useState(true);
  const [showHazardRegions, setShowHazardRegions] = useState(false);
  const [showGridPoints, setShowGridPoints] = useState(true);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/airspace-geojson")
      .then((res) => res.json())
      .then((data) => {
        console.log("airspace-geojson:", data);
        setAirspaceGeojson(data);
      })
      .catch(() => {
        console.warn("Failed to load airspace geojson.");
        setAirspaceGeojson(null);
      });
    fetch("http://127.0.0.1:8000/obstacles")
      .then((res) => res.json())
      .then((data) => {
        setObstacles({
          no_fly_zones: data?.no_fly_zones ?? [],
          slow_zones: data?.slow_zones ?? [],
        });
      })
      .catch(() => {
        console.warn("Failed to load obstacles.");
        setObstacles({
          no_fly_zones: [],
          slow_zones: [],
        });
      });

    fetch("http://127.0.0.1:8000/weather")
      .then((res) => res.json())
      .then((data) => {
        setWeather(data ?? {});
      })
      .catch(() => {
        console.warn("Failed to load weather.");
        setWeather({});
      });

    fetch("http://127.0.0.1:8000/nodes")
      .then((res) => res.json())
      .then((data) => {
        const nodeArray = Object.entries(data).map(([id, val]) => ({
          id,
          ...val,
        }));
        setNodes(nodeArray);
      })
      .catch(() => {
        setError("Failed to load nodes from backend.");
      });
  }, []);

  useEffect(() => {
    if (!selectedStart || !selectedEnd) {
      setRouteData(null);
      return;
    }

    const effectiveRouteTime = requestedGridTime ?? gridTime;
    const url = `http://127.0.0.1:8000/route?start=${selectedStart}&end=${selectedEnd}&departure_time=${encodeURIComponent(effectiveRouteTime)}`;
    
    setIsRouting(true);
    setError("");

    fetch(url)
      .then((res) => {
        if (!res.ok) {
          throw new Error("No feasible route found.");
        }
        return res.json();
      })
      .then((data) => {
        setRouteData(data);
        setError("");
        setIsRouting(false);
      })
      .catch((err) => {
        setRouteData(null);
        setError(err.message || "Failed to fetch route.");
        setIsRouting(false);
      });
  }, [selectedStart, selectedEnd, requestedGridTime]);

  useEffect(() => {
    if (!showWeatherGrid || !requestedGridTime) {
      return;
    }

    fetch(`http://127.0.0.1:8000/weather-grid?target_time=${encodeURIComponent(requestedGridTime)}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error("Weather fetch failed");
        }
        return res.json();
      })
      .then((data) => {
        setWeatherGrid(Array.isArray(data) ? data : []);
      })
      .catch(() => {
        console.warn("Failed to load weather grid.");
        setWeatherGrid([]);
      });
  }, [requestedGridTime, showWeatherGrid]);

  const nodeMap = useMemo(() => {
    const map = {};
    nodes.forEach((node) => {
      map[node.id] = node;
    });
    return map;
  }, [nodes]);

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
            if (p?.lat != null && p?.lon != null) {
              positions.push([p.lat, p.lon]);
            }
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

  const handleNodeSelect = (nodeId) => {
    if (!selectedStart) {
      setSelectedStart(nodeId);
      setSelectedEnd(null);
      setRouteData(null);
      setError("");
      return;
    }

    if (!selectedEnd) {
      if (nodeId === selectedStart) return;
      setSelectedEnd(nodeId);
      return;
    }

    setSelectedStart(nodeId);
    setSelectedEnd(null);
    setRouteData(null);
    setError("");
  };

  const clearSelection = () => {
    setSelectedStart(null);
    setSelectedEnd(null);
    setRouteData(null);
    setError("");
  };

  return (
    <div style={{ display: "flex", height: "100vh", width: "100%" }}>
      <div style={{ flex: 1 }}>
        <MapContainer
          center={[37.5, -121.5]}
          zoom={7}
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

          {(obstacles?.no_fly_zones ?? []).map((zone, idx) => (
            <Circle
              key={`nfz-${idx}`}
              center={[zone.lat, zone.lon]}
              radius={milesToMeters(zone.radius_miles)}
              pathOptions={{
                color: "red",
                fillColor: "red",
                fillOpacity: 0.2,
                weight: 2,
              }}
            >
              <Popup>
                <b>{zone.name}</b>
                <br />
                No-fly zone
              </Popup>
            </Circle>
          ))}

          {(obstacles?.slow_zones ?? []).map((zone, idx) => (
            <Circle
              key={`slow-${idx}`}
              center={[zone.lat, zone.lon]}
              radius={milesToMeters(zone.radius_miles)}
              pathOptions={{
                color: "orange",
                fillColor: "yellow",
                fillOpacity: 0.15,
                weight: 2,
              }}
            >
              <Popup>
                <b>{zone.name}</b>
                <br />
                Slow / caution zone
                <br />
                Penalty: {zone.penalty}
              </Popup>
            </Circle>
          ))}

          {showGridPoints &&
            weatherGrid.map((point, idx) => {
              const wx = point.weather || {};
              const statusColor = weatherColor(wx.status);
              const wind = wx.wind_speed_mph;

              return (
                <CircleMarker
                  key={`grid-${idx}`}
                  center={[point.lat, point.lon]}
                  radius={gridRadiusFromWind(wind)}
                  pathOptions={{
                    color: statusColor,
                    fillColor: statusColor,
                    fillOpacity: 0.35,
                    weight: 1,
                  }}
                >
                  <Popup>
                    <b>Weather Grid Point</b>
                    <br />
                    Lat: {point.lat.toFixed(3)}
                    <br />
                    Lon: {point.lon.toFixed(3)}
                    <br />
                    Time: {wx.forecast_time ?? "N/A"}
                    <br />
                    Status: {wx.status ?? "unknown"}
                    <br />
                    Wind: {wx.wind_speed_mph ?? "N/A"} mph
                    <br />
                    Gusts: {wx.wind_gusts_mph ?? "N/A"} mph
                    <br />
                    Precip: {wx.precipitation_mm ?? "N/A"} mm
                  </Popup>
                </CircleMarker>
              );
            })}

          {showHazardRegions && 
            buildHazardPolygons(weatherGrid).map((poly, idx) => (
              <Polygon
                key={`hazard-poly-${idx}`}
                positions={poly}
                pathOptions={{
                  color: "red",
                  fillColor: "red",
                  fillOpacity: 0.12,
                  weight: 2,
                }}
              >
                <Popup>
                  <b>Hazard Region</b>
                  <br />
                  Merged unsafe-weather influence region.
                </Popup>
              </Polygon>
            ))}
            {showAirspace &&
              airspaceGeojson?.features?.map((feature, idx) => {
                const geom = feature.geometry;
                const props = feature.properties || {};

                const popupText = (
                  <Popup>
                    <b>{props.airspace_type || props.level || "Airspace"}</b>
                    <br />
                    Level: {props.level ?? "N/A"}
                    <br />
                    Lower: {props.lower_limit ?? "N/A"} {props.lower_limit_reference ?? ""}
                    <br />
                    Upper: {props.upper_limit ?? "N/A"} {props.upper_limit_reference ?? ""}
                  </Popup>
                );

                if (geom.type === "Polygon") {
                  const positions = geom.coordinates.map((ring) =>
                    ring.map(([lon, lat]) => [lat, lon])
                  );

                  return (
                    <Polygon
                      key={`airspace-poly-${idx}`}
                      positions={positions}
                      pathOptions={airspaceStyle(feature)}
                    >
                      {popupText}
                    </Polygon>
                  );
                }

                if (geom.type === "MultiPolygon") {
                  return geom.coordinates.map((poly, polyIdx) => {
                    const positions = poly.map((ring) =>
                      ring.map(([lon, lat]) => [lat, lon])
                    );

                    return (
                      <Polygon
                        key={`airspace-mpoly-${idx}-${polyIdx}`}
                        positions={positions}
                        pathOptions={airspaceStyle(feature)}
                      >
                        {popupText}
                      </Polygon>
                    );
                  });
                }

                return null;
              })}
            
                    {nodes.map((node) => {
            const isStart = node.id === selectedStart;
            const isEnd = node.id === selectedEnd;

            const wx = weather[node.id];
            const wxColor = weatherColor(wx?.status);


            
            return (
              <div key={node.id}>
                <Marker
                  position={[node.lat, node.lon]}
                  eventHandlers={{
                    click: () => handleNodeSelect(node.id),
                  }}
                >
                  <Popup>
                    <b>{node.id}</b>
                    <br />
                    {node.name}
                    <br />
                    Type: {node.type}
                    <br />
                    <br />
                    <b>Weather</b>
                    <br />
                    Status: {wx?.status ?? "loading"}
                    <br />
                    Wind: {wx?.wind_speed_mph ?? "N/A"} mph
                    <br />
                    Gusts: {wx?.wind_gusts_mph ?? "N/A"} mph
                    <br />
                    Visibility: {formatVisibilityMiles(wx?.visibility_m)} mi
                    <br />
                    Precip: {wx?.precipitation_mm ?? "N/A"} mm
                  </Popup>
                </Marker>

                <CircleMarker
                  center={[node.lat, node.lon]}
                  radius={9}
                  pathOptions={{
                    color: wxColor,
                    weight: 3,
                    fillOpacity: 0,
                  }}
                />

                {(isStart || isEnd) && (
                  <CircleMarker
                    center={[node.lat, node.lon]}
                    radius={14}
                    pathOptions={{
                      color: isStart ? "green" : "red",
                      weight: 3,
                      fillOpacity: 0,
                    }}
                  />
                )}
              </div>
            );
          })}
          {routeData?.raw_polyline && routeData.raw_polyline.length > 1 && (
            <Polyline
              positions={routeData.raw_polyline}
              pathOptions={{
                color: "gray",
                weight: 2,
                opacity: 0.75,
                dashArray: "6,8",
              }}
            />
          )}
          {routeData?.polyline && routeData.polyline.length > 1 && (
            <Polyline
              positions={routeData.polyline}
              pathOptions={{
                color: "blue",
                weight: 5,
                opacity: 0.5,
              }}
            >
              <Popup>
                <b>Field Route</b>
                <br />
                Continuous path (field-based routing)
              </Popup>
            </Polyline>
          )}

{/*           {routeSegments.map((segment, idx) => (
            <Polyline
              key={idx}
              positions={segment.positions}
              pathOptions={{
                color: routeColor(segment.routeClass),
                weight: 5,
              }}
            >
              <Popup>
                <b>
                  {segment.from} → {segment.to}
                </b>
                <br />
                {segment.distance} mi
                <br />
                {segment.routeClass}
                <br />
                Detour points: {segment.viaCount}
              </Popup>
            </Polyline>
          ))} */}
        </MapContainer>
      </div>

      <div
        style={{
          width: "360px",
          padding: "16px",
          borderLeft: "1px solid #ccc",
          background: "#f7f7f7",
          overflowY: "auto",
          fontFamily: "Arial, sans-serif",
        }}
      >
        <h2 style={{ marginTop: 0 }}>CITRIS Routing Panel</h2>

        <p>
          <strong>Instructions:</strong>
          <br />
          Click one node for the start, then another for the destination.
        </p>

        <p>
          <strong>Start:</strong> {selectedStart || "None"}
          <br />
          <strong>End:</strong> {selectedEnd || "None"}
        </p>

        <button onClick={clearSelection} style={{ marginBottom: "16px" }}>
          Clear Selection
        </button>

        <div style={{ marginBottom: "16px" }}>
          <strong>Weather Overlay</strong>
          <br />

          <label style={{ display: "block", marginTop: "8px" }}>
            <input
              type="checkbox"
              checked={showGridPoints}
              onChange={(e) => setShowGridPoints(e.target.checked)}
              style={{ marginRight: "8px" }}
            />
            Show grid points
          </label>

          <label style={{ display: "block", marginTop: "8px" }}>
            <input
              type="checkbox"
              checked={showHazardRegions}
              onChange={(e) => setShowHazardRegions(e.target.checked)}
              style={{ marginRight: "8px" }}
            />
            Show hazard regions
          </label>

          <label style={{ display: "block", marginTop: "10px" }}>
            Replay time:
            <input
              type="datetime-local"
              value={gridTime}
              onChange={(e) => setGridTime(e.target.value)}
              style={{
                display: "block",
                marginTop: "6px",
                width: "100%",
                padding: "6px",
              }}
            />
          </label>
          <label style={{ display: "block", marginTop: "8px" }}>
            <input
              type="checkbox"
              checked={showAirspace}
              onChange={(e) => setShowAirspace(e.target.checked)}
              style={{ marginRight: "8px" }}
            />
            Show airspace
          </label>
          <button
            onClick={() => {
            //  if (preloadStatus?.status !== "complete") {
            //    alert("Please initialize simulation first.");
            //    return;
            //  }
              setRequestedGridTime(gridTime);
            }}
            style={{
              marginTop: "8px",
              width: "100%",
              padding: "8px",
              fontWeight: "bold",
            }}
          >
            Load Weather for This Time
          </button>
        </div>

        <div style={{ marginBottom: "16px" }}>
          <strong>Legend</strong>
          <div style={{ color: "green" }}>Green = preferred</div>
          <div style={{ color: "goldenrod" }}>Yellow = acceptable</div>
          <div style={{ color: "orange" }}>Orange = less preferred</div>
          <div style={{ color: "deepskyblue" }}>Blue = detour segment</div>
          <div style={{ color: "red" }}>Red circle = no-fly zone</div>
        </div>

        {isRouting && (
          <div
            style={{
              marginBottom: "16px",
              padding: "12px",
              borderRadius: "8px",
              background: "#e8f1ff",
              border: "1px solid #b8cffc",
              color: "#1f4ea3",
            }}
          >
            <strong>Calculating route...</strong>
            <br />
            Checking feasibility, weather, and routing cost.
          </div>
        )}

        {error && (
          <div style={{ color: "darkred", marginBottom: "16px" }}>
            <strong>Error:</strong> {error}
          </div>
        )}

        {routeData && (
          <div>
            <h3>Route Result</h3>
            <p>
              <strong>Path:</strong> {routeData.path.join(" → ")}
            </p>
            <p>
              <strong>Total Distance:</strong> {routeData.total_distance_miles} mi
              <br />
              <strong>Total Cost:</strong> {routeData.total_cost}
              <br />
              <strong>Legs:</strong> {routeData.num_legs}
            </p>

            <h4>Legs</h4>
            <ul style={{ paddingLeft: "18px" }}>
              {routeData.legs.map((leg, idx) => (
                <li key={idx} style={{ marginBottom: "10px" }}>
                  <strong>
                    {leg.from} → {leg.to}
                  </strong>
                  <br />
                  {leg.distance_miles} mi
                  <br />
                  <span style={{ color: routeColor(leg.route_class) }}>
                    {leg.route_class}
                  </span>
                  {Array.isArray(leg.via) && leg.via.length > 0 && (
                    <>
                      <br />
                      via {leg.via.length} detour point(s)
                    </>
                  )}
                  {Array.isArray(leg.hazards) && leg.hazards.length > 0 && (
                    <>
                      <br />
                      Hazards:
                      <ul style={{ marginTop: "4px", paddingLeft: "18px" }}>
                        {leg.hazards.map((hz, hzIdx) => (
                          <li key={hzIdx}>
                            {hz.name} ({hz.type}, {hz.mode})
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {!routeData && !error && !isRouting && <p>No route selected yet.</p>}
      </div>
    </div>
  );
}

export default App;