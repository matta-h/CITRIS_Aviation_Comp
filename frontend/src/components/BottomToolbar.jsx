import { useState, useEffect } from "react";

const TAB_STYLE = (active) => ({
  padding: "5px 18px",
  border: "none",
  borderBottom: active ? "2px solid #4fc3f7" : "2px solid transparent",
  background: "transparent",
  color: active ? "#4fc3f7" : "rgba(255,255,255,0.5)",
  fontWeight: active ? "bold" : "normal",
  fontSize: "12px",
  cursor: "pointer",
  letterSpacing: "0.4px",
  transition: "color 0.15s",
  whiteSpace: "nowrap",
});

const LABEL_STYLE = {
  fontSize: "12px",
  opacity: 0.75,
  whiteSpace: "nowrap",
};

const INPUT_STYLE = {
  width: "58px",
  padding: "3px 5px",
  borderRadius: "5px",
  border: "1px solid rgba(255,255,255,0.2)",
  background: "rgba(255,255,255,0.08)",
  color: "white",
  fontSize: "12px",
  textAlign: "center",
};

const TOGGLE_LABEL = (active) => ({
  display: "flex",
  alignItems: "center",
  gap: "6px",
  padding: "4px 10px",
  borderRadius: "6px",
  background: active ? "rgba(79,195,247,0.18)" : "rgba(255,255,255,0.06)",
  border: `1px solid ${active ? "rgba(79,195,247,0.5)" : "rgba(255,255,255,0.12)"}`,
  cursor: "pointer",
  fontSize: "12px",
  color: active ? "#4fc3f7" : "rgba(255,255,255,0.7)",
  userSelect: "none",
  transition: "all 0.15s",
});

