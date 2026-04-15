export default function LeftSidebar({
  nodes,
  activeFlights,
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
  const portOptions = nodes
    .filter((node) => node?.id)
    .sort((a, b) => a.id.localeCompare(b.id));

  const selectStyle = {
    width: "100%",
    padding: "8px",
    borderRadius: "8px",
    border: "1px solid rgba(255,255,255,0.15)",
    background: "#08244f",
    color: "white",
  };

  const labelStyle = {
    fontSize: "12px",
    opacity: 0.85,
    marginBottom: "4px",
  };

  return (
    <div
      style={{
        width: "310px",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: "linear-gradient(180deg, #052b63 0%, #031f47 100%)",
        borderRight: "2px solid #0c3f73",
        boxShadow: "4px 0 16px rgba(0,0,0,0.3)",
        fontFamily: "Arial, sans-serif",
        color: "white",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "16px",
          borderBottom: "1px solid rgba(255,255,255,0.1)",
          fontWeight: "bold",
          fontSize: "18px",
          letterSpacing: "1px",
        }}
      >
        FLIGHT MANAGER
      </div>

      {/* Add Flight form */}
      <div style={{ padding: "14px", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
        <div
          style={{
            background: "#0a2d63",
            border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: "14px",
            padding: "14px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
          }}
        >
          <div style={{ fontWeight: "bold", fontSize: "15px", marginBottom: "10px" }}>
            Add Flight
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {/* Origin */}
            <div>
              <div style={labelStyle}>Origin</div>
              <select value={pendingStart} onChange={(e) => setPendingStart(e.target.value)} style={selectStyle}>
                <option value="">Select port...</option>
                {portOptions.map((node) => (
                  <option key={`start-${node.id}`} value={node.id}>
                    {node.id} — {node.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Destination */}
            <div>
              <div style={labelStyle}>Destination</div>
              <select value={pendingEnd} onChange={(e) => setPendingEnd(e.target.value)} style={selectStyle}>
                <option value="">Select port...</option>
                {portOptions.map((node) => (
                  <option key={`end-${node.id}`} value={node.id}>
                    {node.id} — {node.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Departure time */}
            <div>
              <div style={labelStyle}>Departure Time <span style={{ opacity: 0.55 }}>(leave blank to use sim clock)</span></div>
              <input
                type="time"
                value={pendingDepartureTime}
                onChange={(e) => setPendingDepartureTime(e.target.value)}
                style={{
                  ...selectStyle,
                  colorScheme: "dark",
                }}
              />
            </div>

            <button
              onClick={onCreateFlight}
              disabled={!pendingStart || !pendingEnd || pendingStart === pendingEnd}
              style={{
                marginTop: "4px",
                padding: "10px 12px",
                borderRadius: "10px",
                border: "none",
                cursor:
                  !pendingStart || !pendingEnd || pendingStart === pendingEnd
                    ? "not-allowed"
                    : "pointer",
                background:
                  !pendingStart || !pendingEnd || pendingStart === pendingEnd
                    ? "#5d6f89"
                    : "#0e62b6",
                color: "white",
                fontWeight: "bold",
              }}
            >
              Create Flight
            </button>
          </div>
        </div>
      </div>

      {/* Active flights list */}
      <div style={{ padding: "14px 14px 6px", fontWeight: "bold", fontSize: "15px" }}>
        Active Flights
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "0 14px 14px 14px" }}>
        {activeFlights.length === 0 ? (
          <div
            style={{
              background: "#0a2d63",
              borderRadius: "14px",
              padding: "18px",
              opacity: 0.85,
              textAlign: "center",
            }}
          >
            No active flights yet.
          </div>
        ) : (
          activeFlights.map((flight) => {
            const statusColor =
              flight.status === "arrived" ? "#4caf50"
              : flight.status === "turnaround" ? "#ffb74d"
              : flight.status === "waiting_departure" ? "#90caf9"
              : "#4fc3f7";

            const statusLabel =
              flight.status === "arrived" ? "Arrived"
              : flight.status === "turnaround" ? "At Exchange"
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
                  border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: "14px",
                  padding: "12px 14px",
                  marginBottom: "10px",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
                  cursor: "pointer",
                }}
              >
                {/* Route + status badge */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "8px",
                  }}
                >
                  <div style={{ fontWeight: "bold", fontSize: "15px" }}>
                    {flight.start} → {flight.end}
                  </div>
                  <div
                    style={{
                      fontSize: "11px",
                      fontWeight: "bold",
                      padding: "3px 8px",
                      borderRadius: "999px",
                      background: statusColor,
                      color: "#002b5c",
                    }}
                  >
                    {statusLabel}
                  </div>
                </div>

                {/* Distance + progress */}
                <div style={{ fontSize: "13px", lineHeight: 1.6, opacity: 0.92 }}>
                  <div>Distance: {flight.distanceText || "—"}</div>
                  <div>Progress: {((flight.progress ?? 0) * 100).toFixed(0)}%</div>
                </div>

                {/* Departure / Arrival times */}
                <div
                  style={{
                    marginTop: "8px",
                    padding: "7px 10px",
                    background: "rgba(255,255,255,0.06)",
                    borderRadius: "8px",
                    fontSize: "12px",
                    display: "flex",
                    justifyContent: "space-between",
                  }}
                >
                  <span>
                    <span style={{ opacity: 0.65 }}>Dep </span>
                    <b>{flight.departureLabel ?? "—"}</b>
                  </span>
                  <span style={{ opacity: 0.45 }}>→</span>
                  <span>
                    <span style={{ opacity: 0.65 }}>Arr </span>
                    <b>{flight.arrivalLabel ?? "—"}</b>
                  </span>
                </div>

                {/* Delete */}
                <div style={{ marginTop: "10px", display: "flex", justifyContent: "flex-end" }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteFlight(flight.id);
                    }}
                    style={{
                      padding: "5px 10px",
                      borderRadius: "8px",
                      border: "1px solid rgba(255,255,255,0.15)",
                      background: "#7d1020",
                      color: "white",
                      cursor: "pointer",
                      fontWeight: "bold",
                      fontSize: "12px",
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
