import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  CircleMarker,
  Circle,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet-defaulticon-compatibility";
import "leaflet-defaulticon-compatibility/dist/leaflet-defaulticon-compatibility.css";

function milesToMeters(miles) {
  return miles * 1609.34;
}

function routeColor(routeClass) {
  if (routeClass === "green") return "green";
  if (routeClass === "yellow") return "gold";
  if (routeClass === "orange") return "orange";
  return "red";
}

function App() {
  const [nodes, setNodes] = useState([]);
  const [selectedStart, setSelectedStart] = useState(null);
  const [selectedEnd, setSelectedEnd] = useState(null);
  const [routeData, setRouteData] = useState(null);
  const [error, setError] = useState("");
  const [obstacles, setObstacles] = useState({
    no_fly_zones: [],
    slow_zones: [],
  });

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

    const url = `http://127.0.0.1:8000/route?start=${selectedStart}&end=${selectedEnd}`;

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
      })
      .catch((err) => {
        setRouteData(null);
        setError(err.message || "Failed to fetch route.");
      });
  }, [selectedStart, selectedEnd]);

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

        return {
          positions: [
            [fromNode.lat, fromNode.lon],
            [toNode.lat, toNode.lon],
          ],
          routeClass: leg.route_class,
          from: leg.from,
          to: leg.to,
          distance: leg.distance_miles,
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

          {obstacles.no_fly_zones.map((zone, idx) => (
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

          {obstacles.slow_zones.map((zone, idx) => (
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

          {nodes.map((node) => {
            const isStart = node.id === selectedStart;
            const isEnd = node.id === selectedEnd;

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
                  </Popup>
                </Marker>

                {(isStart || isEnd) && (
                  <CircleMarker
                    center={[node.lat, node.lon]}
                    radius={12}
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

          {routeSegments.map((segment, idx) => (
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
              </Popup>
            </Polyline>
          ))}
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
          <strong>Legend</strong>
          <div style={{ color: "green" }}>Green = preferred</div>
          <div style={{ color: "goldenrod" }}>Yellow = acceptable</div>
          <div style={{ color: "orange" }}>Orange = less preferred</div>
          <div style={{ color: "red" }}>Red circle = no-fly zone</div>
        </div>

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
                </li>
              ))}
            </ul>
          </div>
        )}

        {!routeData && !error && <p>No route selected yet.</p>}
      </div>
    </div>
  );
}

export default App;