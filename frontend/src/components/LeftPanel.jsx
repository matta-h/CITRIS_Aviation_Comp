import { useState, useMemo } from "react";

const STATUS_COLOR = {
  available:           "#4caf50",
  taxiing_to_pad:      "#ffb74d",
  in_flight:           "#4fc3f7",
  taxiing_to_charge:   "#ffb74d",
  charging:            "#ff9800",
  queued:              "#ce93d8",
  inoperable:          "#ef5350",
};

const STATUS_LABEL = {
  available:           "Available",
  taxiing_to_pad:      "Taxiing",
  in_flight:           "In Flight",
  taxiing_to_charge:   "Taxiing",
  charging:            "Charging",
  queued:              "Queued",
  inoperable:          "Inoperable",
};

function BatteryBar({ pct }) {
  const color = pct > 60 ? "#4caf50" : pct > 30 ? "#ffb74d" : "#ef5350";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "6px", flex: 1 }}>
      <div style={{
        flex: 1, height: "6px", background: "rgba(255,255,255,0.1)",
        borderRadius: "3px", overflow: "hidden",
      }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: "3px" }} />
      </div>
      <span style={{ fontSize: "11px", opacity: 0.85, minWidth: "32px", textAlign: "right" }}>
        {Math.round(pct)}%
      </span>
    </div>
  );
}

function VTOLRow({ vtol }) {
  const statusColor = STATUS_COLOR[vtol.status] ?? "#90caf9";
  const label = STATUS_LABEL[vtol.status] ?? vtol.status;
  const inFlight = vtol.status === "in_flight";

  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: "3px",
      padding: "7px 10px",
      borderRadius: "8px",
      background: "rgba(255,255,255,0.04)",
      marginBottom: "4px",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        {/* Status dot */}
        <div style={{
          width: "8px", height: "8px", borderRadius: "50%",
          background: statusColor, flexShrink: 0,
        }} />
        {/* ID */}
        <span style={{ fontWeight: "bold", fontSize: "13px", minWidth: "72px" }}>
          {vtol.id}
        </span>
        {/* Battery bar */}
        <BatteryBar pct={vtol.battery_pct} />
        {/* Status badge */}
        <span style={{
          fontSize: "10px", fontWeight: "bold", padding: "2px 6px",
          borderRadius: "999px", background: statusColor, color: "#002b5c",
          flexShrink: 0,
        }}>
          {label}
        </span>
      </div>
      {inFlight && vtol.from_port && vtol.to_port && (
        <div style={{ fontSize: "11px", opacity: 0.6, paddingLeft: "16px" }}>
          {vtol.from_port} → {vtol.to_port}
        </div>
      )}
    </div>
  );
}

function PortSection({ portId, vtols }) {
  const [expanded, setExpanded] = useState(true);
  const inFlight = vtols.filter((v) => v.status === "in_flight").length;
  const charging = vtols.filter((v) => v.status === "charging").length;

  return (
    <div style={{ marginBottom: "8px" }}>
      <button
        onClick={() => setExpanded((e) => !e)}
        style={{
          width: "100%", display: "flex", justifyContent: "space-between",
          alignItems: "center", padding: "6px 10px",
          background: "#0c3565", border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: "8px", color: "white", cursor: "pointer",
          fontSize: "13px", fontWeight: "bold",
        }}
      >
        <span>{portId}</span>
        <span style={{ fontSize: "11px", opacity: 0.7, fontWeight: "normal" }}>
          {inFlight > 0 && <span style={{ color: "#4fc3f7" }}>{inFlight} flying </span>}
          {charging > 0 && <span style={{ color: "#ff9800" }}>{charging} charging </span>}
          {expanded ? "▲" : "▼"}
        </span>
      </button>
      {expanded && (
        <div style={{ marginTop: "4px", paddingLeft: "4px" }}>
          {vtols.map((v) => <VTOLRow key={v.id} vtol={v} />)}
        </div>
      )}
    </div>
  );
}

