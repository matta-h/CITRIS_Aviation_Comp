export default function LeftSidebar({
  nodes,
  activeFlights,
  pendingStart,
  pendingEnd,
  setPendingStart,
  setPendingEnd,
  onCreateFlight,
  onSelectFlight,
  onDeleteFlight,
}) {
  const portOptions = nodes
    .filter((node) => node?.id)
    .sort((a, b) => a.id.localeCompare(b.id));

  return (
    <div
      style={{
        width: "410px",
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
            <div>
              <div style={{ fontSize: "12px", opacity: 0.85, marginBottom: "4px" }}>Origin</div>
              <select
                value={pendingStart}
                onChange={(e) => setPendingStart(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px",
                  borderRadius: "8px",
                  border: "1px solid rgba(255,255,255,0.15)",
                  background: "#08244f",
                  color: "white",
                }}
              >
                <option value="">Select port...</option>
                {portOptions.map((node) => (
                  <option key={`start-${node.id}`} value={node.id}>
                    {node.id} — {node.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <div style={{ fontSize: "12px", opacity: 0.85, marginBottom: "4px" }}>Destination</div>
              <select
                value={pendingEnd}
                onChange={(e) => setPendingEnd(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px",
                  borderRadius: "8px",
                  border: "1px solid rgba(255,255,255,0.15)",
                  background: "#08244f",
                  color: "white",
                }}
              >
                <option value="">Select port...</option>
                {portOptions.map((node) => (
                  <option key={`end-${node.id}`} value={node.id}>
                    {node.id} — {node.name}
                  </option>
                ))}
              </select>
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

      <div style={{ padding: "14px", fontWeight: "bold", fontSize: "15px" }}>
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
          activeFlights.map((flight) => (
            <div
              key={flight.id}
              onClick={() => onSelectFlight(flight)}
              style={{
                background: "#0a2d63",
                border: "1px solid rgba(255,255,255,0.12)",
                borderRadius: "14px",
                padding: "14px",
                marginBottom: "12px",
                boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
                cursor: "pointer",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "8px",
                }}
              >
                <div style={{ fontWeight: "bold", fontSize: "16px" }}>
                  {flight.start} → {flight.end}
                </div>
                <div
                  style={{
                    fontSize: "11px",
                    fontWeight: "bold",
                    padding: "4px 8px",
                    borderRadius: "999px",
                    background:
                      flight.risk === "High"
                        ? "#e53935"
                        : flight.risk === "Medium"
                          ? "#fbc02d"
                          : "#43a047",
                    color: flight.risk === "Medium" ? "#222" : "white",
                  }}
                >
                  {flight.risk || "Pending"}
                </div>
              </div>

              <div style={{ fontSize: "14px", lineHeight: 1.5, opacity: 0.95 }}>
                <div>Total: {flight.distanceText || "—"}</div>
                <div>ETA: {flight.etaText || "—"}</div>
              </div>

              <div style={{ marginTop: "10px", display: "flex", justifyContent: "flex-end" }}>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteFlight(flight.id);
                  }}
                  style={{
                    padding: "6px 10px",
                    borderRadius: "8px",
                    border: "1px solid rgba(255,255,255,0.15)",
                    background: "#7d1020",
                    color: "white",
                    cursor: "pointer",
                    fontWeight: "bold",
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}