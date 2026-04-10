import React from "react";

const Row = ({ label, value }) => (
  <div
    style={{
      display: "flex",
      justifyContent: "space-between",
      padding: "6px 0",
      borderBottom: "1px solid rgba(255,255,255,0.08)",
    }}
  >
    <span style={{ width: "140px", opacity: 0.7 }}>{label}</span>
    <span style={{ fontWeight: "bold", textAlign: "right", flex: 1 }}>
      {value}
    </span>
  </div>
);

export default function FlightPanel({ routeData }) {
  if (!routeData) return null;

  const {
    total_distance_miles,
    total_time_minutes,
    selected_mission_type,
    exchange_required,
    exchange_stops,
    total_cost,
    arrival_time,
    departure_time,
    selection_notes = {},
    legs = [],
  } = routeData;

  const reasoning = [];

  if (selected_mission_type) {
    reasoning.push(`Mission type selected: ${selected_mission_type}`);
  }

  if (exchange_required) {
    if (Array.isArray(exchange_stops) && exchange_stops.length > 0) {
      reasoning.push(`Exchange required to satisfy mission structure via ${exchange_stops.join(", ")}`);
    } else {
      reasoning.push("Exchange required to satisfy mission structure");
    }
  } else {
    reasoning.push("Direct mission structure was feasible and selected");
  }

  if (selection_notes?.exchange_delay_min != null) {
    reasoning.push(`Exchange delay applied: ${selection_notes.exchange_delay_min} min`);
  }

  if (selection_notes?.airspace_penalty_min != null) {
    reasoning.push(`Airspace penalty considered: ${selection_notes.airspace_penalty_min} min`);
  }

  if (selection_notes?.corridor_penalty_min != null) {
    reasoning.push(`Corridor deviation penalty considered: ${selection_notes.corridor_penalty_min} min`);
  }

  if (legs.length >= 3) {
    reasoning.push("Mission is operationally more complex due to multi-leg structure");
  }
  // === STATUS LOGIC ===
  let status = "SAFE";
  let statusColor = "#4caf50";

  if (exchange_required) {
    status = "CAUTION";
    statusColor = "#ffb74d";
  }

  if (legs.length >= 3) {
    status = "COMPLEX";
    statusColor = "#ef5350";
  }
  return (
    <div>
      {/* HEADER */}
      <div
        style={{
          background: "#0a2d63",
          color: "white",
          borderRadius: "14px",
          padding: "14px 16px",
          marginBottom: "16px",
          fontWeight: "bold",
          fontSize: "22px",
          boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span>Flight Overview</span>

        <span
          style={{
            background: statusColor,
            color: "#002b5c",
            padding: "6px 10px",
            borderRadius: "8px",
            fontSize: "13px",
            fontWeight: "bold",
          }}
        >
          {status}
        </span>
      </div>

      {/* MISSION SUMMARY */}
      <div
        style={{
          background: "#082b5b",
          border: "2px solid #1e6ca1",
          borderRadius: "12px",
          padding: "16px",
          marginBottom: "16px",
          color: "white",
        }}
      >
        <div style={{ fontWeight: "bold", marginBottom: "10px", fontSize: "18px" }}>
          Mission Summary
        </div>
        <Row label="Mission Type" value={selected_mission_type ?? "N/A"} />
        <Row label="Distance" value={total_distance_miles != null ? `${total_distance_miles.toFixed(1)} mi` : "N/A"} />
        <Row label="Flight Time" value={total_time_minutes != null ? `${Math.round(total_time_minutes)} min` : "N/A"} />
        {/* <Row label="Leg Count" value={legs.length} />
        <Row label="Exchange Required" value={exchange_required ? "Yes" : "No"} />
        <Row label="Exchange Stops" value={Array.isArray(exchange_stops) && exchange_stops.length > 0 ? exchange_stops.join(", ") : "None"} /> */}
        <Row label="Departure" value={departure_time ?? "N/A"} />
        <Row label="Arrival" value={arrival_time ?? "N/A"} />
        <Row label="Score / Cost" value={total_cost ?? "N/A"} />
      </div>

      {/* LEGS */}
      <div
        style={{
          background: "#082b5b",
          border: "2px solid #1e6ca1",
          borderRadius: "12px",
          padding: "16px",
          marginBottom: "16px",
          color: "white",
          maxHeight: "140px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ fontWeight: "bold", marginBottom: "10px", fontSize: "18px" }}>
          Route Breakdown
        </div>

        <div
          style={{
            overflowY: "auto",
            paddingRight: "4px",
            flex: 1,
          }}
        >
          {legs.length === 0 ? (
            <div style={{ opacity: 0.7 }}>No leg data available</div>
          ) : (
            legs.map((leg, i) => (
              <div
                key={i}
                style={{
                  padding: "10px",
                  borderRadius: "8px",
                  background: "rgba(255,255,255,0.05)",
                  marginBottom: "10px",
                }}
              >
                <div style={{ fontWeight: "bold", marginBottom: "4px" }}>
                  Leg {i + 1}: {leg.from} → {leg.to}
                </div>
                <div style={{ fontSize: "14px", opacity: 0.85 }}>
                  Distance: {leg.distance_miles != null ? leg.distance_miles.toFixed(1) : "?"} mi
                </div>
              </div>
            ))
          )}
        </div>
      </div>
      {/* REASONING */}
      <div
        style={{
          background: "#082b5b",
          border: "2px solid #1e6ca1",
          borderRadius: "12px",
          padding: "16px",
          color: "white",
          maxHeight: "140px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ fontWeight: "bold", marginBottom: "10px", fontSize: "18px" }}>
          Why This Route Was Selected
        </div>

        <div
          style={{
            overflowY: "auto",
            paddingRight: "4px",
            flex: 1,
          }}
        >
          {reasoning.length > 0 ? (
            reasoning.map((item, i) => (
              <div key={i} style={{ marginBottom: "8px", opacity: 0.92 }}>
                • {item}
              </div>
            ))
          ) : (
            <div style={{ opacity: 0.75 }}>
              No route-selection reasoning available.
            </div>
          )}

          <div style={{ marginTop: "12px", opacity: 0.72 }}>
            This explanation is based on current mission-planning output and can later be expanded
            with live simulation state such as delay, diversion, queueing, battery, and landing availability.
          </div>
        </div>
      </div>
    </div>
  );
}