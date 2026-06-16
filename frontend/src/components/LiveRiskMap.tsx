"use client";

// View A — Live Risk Map. Leaflet + OpenStreetMap tiles (no API key, no
// external predictive data — map tiles are the deployment/UI layer only,
// per the project's internal-data-only constraint, ADR-001).

import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import { getAlerts } from "@/lib/api";
import type { Alert } from "@/lib/types";

const ALERT_COLOR: Record<Alert["alert_level"], string> = {
  GREEN: "#2e7d32",
  YELLOW: "#f9a825",
  ORANGE: "#ef6c00",
  RED: "#c62828",
};

const BENGALURU_CENTER: [number, number] = [12.9716, 77.5946];

export default function LiveRiskMap() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minBand, setMinBand] = useState("MEDIUM");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAlerts({ min_band: minBand, limit: 200 })
      .then((res) => {
        if (!cancelled) {
          setAlerts(res.alerts);
          setError(null);
        }
      })
      .catch((err) => !cancelled && setError(String(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [minBand]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 text-sm">
        <span className="font-medium">Minimum risk band:</span>
        {["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((band) => (
          <button
            key={band}
            onClick={() => setMinBand(band)}
            className={`rounded px-3 py-1 border ${
              minBand === band
                ? "bg-slate-800 text-white border-slate-800"
                : "bg-white text-slate-700 border-slate-300"
            }`}
          >
            {band}
          </button>
        ))}
        {loading && <span className="text-slate-500">Loading…</span>}
        {error && <span className="text-red-600">{error}</span>}
        {!loading && !error && (
          <span className="text-slate-500">{alerts.length} zones shown</span>
        )}
      </div>

      <div className="h-[520px] w-full rounded-lg overflow-hidden border border-slate-200">
        <MapContainer
          center={BENGALURU_CENTER}
          zoom={12}
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {alerts.map((a) => (
            <CircleMarker
              key={a.zone}
              center={[a.latitude, a.longitude]}
              radius={8}
              pathOptions={{
                color: ALERT_COLOR[a.alert_level],
                fillColor: ALERT_COLOR[a.alert_level],
                fillOpacity: 0.7,
              }}
            >
              <Popup>
                <div className="text-sm space-y-1">
                  <div className="font-semibold">{a.junction_name}</div>
                  <div>Zone: {a.zone}</div>
                  <div>
                    Alert:{" "}
                    <span style={{ color: ALERT_COLOR[a.alert_level] }}>
                      {a.alert_level}
                    </span>{" "}
                    ({a.risk_band})
                  </div>
                  <div>Probability: {(a.probability * 100).toFixed(1)}%</div>
                  <div>Risk score: {a.risk_score.toFixed(1)} / 100</div>
                  <div className="font-medium">{a.recommendation}</div>
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      <div className="flex gap-4 text-xs text-slate-600">
        {(Object.keys(ALERT_COLOR) as Alert["alert_level"][]).map((level) => (
          <span key={level} className="flex items-center gap-1">
            <span
              className="inline-block w-3 h-3 rounded-full"
              style={{ background: ALERT_COLOR[level] }}
            />
            {level}
          </span>
        ))}
      </div>
    </div>
  );
}