export default function LeftSidebar({
  nodes,
  activeFlights,
  fleet,
  pendingStart,
  pendingEnd,
  setPendingStart,
  setPendingEnd,
  pendingDepartureTime,
  setPendingDepartureTime,
  onCreateFlight,
  onSelectFlight,
  onDeleteFlight,
}) {
  const [addFlightOpen, setAddFlightOpen] = useState(false);

  const portOptions = nodes
    .filter((node) => node?.id)
    .sort((a, b) => a.id.localeCompare(b.id));

  const selectStyle = {
    width: "100%", padding: "6px 8px", borderRadius: "8px",
    border: "1px solid rgba(255,255,255,0.15)",
    background: "#08244f", color: "white", fontSize: "13px",
  };

  const labelStyle = { fontSize: "11px", opacity: 0.8, marginBottom: "3px" };

  // Group fleet by current_port
  const fleetByPort = useMemo(() => {
    const groups = {};
    (fleet ?? []).forEach((v) => {
      const port = v.current_port ?? v.home_port;
      if (!groups[port]) groups[port] = [];
      groups[port].push(v);
    });
    // For in-flight VTOLs, group under home_port instead so they still appear somewhere
    // Actually fleet API returns current_port = home port when in flight (set in backend).
    // If port is null for in_flight, fall back to home_port.
    return groups;
  }, [fleet]);

  const portOrder = Object.keys(fleetByPort).sort();

  return (
    <div style={{
      width: "310px", height: "100%", display: "flex", flexDirection: "column",
      background: "linear-gradient(180deg, #052b63 0%, #031f47 100%)",
      borderRight: "2px solid #0c3f73",
      boxShadow: "4px 0 16px rgba(0,0,0,0.3)",
      fontFamily: "Arial, sans-serif", color: "white",
    }}>
      {/* Header */}
      <div style={{
        padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.1)",
        fontWeight: "bold", fontSize: "17px", letterSpacing: "1px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <span>FLEET MANAGER</span>
        <span style={{ fontSize: "12px", opacity: 0.6 }}>{fleet.length} VTOLs</span>
      </div>

      {/* Add Flight — collapsible */}
      <div style={{ padding: "10px 14px", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
        <button
          onClick={() => setAddFlightOpen((o) => !o)}
          style={{
            width: "100%", padding: "7px 12px", borderRadius: "8px",
            border: "1px solid rgba(255,255,255,0.15)",
            background: addFlightOpen ? "#0e62b6" : "#0a2d63",
            color: "white", fontWeight: "bold", fontSize: "13px", cursor: "pointer",
            textAlign: "left",
          }}
        >
          {addFlightOpen ? "▾" : "▸"} Add Flight (debug)
        </button>

        {addFlightOpen && (
          <div style={{
            marginTop: "8px", background: "#0a2d63",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "10px", padding: "12px",
          }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <div>
                <div style={labelStyle}>Origin</div>
                <select value={pendingStart} onChange={(e) => setPendingStart(e.target.value)} style={selectStyle}>
                  <option value="">Select port...</option>
                  {portOptions.map((node) => (
                    <option key={`s-${node.id}`} value={node.id}>{node.id} — {node.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <div style={labelStyle}>Destination</div>
                <select value={pendingEnd} onChange={(e) => setPendingEnd(e.target.value)} style={selectStyle}>
                  <option value="">Select port...</option>
                  {portOptions.map((node) => (
                    <option key={`e-${node.id}`} value={node.id}>{node.id} — {node.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <div style={labelStyle}>Departure <span style={{ opacity: 0.5 }}>(blank = sim clock)</span></div>
                <input
                  type="time" value={pendingDepartureTime}
                  onChange={(e) => setPendingDepartureTime(e.target.value)}
                  style={{ ...selectStyle, colorScheme: "dark" }}
                />
              </div>
              <button
                onClick={onCreateFlight}
                disabled={!pendingStart || !pendingEnd || pendingStart === pendingEnd}
                style={{
                  padding: "8px 12px", borderRadius: "8px", border: "none",
                  cursor: (!pendingStart || !pendingEnd || pendingStart === pendingEnd) ? "not-allowed" : "pointer",
                  background: (!pendingStart || !pendingEnd || pendingStart === pendingEnd) ? "#5d6f89" : "#0e62b6",
                  color: "white", fontWeight: "bold", fontSize: "13px",
                }}
              >
                Create Flight
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Fleet Status */}
      <div style={{ padding: "10px 14px 4px", fontWeight: "bold", fontSize: "13px", opacity: 0.8 }}>
        FLEET STATUS
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "0 14px 10px" }}>
        {portOrder.length === 0 ? (
          <div style={{ opacity: 0.5, fontSize: "13px", padding: "10px 0" }}>
            Fleet data loading...
          </div>
        ) : (
          portOrder.map((port) => (
            <PortSection key={port} portId={port} vtols={fleetByPort[port]} />
          ))
        )}

        {/* Active Flights */}
        {activeFlights.length > 0 && (
          <>
            <div style={{
              fontWeight: "bold", fontSize: "13px", opacity: 0.8,
              marginTop: "12px", marginBottom: "6px",
            }}>
              ACTIVE FLIGHTS
            </div>
            {activeFlights.map((flight) => {
              const statusColor =
                flight.status === "arrived" ? "#4caf50"
                : flight.status === "turnaround" ? "#ffb74d"
                : flight.status === "waiting_departure" ? "#90caf9"
                : "#4fc3f7";

              const statusLabel =
                flight.status === "arrived" ? "Arrived"
                : flight.status === "turnaround" ? "Exchange"
                : flight.status === "waiting_departure" ? "Scheduled"
                : flight.status === "enroute_leg1" ? "Leg 1"
                : flight.status === "enroute_leg2" ? "Leg 2"
                : "En Route";

              return (
                <div
                  key={flight.id}
                  onClick={() => onSelectFlight(flight)}
                  style={{
                    background: "#0a2d63",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: "10px", padding: "10px 12px",
                    marginBottom: "8px", cursor: "pointer",
                    boxShadow: "0 3px 8px rgba(0,0,0,0.2)",
                  }}
                >
                  <div style={{
                    display: "flex", justifyContent: "space-between",
                    alignItems: "center", marginBottom: "4px",
                  }}>
                    <div style={{ fontWeight: "bold", fontSize: "13px" }}>
                      {flight.start} → {flight.end}
                    </div>
                    <div style={{
                      fontSize: "10px", fontWeight: "bold", padding: "2px 6px",
                      borderRadius: "999px", background: statusColor, color: "#002b5c",
                    }}>
                      {statusLabel}
                    </div>
                  </div>

                  {flight.vtolId && (
                    <div style={{ fontSize: "11px", opacity: 0.7, marginBottom: "3px" }}>
                      {flight.vtolId}
                      {flight.vtolBatteryCostPct != null && ` · −${flight.vtolBatteryCostPct.toFixed(0)}% battery`}
                    </div>
                  )}

                  <div style={{
                    display: "flex", justifyContent: "space-between",
                    fontSize: "11px", opacity: 0.75, marginTop: "4px",
                  }}>
                    <span>Dep <b>{flight.departureLabel ?? "—"}</b></span>
                    <span>→</span>
                    <span>Arr <b>{flight.arrivalLabel ?? "—"}</b></span>
                  </div>

                  <div style={{ marginTop: "6px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: "11px", opacity: 0.6 }}>
                      {((flight.progress ?? 0) * 100).toFixed(0)}%
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); onDeleteFlight(flight.id); }}
                      style={{
                        padding: "3px 8px", borderRadius: "6px",
                        border: "1px solid rgba(255,255,255,0.15)",
                        background: "#7d1020", color: "white",
                        cursor: "pointer", fontSize: "11px",
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
