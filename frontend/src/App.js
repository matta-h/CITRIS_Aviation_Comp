import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  CircleMarker,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet-defaulticon-compatibility";
import "leaflet-defaulticon-compatibility/dist/leaflet-defaulticon-compatibility.css";

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

  useEffect(() => {
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

    // If both already selected, restart selection with new start
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
        <MapContainer center={[37.5, -121.5]} zoom={7} style={{ height: "100%", width: "100%" }}>
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

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
            />
          ))}
        </MapContainer>
      </div>

      <div
        style={{
          width: "340px",
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
            </p>

            <h4>Legs</h4>
            <ul style={{ paddingLeft: "18px" }}>
              {routeData.legs.map((leg, idx) => (
                <li key={idx} style={{ marginBottom: "8px" }}>
                  <strong>{leg.from} → {leg.to}</strong>
                  <br />
                  {leg.distance_miles} mi, {leg.route_class}
                </li>
              ))}
            </ul>
          </div>
        )}

        {!routeData && !error && (
          <p>No route selected yet.</p>
        )}
      </div>
    </div>
  );
}

export default App;