const Row = ({ label, value }) => (
    <div
        style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "12px",
            padding: "6px 0",
            borderBottom: "1px solid rgba(255,255,255,0.08)",
        }}
    >
        <span style={{ width: "120px", opacity: 0.72 }}>{label}</span>
        <span style={{ fontWeight: "bold", textAlign: "right", flex: 1 }}>{value}</span>
    </div>
);

export default function PortPanel({ node, weather }) {
    if (!node) return null;

    const wx = weather?.[node.id] || {};

    return (
        <div>
            <div
                style={{
                    background: "#0a2d63",
                    color: "white",
                    borderRadius: "14px",
                    padding: "14px 16px",
                    marginBottom: "16px",
                    fontWeight: "bold",
                    fontSize: "24px",
                    lineHeight: 1.2,
                    boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
                }}
            >
                {node.name || node.id} Port
            </div>

            <div
                style={{
                    background: "#082b5b",
                    color: "white",
                    border: "2px solid #1e6ca1",
                    borderRadius: "12px",
                    padding: "16px",
                    marginBottom: "16px",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.18)",
                }}
            >
                {/* <div style={{ fontWeight: "bold", marginBottom: "10px", fontSize: "18px" }}>
                    Port Information
                </div>

                <Row label="Node ID" value={node.id} />
                <Row label="Type" value={node.type} />
                <Row label="Latitude" value={node.lat?.toFixed(4)} />
                <Row label="Longitude" value={node.lon?.toFixed(4)} /> */}

                <div style={{
                    /* marginTop: "14px", */
                    marginBottom: "8px", fontWeight: "bold", fontSize: "18px" }}>
                    Weather
                </div>

                <Row label="Status" value={wx.status ?? "N/A"} />
                <Row label="Wind" value={`${wx.wind_speed_mph ?? "N/A"} mph`} />
                <Row label="Gusts" value={`${wx.wind_gusts_mph ?? "N/A"} mph`} />
                <Row label="Visibility" value={wx.visibility_m != null ? `${wx.visibility_m} m` : "N/A"} />
                <Row label="Precipitation" value={wx.precipitation_mm != null ? `${wx.precipitation_mm} mm` : "N/A"} />
            </div>

            <div
                style={{
                    background: "#082b5b",
                    border: "2px solid #1e6ca1",
                    borderRadius: "12px",
                    minHeight: "220px",
                    padding: "16px",
                    color: "white",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.18)",
                }}
            >
                <div style={{ fontWeight: "bold", fontSize: "18px", marginBottom: "10px" }}>
                    Operations
                </div>
                <div style={{ opacity: 0.72 }}>
                    Queue, standby VTOL count, and future port operations data can go here.
                </div>
            </div>
        </div>
    );
}