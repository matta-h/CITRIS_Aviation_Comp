import React from "react";

const Row = ({ label, value, highlight }) => (
  <div
    style={{
      display: "flex",
      justifyContent: "space-between",
      padding: "6px 0",
      borderBottom: "1px solid rgba(255,255,255,0.08)",
    }}
  >
    <span style={{ width: "140px", opacity: 0.7 }}>{label}</span>
    <span
      style={{
        fontWeight: "bold",
        textAlign: "right",
        flex: 1,
        color: highlight ?? "inherit",
      }}
    >
      {value}
    </span>
  </div>
);

export default function FlightPanel({ routeData, selectedFlight }) {
  if (!routeData && !selectedFlight) return null;

  const data = routeData ?? selectedFlight?.routeData ?? {};
  const telemetry = selectedFlight?.telemetry ?? null;
  const flightStatus = selectedFlight?.status ?? null;

  const {
    total_distance_miles,
    total_time_minutes,
    selected_mission_type,
    exchange_required,
    exchange_stops,
    score,           // ← correct field name from mission_planner._finalize_selected_candidate
    total_cost,      // ← fallback from routing._run_field_search (direct flights)
    arrival_time,
    departure_time,
    selection_notes = {},
    legs = [],
  } = data;

  const displayScore = score ?? total_cost ?? null;

  // ── Live telemetry ──────────────────────────────────────
  const altFt = telemetry?.altFt;
  const speedMph = telemetry?.speedMph;

  const fmtAlt = altFt != null
    ? `${Math.round(altFt).toLocaleString()} ft`
    : "—";

  const fmtSpeed = speedMph != null
    ? speedMph === 0
      ? "0 mph (vertical)"
      : `${speedMph} mph`
    : "—";

  // Altitude colour: green = cruise, amber = climbing/descending, gray = ground
  let altColor = "white";
  if (altFt != null) {
    if (altFt < 200) altColor = "#90caf9";           // near ground — blue
    else if (altFt < 3000) altColor = "#ffb74d";     // climbing/descending — amber
    else altColor = "#4caf50";                        // cruise — green
  }

  // ── Reasoning ──────────────────────────────────────────
  const reasoning = [];
  if (selected_mission_type) reasoning.push(`Mission type: ${selected_mission_type}`);
  if (exchange_required) {
    reasoning.push(
      Array.isArray(exchange_stops) && exchange_stops.length > 0
        ? `Exchange via ${exchange_stops.join(", ")}`
        : "Exchange required"
    );
  } else {
    reasoning.push("Direct mission selected");
  }
  if (selection_notes?.exchange_delay_min != null)
    reasoning.push(`Exchange delay: ${selection_notes.exchange_delay_min} min`);
  if (selection_notes?.airspace_penalty_min != null)
    reasoning.push(`Airspace penalty: ${selection_notes.airspace_penalty_min} min`);
  if (selection_notes?.corridor_penalty_min != null)
    reasoning.push(`Corridor penalty: ${selection_notes.corridor_penalty_min} min`);
  if (legs.length >= 3)
    reasoning.push("Multi-leg structure");

  // ── Status badge ───────────────────────────────────────
  let status = "SAFE";
  let statusColor = "#4caf50";
  if (exchange_required) { status = "CAUTION"; statusColor = "#ffb74d"; }
  if (legs.length >= 3)  { status = "COMPLEX"; statusColor = "#ef5350"; }

  // Override with live flight phase if available
  const phaseLabel = {
    waiting_departure: "SCHEDULED",
    enroute:           "EN ROUTE",
    enroute_leg1:      "LEG 1",
    turnaround:        "AT EXCHANGE",
    enroute_leg2:      "LEG 2",
    arrived:           "ARRIVED",
  }[flightStatus];

  const phaseColor = {
    waiting_departure: "#90caf9",
    enroute:           "#4caf50",
    enroute_leg1:      "#4caf50",
    turnaround:        "#ffb74d",
    enroute_leg2:      "#4caf50",
    arrived:           "#b0bec5",
  }[flightStatus] ?? statusColor;

  return (
    <div>
      {/* ── Header ── */}
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
            background: phaseLabel ? phaseColor : statusColor,
            color: "#002b5c",
            padding: "6px 10px",
            borderRadius: "8px",
            fontSize: "12px",
            fontWeight: "bold",
          }}
        >
          {phaseLabel ?? status}
        </span>
      </div>

      {/* ── Live Telemetry ── */}
      {selectedFlight && (
        <div
          style={{
            background: "#071e40",
            border: "2px solid #1a5276",
            borderRadius: "12px",
            padding: "14px 16px",
            marginBottom: "16px",
            color: "white",
          }}
        >
          <div style={{ fontWeight: "bold", marginBottom: "10px", fontSize: "16px", opacity: 0.85 }}>
            ✈ Live Telemetry
          </div>
          <Row
            label="Altitude"
            value={fmtAlt}
            highlight={altColor}
          />
          <Row
            label="Horiz. Speed"
            value={fmtSpeed}
            highlight={speedMph === 0 && altFt > 100 ? "#ffb74d" : "white"}
          />
          <Row
            label="Progress"
            value={selectedFlight.progress != null
              ? `${(selectedFlight.progress * 100).toFixed(0)}%`
              : "—"}
          />
        </div>
      )}

      {/* ── Mission Summary ── */}
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
        <Row
          label="Distance"
          value={total_distance_miles != null ? `${total_distance_miles.toFixed(1)} mi` : "N/A"}
        />
        <Row
          label="Flight Time"
          value={total_time_minutes != null ? `${Math.round(total_time_minutes)} min` : "N/A"}
        />
        <Row label="Departure" value={departure_time ?? selectedFlight?.departureLabel ?? "N/A"} />
        <Row label="Arrival"   value={arrival_time   ?? selectedFlight?.arrivalLabel   ?? "N/A"} />
        <Row
          label="Score"
          value={displayScore != null ? displayScore.toFixed(1) : "N/A"}
        />
      </div>

      {/* ── Route Breakdown ── */}
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
        <div style={{ overflowY: "auto", paddingRight: "4px", flex: 1 }}>
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
                <div style={{ fontSize: "13px", opacity: 0.85 }}>
                  {leg.distance_miles != null ? `${leg.distance_miles.toFixed(1)} mi` : "?"}
                  {leg.route_class ? ` · ${leg.route_class}` : ""}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── Why This Route ── */}
      <div
        style={{
          background: "#082b5b",
          border: "2px solid #1e6ca1",
          borderRadius: "12px",
          padding: "16px",
          color: "white",
          maxHeight: "130px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ fontWeight: "bold", marginBottom: "10px", fontSize: "18px" }}>
          Why This Route
        </div>
        <div style={{ overflowY: "auto", paddingRight: "4px", flex: 1 }}>
          {reasoning.map((item, i) => (
            <div key={i} style={{ marginBottom: "6px", opacity: 0.92, fontSize: "13px" }}>
              • {item}
            </div>
          ))}
          <div style={{ marginTop: "10px", opacity: 0.55, fontSize: "12px" }}>
            Telemetry updates live from simulation clock.
          </div>
        </div>
      </div>
    </div>
  );
}