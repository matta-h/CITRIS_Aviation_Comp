import { useEffect, useMemo, useState } from "react";
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

  const rawName =
    props.name ??
    props.NAME ??
    props.title ??
    props.TITLE ??
    "";

  const rawType =
    props.type ??
    props.TYPE ??
    props.class ??
    props.CLASS ??
    props.category ??
    props.CATEGORY ??
    props.airspace_type ??
    props.AIRSPACE_TYPE ??
    "";

  const rawLevel =
    props.level ??
    props.LEVEL ??
    props.airspace_class ??
    props.AIRSPACE_CLASS ??
    "";

  const name = String(rawName).trim().toUpperCase();
  const type = String(rawType).trim().toUpperCase();
  const level = String(rawLevel).trim().toUpperCase();
  const text = `${name} ${level} ${type}`.trim();

  let color = "green";

  // special-use first
  if (text.includes("PROHIBITED") || type === "P") color = "purple";
  else if (text.includes("RESTRICTED") || type === "R") color = "red";
  else if (text.includes("DANGER") || type === "D") color = "orange";

  // standard classes
  else if (text.includes("CLASS B")) color = "red";
  else if (text.includes("CLASS C")) color = "orange";
  else if (text.includes("CLASS D")) color = "blue";
  else if (text.includes("CLASS E")) color = "gold";
  else if (text.includes("E2")) color = "gold";
  else if (text.includes("E3")) color = "gold";
  else if (text.includes("E4")) color = "gold";
  else if (text.includes("CLASS G")) color = "green";
  else if (type === "B") color = "red";
  else if (type === "C") color = "orange";
  else if (type === "D") color = "blue";
  else if (type.startsWith("E")) color = "gold";
  else if (type === "G") color = "green";

  return {
    color,
    fillColor: color,
    fillOpacity: 0.15,
    weight: 2,
  };
}

