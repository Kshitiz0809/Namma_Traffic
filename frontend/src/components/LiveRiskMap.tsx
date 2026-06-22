"use client";

// View A — Live Risk Map. Leaflet + OpenStreetMap tiles (no API key, no
// external predictive data — map tiles are the deployment/UI layer only,
// per the project's internal-data-only constraint, ADR-001).
//
// Phase 7 addition: a "Replay" mode that scrubs through a REAL historical
// sequence (Elite Junction, 2023-12-23 — see app/serving/replay_service.py)
// instead of only showing a frozen snapshot. This is explicitly labeled as
// a replay of real past data, never implied to be a live feed — there is no
// live streaming pipeline yet (see docs/deployment.md).

import {
  History,
  MapPin,
  Pause,
  Play,
  RotateCcw,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

import { getAlerts, getReplay } from "@/lib/api";
import type { Alert, ReplayPoint, ReplayResponse } from "@/lib/types";

const ALERT_COLOR: Record<Alert["alert_level"], string> = {
  GREEN: "#16a34a",
  YELLOW: "#eab308",
  ORANGE: "#f97316",
  RED: "#dc2626",
};

const BAND_COLOR: Record<ReplayPoint["risk_band"], string> = {
  LOW: ALERT_COLOR.GREEN,
  MEDIUM: ALERT_COLOR.YELLOW,
  HIGH: ALERT_COLOR.ORANGE,
  CRITICAL: ALERT_COLOR.RED,
};

const BENGALURU_CENTER: [number, number] = [12.9716, 77.5946];
const PLAYBACK_INTERVAL_MS = 450;

function RecenterMap({ center, zoom }: { center: [number, number]; zoom?: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, zoom ?? map.getZoom());
  }, [center, zoom, map]);
  return null;
}

function ClickCapture({ onClick }: { onClick: (lat: number, lon: number) => void }) {
  useMapEvents({
    click: (e) => onClick(e.latlng.lat, e.latlng.lng),
  });
  return null;
}