export default function BottomToolbar({
  // Date / time
  selectedDate, setSelectedDate,
  startHour, setStartHour,
  endHour, setEndHour,
  currentTimeMinutes, setCurrentTimeMinutes,
  // Actions
  initialize, isPreloading,
  simulateDay, isSimulating, simSummary,
  // Playback
  isPlaying, setIsPlaying,
  simSpeed, setSimSpeed,
  // Map overlays
  showWeather, setShowWeather,
  showPopulation, setShowPopulation,
  showTerrain, setShowTerrain,
  showFlights, setShowFlights,
  showHazardRegions, setShowHazardRegions,
  // Sim config (UI only for now)
  pilotEnabled, setPilotEnabled,
  batteryMinPct, setBatteryMinPct,
  ticketPrice, setTicketPrice,
  demandScale, setDemandScale,
  turnaroundMinutes, setTurnaroundMinutes,
  minPassengers, setMinPassengers,
  portConfig, onApplyPortConfig,
}) {
  const [activeTab, setActiveTab] = useState("controls");

  // Local editable copy of port config; synced when prop loads/changes
  const [localPorts, setLocalPorts] = useState({});
  useEffect(() => {
    if (!portConfig) return;
    const init = {};
    for (const [id, cfg] of Object.entries(portConfig)) {
      init[id] = {
        totalPads: (cfg.takeoff_landing_pads ?? 1) + (cfg.charging_pads ?? 2),
        vtolCount: cfg.vtol_count ?? 2,
      };
    }
    setLocalPorts(init);
  }, [portConfig]);

  const h = Math.floor(currentTimeMinutes / 60);
  const m = currentTimeMinutes % 60;
  const SPEED_OPTIONS = [1, 2, 5, 10, 30, 60];

  const busy = isPreloading || isSimulating;

  return (
    <div style={{
      height: "130px",
      background: "#031f47",
      borderTop: "2px solid #0c3f73",
      display: "flex",
      flexDirection: "column",
      color: "white",
      fontFamily: "Arial, sans-serif",
      flexShrink: 0,
    }}>

      {/* ── Tab bar ── */}
      <div style={{
        display: "flex",
        alignItems: "flex-end",
        borderBottom: "1px solid rgba(255,255,255,0.1)",
        paddingLeft: "12px",
        gap: "2px",
        height: "30px",
        flexShrink: 0,
      }}>
        {[
          { id: "controls",   label: "Controls" },
          { id: "overlays",   label: "Overlays" },
          { id: "config",     label: "Sim Config" },
          { id: "vertiports", label: "Vertiport Config" },
        ].map(({ id, label }) => (
          <button key={id} style={TAB_STYLE(activeTab === id)} onClick={() => setActiveTab(id)}>
            {label}
          </button>
        ))}

        {/* Sim summary pill — always visible in tab bar when available */}
        {simSummary && !simSummary.error && (
          <div style={{
            marginLeft: "auto", marginRight: "12px",
            display: "flex", gap: "12px", alignItems: "center",
            fontSize: "11px", opacity: 0.9,
          }}>
            <span style={{ color: "#64b5f6", fontWeight: "bold" }}>
              {simSummary.total_flights_network} flights
            </span>
            <span>{simSummary.total_passengers_network} pax</span>
            <span style={{ color: simSummary.total_profit_network >= 0 ? "#81c784" : "#e57373", fontWeight: "bold" }}>
              {simSummary.total_profit_network >= 0 ? "+" : ""}
              ${simSummary.total_profit_network?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>
            {simSummary.break_even_ticket_price && (
              <span style={{ opacity: 0.7 }}>BE: ${simSummary.break_even_ticket_price}</span>
            )}
          </div>
        )}
        {simSummary?.error && (
          <span style={{ marginLeft: "auto", marginRight: "12px", fontSize: "11px", color: "#ef9a9a" }}>
            {simSummary.error}
          </span>
        )}
      </div>

      {/* ── Tab content (100px) ── */}
      <div style={{
        flex: 1,
        padding: "8px 14px",
        display: "flex",
        flexDirection: "column",
        gap: "7px",
        overflow: "hidden",
      }}>

        {/* ── CONTROLS TAB ── */}
        {activeTab === "controls" && (<>
          {/* Row 1: date / time / action buttons */}
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              style={{ padding: "3px 5px", borderRadius: "6px", fontSize: "12px" }}
            />
            <span style={LABEL_STYLE}>Start</span>
            <input type="number" min="0" max="23" value={startHour}
              onChange={(e) => setStartHour(Number(e.target.value))}
              style={{ ...INPUT_STYLE, width: "46px" }}
            />
            <span style={LABEL_STYLE}>End</span>
            <input type="number" min="0" max="23" value={endHour}
              onChange={(e) => setEndHour(Number(e.target.value))}
              style={{ ...INPUT_STYLE, width: "46px" }}
            />
            <button onClick={initialize} disabled={busy} style={{
              padding: "4px 10px", borderRadius: "6px",
              background: busy ? "#333" : "#1e6ca1",
              color: "white", border: "none",
              cursor: busy ? "not-allowed" : "pointer",
              fontSize: "12px", opacity: busy ? 0.6 : 1,
            }}>
              {isPreloading ? "Loading..." : "Initialize"}
            </button>
            <button onClick={simulateDay} disabled={busy} style={{
              padding: "4px 10px", borderRadius: "6px",
              background: busy ? "#333" : "#2e7d32",
              color: "white", border: "none",
              cursor: busy ? "not-allowed" : "pointer",
              fontWeight: "bold", fontSize: "12px", opacity: busy ? 0.7 : 1,
            }}>
              {isSimulating ? "Simulating..." : "Simulate Day"}
            </button>
          </div>

          {/* Row 2: playback */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <button onClick={() => setIsPlaying(!isPlaying)} style={{
              padding: "4px 12px", borderRadius: "6px", border: "none",
              background: isPlaying ? "#e53935" : "#43a047",
              color: "white", fontWeight: "bold", cursor: "pointer",
              minWidth: "60px", fontSize: "12px",
            }}>
              {isPlaying ? "⏸ Pause" : "▶ Play"}
            </button>

            <span style={LABEL_STYLE}>Speed:</span>
            {SPEED_OPTIONS.map((s) => (
              <button key={s} onClick={() => setSimSpeed(s)} style={{
                padding: "2px 7px", borderRadius: "4px",
                border: "1px solid rgba(255,255,255,0.2)",
                background: simSpeed === s ? "#1e6ca1" : "transparent",
                color: "white", cursor: "pointer", fontSize: "11px",
                fontWeight: simSpeed === s ? "bold" : "normal",
              }}>{s}×</button>
            ))}

            <span style={{ fontWeight: "bold", minWidth: "42px", textAlign: "right", fontSize: "13px" }}>
              {String(h).padStart(2, "0")}:{String(m).padStart(2, "0")}
            </span>

            <input type="range"
              min={startHour * 60} max={endHour * 60} step={1}
              value={currentTimeMinutes}
              onChange={(e) => { setIsPlaying(false); setCurrentTimeMinutes(Number(e.target.value)); }}
              style={{ flex: 1 }}
            />
            <span style={{ fontSize: "11px", opacity: 0.6 }}>{endHour}:00</span>
          </div>
        </>)}

        {/* ── OVERLAYS TAB ── */}
        {activeTab === "overlays" && (
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", paddingTop: "6px" }}>
            {[
              { label: "Weather",        val: showWeather,       set: setShowWeather },
              { label: "Population",     val: showPopulation,    set: setShowPopulation },
              { label: "Terrain",        val: showTerrain,       set: setShowTerrain },
              { label: "Flights",        val: showFlights,       set: setShowFlights },
              { label: "Hazard Regions", val: showHazardRegions, set: setShowHazardRegions },
            ].map(({ label, val, set }) => (
              <div key={label} style={TOGGLE_LABEL(val)} onClick={() => set(!val)}>
                <span style={{
                  width: "8px", height: "8px", borderRadius: "50%",
                  background: val ? "#4fc3f7" : "rgba(255,255,255,0.25)",
                  flexShrink: 0,
                }} />
                {label}
              </div>
            ))}
          </div>
        )}

        {/* ── SIM CONFIG TAB ── */}
        {activeTab === "config" && (
          <div style={{ display: "flex", alignItems: "center", gap: "20px", flexWrap: "wrap", paddingTop: "4px" }}>

            {/* Piloted flight toggle */}
            <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
              <span style={{ ...LABEL_STYLE, fontSize: "11px" }}>Piloted Flight</span>
              <div style={{ display: "flex", borderRadius: "6px", overflow: "hidden", border: "1px solid rgba(255,255,255,0.2)" }}>
                {[true, false].map((v) => (
                  <button key={String(v)} onClick={() => setPilotEnabled(v)} style={{
                    padding: "4px 10px", border: "none", cursor: "pointer", fontSize: "12px",
                    background: pilotEnabled === v ? "#1e6ca1" : "transparent",
                    color: "white", fontWeight: pilotEnabled === v ? "bold" : "normal",
                  }}>
                    {v ? "Yes" : "No"}
                  </button>
                ))}
              </div>
            </div>

            {/* Battery minimum */}
            <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
              <span style={{ ...LABEL_STYLE, fontSize: "11px" }}>Min Battery %</span>
              <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <input type="number" min="0" max="80" value={batteryMinPct}
                  onChange={(e) => setBatteryMinPct(Number(e.target.value))}
                  style={INPUT_STYLE}
                />
                <span style={{ fontSize: "11px", opacity: 0.6 }}>%</span>
              </div>
            </div>

            {/* Ticket price */}
            <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
              <span style={{ ...LABEL_STYLE, fontSize: "11px" }}>Ticket Price</span>
              <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <span style={{ fontSize: "11px", opacity: 0.6 }}>$</span>
                <input type="number" min="0" value={ticketPrice}
                  onChange={(e) => setTicketPrice(Number(e.target.value))}
                  style={INPUT_STYLE}
                />
              </div>
            </div>

            {/* Demand scale */}
            <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
              <span style={{ ...LABEL_STYLE, fontSize: "11px" }}>Demand Scale</span>
              <input type="number" min="0.001" step="0.1" value={demandScale}
                onChange={(e) => setDemandScale(Number(e.target.value))}
                style={{ ...INPUT_STYLE, width: "70px" }}
              />
            </div>

            {/* Turnaround time */}
            <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
              <span style={{ ...LABEL_STYLE, fontSize: "11px" }}>Turnaround</span>
              <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <input type="number" min="5" max="60" value={turnaroundMinutes}
                  onChange={(e) => setTurnaroundMinutes(Number(e.target.value))}
                  style={INPUT_STYLE}
                />
                <span style={{ fontSize: "11px", opacity: 0.6 }}>min</span>
              </div>
            </div>

            {/* Minimum passengers */}
            <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
              <span style={{ ...LABEL_STYLE, fontSize: "11px" }}>Min Pax</span>
              <input type="number" min="1" max="4" value={minPassengers}
                onChange={(e) => setMinPassengers(Number(e.target.value))}
                style={{ ...INPUT_STYLE, width: "46px" }}
              />
            </div>

          </div>
        )}

        {/* ── VERTIPORT CONFIG TAB ── */}
        {activeTab === "vertiports" && (
          <div style={{ display: "flex", alignItems: "center", gap: "6px", overflowX: "auto", paddingBottom: "2px" }}>
            {Object.entries(localPorts).map(([portId, vals]) => (
              <div key={portId} style={{
                display: "flex", flexDirection: "column", gap: "4px",
                padding: "4px 8px", borderRadius: "6px",
                border: "1px solid rgba(255,255,255,0.15)",
                background: "rgba(255,255,255,0.05)",
                minWidth: "72px", flexShrink: 0,
              }}>
                <span style={{ fontSize: "11px", fontWeight: "bold", color: "#4fc3f7", textAlign: "center" }}>
                  {portId}
                </span>
                <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                  <span style={{ fontSize: "10px", opacity: 0.6 }}>Pads</span>
                  <input type="number" min="1" max="8" value={vals.totalPads}
                    onChange={(e) => setLocalPorts(p => ({
                      ...p, [portId]: { ...p[portId], totalPads: Number(e.target.value) }
                    }))}
                    style={{ ...INPUT_STYLE, width: "100%", fontSize: "11px", padding: "2px 4px" }}
                  />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                  <span style={{ fontSize: "10px", opacity: 0.6 }}>VTOLs</span>
                  <input type="number" min="1" max="6" value={vals.vtolCount}
                    onChange={(e) => setLocalPorts(p => ({
                      ...p, [portId]: { ...p[portId], vtolCount: Number(e.target.value) }
                    }))}
                    style={{ ...INPUT_STYLE, width: "100%", fontSize: "11px", padding: "2px 4px" }}
                  />
                </div>
              </div>
            ))}
            {Object.keys(localPorts).length > 0 && (
              <button onClick={() => onApplyPortConfig(localPorts)} style={{
                marginLeft: "6px", padding: "6px 14px", borderRadius: "6px",
                background: "#1e6ca1", color: "white", border: "none",
                cursor: "pointer", fontSize: "12px", fontWeight: "bold",
                flexShrink: 0, alignSelf: "center",
              }}>
                Apply
              </button>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
