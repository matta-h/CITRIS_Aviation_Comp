export default function BottomToolbar({
  selectedDate,
  setSelectedDate,
  startHour,
  setStartHour,
  endHour,
  setEndHour,
  currentTimeMinutes,
  setCurrentTimeMinutes,
  showWeather,
  setShowWeather,
  showPopulation,
  setShowPopulation,
  showTerrain,
  setShowTerrain,
  showFlights,
  setShowFlights,
  showHazardRegions,
  setShowHazardRegions,
  initialize,
  isPreloading,
  simulateDay,
  isSimulating,
  simSummary,
  // Sim clock
  isPlaying,
  setIsPlaying,
  simSpeed,
  setSimSpeed,
}) {
  const h = Math.floor(currentTimeMinutes / 60);
  const m = currentTimeMinutes % 60;

  const SPEED_OPTIONS = [1, 2, 5, 10, 30, 60];

  return (
    <div
      style={{
        height: simSummary ? "148px" : "120px",
        background: "#031f47",
        borderTop: "2px solid #0c3f73",
        padding: "10px 16px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        color: "white",
        fontFamily: "Arial, sans-serif",
      }}
    >
      {/* Top row: date/time config + toggles */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "16px",
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            style={{ padding: "4px", borderRadius: "6px" }}
          />

          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            Start:
            <input
              type="number"
              min="0"
              max="23"
              value={startHour}
              onChange={(e) => setStartHour(Number(e.target.value))}
              style={{ width: "50px", marginLeft: "6px" }}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            End:
            <input
              type="number"
              min="0"
              max="23"
              value={endHour}
              onChange={(e) => setEndHour(Number(e.target.value))}
              style={{ width: "50px", marginLeft: "6px" }}
            />
            <button
              onClick={initialize}
              disabled={isPreloading || isSimulating}
              style={{
                marginLeft: "8px",
                padding: "4px 8px",
                borderRadius: "6px",
                background: "#1e6ca1",
                color: "white",
                border: "none",
                cursor: isPreloading || isSimulating ? "not-allowed" : "pointer",
                opacity: isPreloading || isSimulating ? 0.6 : 1,
              }}
            >
              {isPreloading ? "Loading..." : "Initialize"}
            </button>
            <button
              onClick={simulateDay}
              disabled={isSimulating || isPreloading}
              style={{
                marginLeft: "6px",
                padding: "4px 10px",
                borderRadius: "6px",
                background: isSimulating ? "#555" : "#2e7d32",
                color: "white",
                border: "none",
                cursor: isSimulating || isPreloading ? "not-allowed" : "pointer",
                fontWeight: "bold",
                opacity: isSimulating || isPreloading ? 0.7 : 1,
              }}
            >
              {isSimulating ? "Simulating..." : "Simulate Day"}
            </button>
          </div>
        </div>

        <div style={{ display: "flex", gap: "14px", flexWrap: "wrap" }}>
          <label>
            <input
              type="checkbox"
              checked={showHazardRegions}
              onChange={() => setShowHazardRegions(!showHazardRegions)}
              style={{ marginRight: "6px" }}
            />
            Hazard Regions
          </label>
          <label>
            <input
              type="checkbox"
              checked={showWeather}
              onChange={() => setShowWeather(!showWeather)}
              style={{ marginRight: "6px" }}
            />
            Weather
          </label>
          <label>
            <input
              type="checkbox"
              checked={showPopulation}
              onChange={() => setShowPopulation(!showPopulation)}
              style={{ marginRight: "6px" }}
            />
            Population
          </label>
          <label>
            <input
              type="checkbox"
              checked={showTerrain}
              onChange={() => setShowTerrain(!showTerrain)}
              style={{ marginRight: "6px" }}
            />
            Terrain
          </label>
          <label>
            <input
              type="checkbox"
              checked={showFlights}
              onChange={() => setShowFlights(!showFlights)}
              style={{ marginRight: "6px" }}
            />
            Flights
          </label>
        </div>
      </div>

      {/* Simulation summary strip */}
      {simSummary && !simSummary.error && (
        <div style={{
          display: "flex", gap: "18px", alignItems: "center",
          fontSize: "12px", background: "rgba(0,0,0,0.25)",
          borderRadius: "6px", padding: "4px 10px", flexWrap: "wrap",
        }}>
          <span style={{ color: "#64b5f6", fontWeight: "bold" }}>Sim Results:</span>
          <span>{simSummary.total_flights_network} flights</span>
          <span>{simSummary.total_passengers_network} pax</span>
          <span style={{ color: simSummary.total_profit_network >= 0 ? "#81c784" : "#e57373" }}>
            {simSummary.total_profit_network >= 0 ? "+" : ""}${simSummary.total_profit_network?.toLocaleString(undefined, { maximumFractionDigits: 0 })} profit
          </span>
          {simSummary.break_even_ticket_price && (
            <span style={{ opacity: 0.8 }}>Break-even: ${simSummary.break_even_ticket_price}</span>
          )}
          {simSummary.busiest_route && (
            <span style={{ opacity: 0.8 }}>
              Busiest: {simSummary.busiest_route.origin}→{simSummary.busiest_route.destination} ({simSummary.busiest_route.flight_count}x)
            </span>
          )}
        </div>
      )}
      {simSummary?.error && (
        <div style={{ fontSize: "12px", color: "#ef9a9a" }}>{simSummary.error}</div>
      )}

      {/* Bottom row: timeline scrubber + play controls */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>

        {/* Play / Pause */}
        <button
          onClick={() => setIsPlaying(!isPlaying)}
          style={{
            padding: "5px 14px",
            borderRadius: "6px",
            border: "none",
            background: isPlaying ? "#e53935" : "#43a047",
            color: "white",
            fontWeight: "bold",
            cursor: "pointer",
            minWidth: "64px",
            fontSize: "13px",
          }}
        >
          {isPlaying ? "⏸ Pause" : "▶ Play"}
        </button>

        {/* Speed selector */}
        <div style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "13px" }}>
          <span style={{ opacity: 0.75 }}>Speed:</span>
          {SPEED_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setSimSpeed(s)}
              style={{
                padding: "3px 8px",
                borderRadius: "5px",
                border: "1px solid rgba(255,255,255,0.2)",
                background: simSpeed === s ? "#1e6ca1" : "transparent",
                color: "white",
                cursor: "pointer",
                fontSize: "12px",
                fontWeight: simSpeed === s ? "bold" : "normal",
              }}
            >
              {s}×
            </button>
          ))}
        </div>

        {/* Current time display */}
        <span style={{ fontWeight: "bold", minWidth: "50px", textAlign: "right" }}>
          {String(h).padStart(2, "0")}:{String(m).padStart(2, "0")}
        </span>

        {/* Scrubber */}
        <input
          type="range"
          min={startHour * 60}
          max={endHour * 60}
          step={1}
          value={currentTimeMinutes}
          onChange={(e) => {
            setIsPlaying(false); // pause when scrubbing manually
            setCurrentTimeMinutes(Number(e.target.value));
          }}
          style={{ flex: 1 }}
        />

        <span style={{ opacity: 0.7 }}>{endHour}:00</span>
      </div>
    </div>
  );
}