function LiveMode({
  onForecastZone,
  onForecastLocation,
  focusLocation,
}: {
  onForecastZone?: (cell: string) => void;
  onForecastLocation?: (lat: number, lon: number) => void;
  focusLocation?: { lat: number; lon: number; label?: string } | null;
}) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minBand, setMinBand] = useState("MEDIUM");
  const [clickedPoint, setClickedPoint] = useState<{ lat: number; lon: number } | null>(null);

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
    <div className="flex flex-col gap-4">
      <div className="card p-3 flex items-center gap-3 flex-wrap text-sm">
        <span className="font-semibold text-slate-600 flex-shrink-0">
          Minimum risk band
        </span>
        <div className="flex gap-1.5">
          {["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((band) => (
            <button
              key={band}
              onClick={() => setMinBand(band)}
              className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                minBand === band
                  ? "bg-indigo-600 text-white border-indigo-600"
                  : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
              }`}
            >
              {band}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        {loading && <span className="text-slate-400">Loading…</span>}
        {error && <span className="text-red-600">{error}</span>}
        {!loading && !error && (
          <span className="text-slate-400 text-xs">{alerts.length} zones shown</span>
        )}
      </div>

      {onForecastLocation && (
        <p className="text-xs text-slate-400 px-1">
          Click anywhere on the map to forecast that exact location, even
          outside the markers shown above.
        </p>
      )}

      <div className="h-[520px] w-full rounded-xl overflow-hidden border border-slate-200 shadow-sm">
        <MapContainer center={BENGALURU_CENTER} zoom={12} style={{ height: "100%", width: "100%" }}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {onForecastLocation && (
            <ClickCapture onClick={(lat, lon) => setClickedPoint({ lat, lon })} />
          )}
          {focusLocation && (
            <>
              <RecenterMap center={[focusLocation.lat, focusLocation.lon]} zoom={16} />
              <CircleMarker
                center={[focusLocation.lat, focusLocation.lon]}
                radius={14}
                pathOptions={{ color: "#4f46e5", fillColor: "#4f46e5", fillOpacity: 0.15, weight: 3, dashArray: "4 4" }}
              >
                <Popup>
                  <div className="text-sm font-medium">{focusLocation.label || "Location"}</div>
                </Popup>
              </CircleMarker>
            </>
          )}
          {clickedPoint && (
            <CircleMarker
              center={[clickedPoint.lat, clickedPoint.lon]}
              radius={9}
              pathOptions={{ color: "#4f46e5", fillColor: "#4f46e5", fillOpacity: 0.5 }}
            >
              <Popup>
                <div className="text-sm space-y-1.5">
                  <div className="font-semibold">Clicked location</div>
                  <div className="font-mono text-xs">
                    {clickedPoint.lat.toFixed(5)}, {clickedPoint.lon.toFixed(5)}
                  </div>
                  <p className="text-xs text-slate-500">
                    No H3 cell ID needed — the backend resolves this point to
                    its H3 cell and forecasts it directly.
                  </p>
                  {onForecastLocation && (
                    <button
                      onClick={() => onForecastLocation(clickedPoint.lat, clickedPoint.lon)}
                      className="mt-1 text-xs px-2 py-1 rounded bg-indigo-600 text-white"
                    >
                      Forecast this location →
                    </button>
                  )}
                </div>
              </Popup>
            </CircleMarker>
          )}
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
                    <span style={{ color: ALERT_COLOR[a.alert_level] }}>{a.alert_level}</span>{" "}
                    ({a.risk_band})
                  </div>
                  <div>Probability: {(a.probability * 100).toFixed(1)}%</div>
                  <div>Risk score: {a.risk_score.toFixed(1)} / 100</div>
                  <div>
                    Carriageway impact: {a.carriageway_impact_label} ({a.carriageway_impact_score})
                  </div>
                  <div className="font-medium">{a.recommendation}</div>
                  {onForecastZone && (
                    <button
                      onClick={() => onForecastZone(a.zone)}
                      className="mt-1 text-xs px-2 py-1 rounded bg-indigo-600 text-white"
                    >
                      Forecast this zone →
                    </button>
                  )}
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      <div className="card px-4 py-2.5 flex gap-5 text-xs text-slate-600">
        {(Object.keys(ALERT_COLOR) as Alert["alert_level"][]).map((level) => (
          <span key={level} className="flex items-center gap-1.5">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full"
              style={{ background: ALERT_COLOR[level] }}
            />
            {level}
          </span>
        ))}
      </div>
    </div>
  );
}

function ReplayMode() {
  const [data, setData] = useState<ReplayResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    getReplay("growth")
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => !cancelled && setError(String(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!playing || !data) return;
    intervalRef.current = setInterval(() => {
      setIndex((i) => {
        if (i >= data.points.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, PLAYBACK_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing, data]);

  if (loading)
    return <div className="card p-10 text-center text-slate-400">Loading real replay sequence…</div>;
  if (error)
    return <div className="card p-4 text-red-700 bg-red-50 border-red-200">{error}</div>;
  if (!data || data.points.length === 0)
    return <div className="card p-10 text-center text-slate-400">No replay data.</div>;

  const point = data.points[index];
  const trail = data.points.slice(0, index + 1);
  const atEnd = index >= data.points.length - 1;
  const progressPct = (index / (data.points.length - 1)) * 100;

  return (
    <div className="flex flex-col gap-4">
      <div className="card border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 flex items-start gap-2">
        <History size={16} className="mt-0.5 flex-shrink-0 text-amber-600" />
        <div>
          <span className="font-semibold">{data.label}</span> — replaying real,
          historical events through the frozen models. This is NOT a live
          feed; there is no real-time streaming pipeline yet.
        </div>
      </div>

      <div className="card p-3 flex items-center gap-3">
        <button
          onClick={() => {
            if (atEnd) setIndex(0);
            setPlaying((p) => !p);
          }}
          className="flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium bg-indigo-600 hover:bg-indigo-700 text-white transition-colors"
        >
          {playing ? (
            <Pause size={14} />
          ) : atEnd ? (
            <RotateCcw size={14} />
          ) : (
            <Play size={14} />
          )}
          {playing ? "Pause" : atEnd ? "Replay again" : "Play"}
        </button>
        <div className="flex-1 flex flex-col gap-1">
          <input
            type="range"
            min={0}
            max={data.points.length - 1}
            value={index}
            onChange={(e) => {
              setPlaying(false);
              setIndex(Number(e.target.value));
            }}
            className="w-full accent-indigo-600"
          />
          <div className="h-1 w-full bg-slate-100 rounded-full overflow-hidden -mt-2.5 pointer-events-none">
            <div
              className="h-full bg-indigo-200"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
        <span className="text-slate-400 text-xs flex-shrink-0 font-mono">
          {index + 1} / {data.points.length}
        </span>
      </div>

      <div className="h-[520px] w-full rounded-xl overflow-hidden border border-slate-200 shadow-sm">
        <MapContainer
          center={[point.latitude, point.longitude]}
          zoom={15}
          style={{ height: "100%", width: "100%" }}
        >
          <RecenterMap center={[point.latitude, point.longitude]} zoom={15} />
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {trail.map((p, i) => {
            const isCurrent = i === trail.length - 1;
            const recency = (i + 1) / trail.length;
            return (
              <CircleMarker
                key={`${p.timestamp}-${i}`}
                center={[p.latitude, p.longitude]}
                radius={isCurrent ? 12 : 5}
                pathOptions={{
                  color: BAND_COLOR[p.risk_band],
                  fillColor: BAND_COLOR[p.risk_band],
                  fillOpacity: isCurrent ? 0.9 : 0.15 + 0.25 * recency,
                  weight: isCurrent ? 3 : 1,
                }}
              >
                {isCurrent && (
                  <Popup>
                    <div className="text-sm space-y-1">
                      <div className="font-semibold">{p.junction_name}</div>
                      <div>{new Date(p.timestamp).toLocaleString()}</div>
                      <div>Vehicle: {p.vehicle_type}</div>
                      <div>Risk score: {p.risk_score.toFixed(1)} ({p.risk_band})</div>
                      <div>
                        Carriageway impact: {p.carriageway_impact_label} ({p.carriageway_impact_score})
                      </div>
                      <div className="font-medium">{p.recommendation}</div>
                    </div>
                  </Popup>
                )}
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <Stat label="Time" value={new Date(point.timestamp).toLocaleTimeString()} />
        <Stat label="Risk score" value={`${point.risk_score.toFixed(1)} (${point.risk_band})`} />
        <Stat label="Violations (last 15m)" value={point.violations_last_15m.toFixed(0)} />
        <Stat
          label="Carriageway impact"
          value={`${point.carriageway_impact_label} (${point.carriageway_impact_score})`}
        />
        <Stat label="Vehicle" value={point.vehicle_type} />
        <Stat label="Recommendation" value={point.recommendation} />
        <Stat label="Escalated" value={point.escalated ? "Yes" : "No"} />
        <Stat label="Hotspot intensity" value={point.rolling_hotspot_intensity.toFixed(1)} />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="font-semibold text-slate-800 text-sm mt-0.5">{value}</div>
    </div>
  );
}

export default function LiveRiskMap({
  onForecastZone,
  onForecastLocation,
  focusLocation,
}: {
  onForecastZone?: (cell: string) => void;
  onForecastLocation?: (lat: number, lon: number) => void;
  focusLocation?: { lat: number; lon: number; label?: string } | null;
} = {}) {
  const [mode, setMode] = useState<"live" | "replay">("live");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2 bg-slate-100 p-1 rounded-full w-fit">
        <button
          onClick={() => setMode("live")}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
            mode === "live"
              ? "bg-white text-indigo-700 shadow-sm"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          <MapPin size={14} />
          Live snapshot
        </button>
        <button
          onClick={() => setMode("replay")}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
            mode === "replay"
              ? "bg-white text-indigo-700 shadow-sm"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          <History size={14} />
          Replay: real surge (2023-12-23)
        </button>
      </div>
      {mode === "live" ? (
        <LiveMode onForecastZone={onForecastZone} onForecastLocation={onForecastLocation} focusLocation={focusLocation} />
      ) : (
        <ReplayMode />
      )}
    </div>
  );
}
