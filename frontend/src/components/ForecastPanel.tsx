"use client";

// View B — Forecast Panel. Lets a user query a specific zone and see the
// /forecast response: hotspot probability, predicted count, congestion
// risk, confidence.

import {
  AlertTriangle,
  Gauge,
  Search,
  Snowflake,
  Truck,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { getForecast } from "@/lib/api";
import type { ForecastResponse } from "@/lib/types";

const EXAMPLE_CELLS = [
  { label: "Safina Plaza Junction area", h3_cell: "8960145b487ffff" },
  { label: "Elite Junction area", h3_cell: "8960145b553ffff" },
  { label: "Unknown cell (cold start demo)", h3_cell: "ffffffffffffff" },
];

const BAND_STYLE: Record<string, { border: string; bg: string; text: string; dot: string }> = {
  LOW: { border: "border-green-200", bg: "bg-green-50", text: "text-green-800", dot: "bg-green-500" },
  MEDIUM: { border: "border-yellow-200", bg: "bg-yellow-50", text: "text-yellow-800", dot: "bg-yellow-500" },
  HIGH: { border: "border-orange-200", bg: "bg-orange-50", text: "text-orange-800", dot: "bg-orange-500" },
  CRITICAL: { border: "border-red-200", bg: "bg-red-50", text: "text-red-800", dot: "bg-red-500" },
};

const IMPACT_BAR_COLOR: Record<string, string> = {
  Minimal: "bg-slate-400",
  Moderate: "bg-yellow-500",
  Significant: "bg-orange-500",
  Severe: "bg-red-500",
};

export default function ForecastPanel({
  initialCell,
}: {
  initialCell?: string | null;
} = {}) {
  const [h3Cell, setH3Cell] = useState(initialCell || EXAMPLE_CELLS[0].h3_cell);
  const [vehicleType, setVehicleType] = useState("");
  const [result, setResult] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastAppliedCell = useRef<string | null>(null);

  // Jumped here from a map marker ("Forecast this zone") — populate the
  // cell field and run the forecast immediately instead of making the user
  // re-type the H3 ID.
  useEffect(() => {
    if (initialCell && initialCell !== lastAppliedCell.current) {
      lastAppliedCell.current = initialCell;
      setH3Cell(initialCell);
      runForecast(initialCell);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCell]);

  async function runForecast(cell: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await getForecast({
        h3_cell: cell,
        vehicle_type: vehicleType || undefined,
      });
      setResult(res);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  const band = result ? BAND_STYLE[result.risk_band] : null;

  return (
    <div className="grid lg:grid-cols-[380px_1fr] gap-6 items-start">
      <div className="card p-5 flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center">
            <Search size={16} className="text-indigo-600" />
          </div>
          <h2 className="font-semibold text-slate-800">Query a zone</h2>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
            H3 cell ID
          </label>
          <input
            value={h3Cell}
            onChange={(e) => setH3Cell(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400"
          />
          <div className="flex gap-1.5 flex-wrap mt-1">
            {EXAMPLE_CELLS.map((c) => (
              <button
                key={c.h3_cell}
                onClick={() => setH3Cell(c.h3_cell)}
                className="text-xs px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-slate-600 hover:bg-indigo-50 hover:border-indigo-200 hover:text-indigo-700 transition-colors"
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
            Vehicle type override (optional)
          </label>
          <input
            value={vehicleType}
            onChange={(e) => setVehicleType(e.target.value)}
            placeholder="e.g. LORRY/GOODS VEHICLE"
            className="border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400"
          />
        </div>

        <button
          onClick={() => runForecast(h3Cell)}
          disabled={loading}
          className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-4 py-2.5 text-sm font-medium disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
        >
          <Gauge size={16} />
          {loading ? "Forecasting…" : "Get forecast"}
        </button>

        {error && (
          <div className="text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm">
            {error}
          </div>
        )}
      </div>

      <div>
        {!result && !error && (
          <div className="card p-10 text-center text-slate-400 text-sm">
            Run a forecast to see hotspot probability, predicted count,
            risk band, and carriageway impact for this zone.
          </div>
        )}

        {result && result.is_cold_start && (
          <div className="card p-6 border-slate-200">
            <div className="flex items-center gap-2 text-slate-700 font-semibold mb-2">
              <Snowflake size={18} className="text-sky-500" />
              Cold start — no historical data
            </div>
            <p className="text-sm text-slate-600">{result.note}</p>
          </div>
        )}

        {result && !result.is_cold_start && band && (
          <div className="flex flex-col gap-4">
            <div className={`card border-2 ${band.border} ${band.bg} p-5`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`w-2.5 h-2.5 rounded-full ${band.dot}`} />
                  <span className={`text-sm font-bold uppercase tracking-wide ${band.text}`}>
                    {result.risk_band} risk
                  </span>
                </div>
                <span className="text-xs text-slate-500">
                  Confidence {(result.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <div className="mt-3 flex items-start gap-2">
                <AlertTriangle size={16} className={`${band.text} mt-0.5 flex-shrink-0`} />
                <p className={`text-sm font-medium ${band.text}`}>{result.recommendation}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Metric
                label="Hotspot probability"
                value={`${((result.hotspot_probability ?? 0) * 100).toFixed(1)}%`}
              />
              <Metric
                label="Predicted count (60m)"
                value={result.predicted_count?.toFixed(1) ?? "—"}
              />
              <Metric
                label="Congestion risk"
                value={`${result.congestion_risk.toFixed(1)} / 100`}
              />
              <Metric
                label="Carriageway impact"
                value={result.carriageway_impact_label}
                sub={`score ${result.carriageway_impact_score.toFixed(1)}`}
                icon={<Truck size={14} className="text-slate-400" />}
                barColor={IMPACT_BAR_COLOR[result.carriageway_impact_label]}
                barPct={Math.min(100, (result.carriageway_impact_score / 10) * 100)}
              />
            </div>

            <div className="card p-5">
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                Top contributing factors
              </div>
              <ul className="space-y-2">
                {result.top_contributing_factors.map((f) => (
                  <li key={f.factor} className="flex items-center gap-3 text-sm">
                    <span className="text-slate-700 flex-1">{f.factor}</span>
                    <span className="font-mono text-xs text-slate-500">
                      {f.contribution.toFixed(1)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <p className="text-xs text-slate-400 px-1">
              Carriageway impact is a vehicle-size-weighted, dataset-only
              proxy for road-width consumed by concurrently parked
              vehicles — not measured traffic speed/volume.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  icon,
  barColor,
  barPct,
}: {
  label: string;
  value: string;
  sub?: string;
  icon?: React.ReactNode;
  barColor?: string;
  barPct?: number;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 mb-1">
        {icon}
        {label}
      </div>
      <div className="text-xl font-bold text-slate-800">{value}</div>
      {sub && <div className="text-xs text-slate-400 mt-0.5">{sub}</div>}
      {barColor && barPct !== undefined && (
        <div className="mt-2 h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
          <div
            className={`h-full ${barColor} rounded-full`}
            style={{ width: `${barPct}%` }}
          />
        </div>
      )}
    </div>
  );
}