function App() {
  const [airspaceGeojson, setAirspaceGeojson] = useState(null);
  const [airspaceSource, setAirspaceSource] = useState("openair");
  const [showAirspace, setShowAirspace] = useState(true);
  const [nodes, setNodes] = useState([]);
  const [selectedStart, setSelectedStart] = useState(null);
  const [selectedEnd, setSelectedEnd] = useState(null);
  const [pendingStart, setPendingStart] = useState("");
  const [pendingEnd, setPendingEnd] = useState("");
  const [activeFlights, setActiveFlights] = useState([]);
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
  const [showHazardRegions, setShowHazardRegions] = useState(true);
  const [showGridPoints, setShowGridPoints] = useState(true);
  const [selectedType, setSelectedType] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedDate, setSelectedDate] = useState("2024-01-15");
  const [startHour, setStartHour] = useState(6);
  const [endHour, setEndHour] = useState(22);
  const [currentHour, setCurrentHour] = useState(8);
  /*   const [usePreloadedWeather, setUsePreloadedWeather] = useState(false); */
  const [isPreloading, setIsPreloading] = useState(false);

  const [showWeather, setShowWeather] = useState(true);
  const [showPopulation, setShowPopulation] = useState(false);
  const [showFlights, setShowFlights] = useState(true);
  const handleInitialize = () => {
    if (!selectedDate) return;

    setIsPreloading(true);

    fetch("http://127.0.0.1:8000/weather-grid-day-preload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        date: selectedDate,
        start_hour: startHour,
        end_hour: endHour,
      }),
    })
      .then((res) => {
        if (!res.ok) {
          throw new Error("Pre-cache failed");
        }
        return res.json();
      })
      .then(() => {
        const initialIso = `${selectedDate}T${String(startHour).padStart(2, "0")}:00`;
        setCurrentHour(startHour);
        setRequestedGridTime(initialIso);
      })
      .catch((err) => {
        console.warn("Preload failed", err);
      })
      .finally(() => {
        setIsPreloading(false);
      });
  };

  useEffect(() => {
    // 🔥 set backend source first
    fetch(`http://127.0.0.1:8000/set-airspace-source?source=${airspaceSource}`)
      .then(() => {
        return fetch("http://127.0.0.1:8000/airspace-geojson");
      })
      .then((res) => res.json())
      .then((data) => {
        console.log("airspace-geojson:", data);
        console.log("first airspace properties:", data?.features?.[0]?.properties);
        setAirspaceGeojson(data);
      })
      .catch(() => {
        console.warn("Failed to load airspace geojson.");
        setAirspaceGeojson(null);
      });
  }, [airspaceSource]);
  useEffect(() => {
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

    /* fetch("http://127.0.0.1:8000/weather")
      .then((res) => res.json())
      .then((data) => {
        setWeather(data ?? {});
      })
      .catch(() => {
        console.warn("Failed to load weather.");
        setWeather({});
      }); */

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
        const newFlight = {
          id: `flight-${Date.now()}`,
          start: selectedStart,
          end: selectedEnd,
          routeData: data,
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
            data?.estimated_time_min != null
              ? `${Math.round(data.estimated_time_min)} min`
              : data?.score != null
                ? `${Math.round(data.score)} min`
                : "—",
        };

        setRouteData(data);
        setSelectedType("flight");
        setSelectedNode(null);
        setActiveFlights((prev) => [newFlight, ...prev]);
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
    const iso = `${selectedDate}T${String(currentHour).padStart(2, "0")}:00`;
    setRequestedGridTime(iso);
  }, [currentHour, selectedDate]);

  useEffect(() => {
    const effectiveWeatherTime = requestedGridTime ?? gridTime;

    fetch(`http://127.0.0.1:8000/weather?target_time=${encodeURIComponent(effectiveWeatherTime)}`)
      .then((res) => res.json())
      .then((data) => {
        setWeather(data ?? {});
      })
      .catch(() => {
        console.warn("Failed to load weather.");
        setWeather({});
      });
  }, [gridTime, requestedGridTime]);

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
    const node = nodeMap[nodeId] || null;
    setSelectedType("port");
    setSelectedNode(node);
  };

  /*   const handleNodeSelect = (nodeId) => {
      const node = nodeMap[nodeId] || null;
      setSelectedType("port");
      setSelectedNode(node);
  
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
    }; */

  const handleCreateFlight = () => {
    if (!pendingStart || !pendingEnd || pendingStart === pendingEnd) return;

    setSelectedStart(pendingStart);
    setSelectedEnd(pendingEnd);
    setPendingStart("");
    setPendingEnd("");
    setError("");
  };

  const handleSelectFlight = (flight) => {
    setSelectedType("flight");
    setSelectedNode(null);
    setRouteData(flight.routeData || null);
  };

  const handleDeleteFlight = (flightId) => {
    setActiveFlights((prev) => prev.filter((flight) => flight.id !== flightId));
  };

  const clearSelection = () => {
    setSelectedStart(null);
    setSelectedEnd(null);
    setRouteData(null);
    setError("");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", width: "100%" }}>
      <div style={{ display: "flex", flex: 1 }}>
        <LeftPanel
          nodes={nodes}
          activeFlights={activeFlights}
          pendingStart={pendingStart}
          pendingEnd={pendingEnd}
          setPendingStart={setPendingStart}
          setPendingEnd={setPendingEnd}
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
                    <Tooltip direction="top" offset={[0, -8]} opacity={0.95} sticky>
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
                    </Tooltip>
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
                  <Tooltip direction="top" offset={[0, -8]} opacity={0.95} sticky>
                    <b>
                      {String(
                        props.name ??
                        props.NAME ??
                        props.airspace_type ??
                        props.AIRSPACE_TYPE ??
                        props.level ??
                        props.LEVEL ??
                        props.type ??
                        props.TYPE ??
                        props.class ??
                        props.CLASS ??
                        "Airspace"
                      )}
                    </b>
                    <br />
                    Level: {
                      props.level
                      ?? props.LEVEL
                      ?? props.airspace_class
                      ?? props.AIRSPACE_CLASS
                      ?? props.class
                      ?? props.CLASS
                      ?? props.type
                      ?? props.TYPE
                      ?? "N/A"
                    }
                    <br />
                    Lower: {
                      props.lower_limit
                      ?? props.lower
                      ?? props.LOWER
                      ?? props.floor
                      ?? props.FLOOR
                      ?? props.base
                      ?? props.BASE
                      ?? "N/A"
                    }
                    <br />
                    Upper: {
                      props.upper_limit
                      ?? props.upper
                      ?? props.UPPER
                      ?? props.ceiling
                      ?? props.CEILING
                      ?? props.top
                      ?? props.TOP
                      ?? "N/A"
                    }
                  </Tooltip>
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
                    <Tooltip direction="top" offset={[0, -8]} opacity={0.95} sticky>
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
                    </Tooltip>
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

          {isPreloading && (
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: "rgba(0,0,0,0.45)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 1000,
                color: "white",
                fontSize: "28px",
                fontWeight: "bold",
                letterSpacing: "0.5px",
                pointerEvents: "all",
              }}
            >
              Pre-caching data...
            </div>
          )}
        </div>
        <RightPanel
          selectedType={selectedType}
          selectedNode={selectedNode}
          routeData={routeData}
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
        currentHour={currentHour}
        setCurrentHour={setCurrentHour}
        showWeather={showWeather}
        setShowWeather={setShowWeather}
        showPopulation={showPopulation}
        setShowPopulation={setShowPopulation}
        showFlights={showFlights}
        setShowFlights={setShowFlights}
        showHazardRegions={showHazardRegions}
        setShowHazardRegions={setShowHazardRegions}
      />
    </div>
  );
}

export default App;