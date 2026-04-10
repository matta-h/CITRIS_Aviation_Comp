import PortPanel from "./PortPanel";
import FlightPanel from "./FlightPanel";

export default function RightPanel({
  selectedType,
  selectedNode,
  routeData,
  weather,
}) {
  const panelTitle =
    selectedType === "port"
      ? "PORT VIEW"
      : selectedType === "flight"
        ? "FLIGHT VIEW"
        : "OPERATIONS PANEL";

  const panelColor =
    selectedType === "port"
      ? "#4fc3f7"
      : selectedType === "flight"
        ? "#ffb74d"
        : "#90caf9";

  return (
    <div
      style={{
        width: "325px",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: "linear-gradient(180deg, #052b63 0%, #031f47 100%)",
        borderLeft: "2px solid #0c3f73",
        boxShadow: "-4px 0 16px rgba(0,0,0,0.3)",
        fontFamily: "Arial, sans-serif",
        fontSize: "0.875rem",
      }}
    >
      <div
        style={{
          padding: "16px",
          borderBottom: "1px solid rgba(255,255,255,0.1)",
          color: "white",
          fontWeight: "bold",
          fontSize: "18px",
          letterSpacing: "1px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span>{panelTitle}</span>

        <span
          style={{
            fontSize: "12px",
            padding: "4px 8px",
            borderRadius: "6px",
            background: panelColor,
            color: "#002b5c",
            fontWeight: "bold",
          }}
        >
          ACTIVE
        </span>
      </div>
      <div
        style={{
          flex: 1,
          overflow: "hidden",          // 🔴 CHANGE
          padding: "16px",
          display: "flex",             // 🔴 ADD
          flexDirection: "column",     // 🔴 ADD
        }}
      ><div style={{ flex: 1, overflowY: "auto" }}>
          {selectedType === "port" && selectedNode ? (
            <PortPanel node={selectedNode} weather={weather} />
          ) : selectedType === "flight" && routeData ? (
            <FlightPanel routeData={routeData} />
          ) : (
            <div
              style={{
                color: "white",
                background: "#0a2d63",
                borderRadius: "14px",
                padding: "24px",
                fontSize: "16px",
                textAlign: "center",
                opacity: 0.85,
                boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
              }}
            >
              Select a port or flight to view operational data.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}