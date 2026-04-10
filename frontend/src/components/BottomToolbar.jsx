export default function BottomToolbar({
  selectedDate,
  setSelectedDate,
  startHour,
  setStartHour,
  endHour,
  setEndHour,
  currentHour,
  setCurrentHour,
  showWeather,
  setShowWeather,
  showPopulation,
  setShowPopulation,
  showFlights,
  setShowFlights,

  showHazardRegions,
  setShowHazardRegions,

  initialize,
  isPreloading,
}) {
  return (
    <div
      style={{
        height: "110px",
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

          <div>
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
              style={{
                marginLeft: "8px",
                padding: "4px 8px",
                borderRadius: "6px",
                background: "#1e6ca1",
                color: "white",
                border: "none",
                cursor: "pointer",
              }}
            >
              {isPreloading ? "Loading..." : "Initialize"}
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
          {/*           <label>
            <input
              type="checkbox"
              checked={usePreloadedWeather}
              onChange={() => setUsePreloadedWeather(!usePreloadedWeather)}
              style={{ marginRight: "6px" }}
            />
            Preloaded Mode
          </label> */}
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
              checked={showFlights}
              onChange={() => setShowFlights(!showFlights)}
              style={{ marginRight: "6px" }}
            />
            Flights
          </label>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <span>{currentHour}:00</span>

        <input
          type="range"
          min={startHour}
          max={endHour}
          value={currentHour}
          onChange={(e) => setCurrentHour(Number(e.target.value))}
          style={{ flex: 1 }}
        />

        <span>{endHour}:00</span>
      </div>
    </div>
  );
}