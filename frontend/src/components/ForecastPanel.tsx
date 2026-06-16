"use client";

// View B — Forecast Panel. Lets a user query a specific zone and see the
// /forecast response: hotspot probability, predicted count, congestion
// risk, confidence.

import { useState } from "react";

import { getForecast } from "@/lib/api";
import type { ForecastResponse } from "@/lib/types";

const EXAMPLE_CELLS = [
  { label: "Safina Plaza Junction area", h3_cell: "8960145b487ffff" },
  { label: "Elite Junction area", h3_cell: "8960145b553ffff" },
  { label: "Unknown cell (cold start demo)", h3_cell: "ffffffffffffff" },
];

const BAND_COLOR: Record<string, string> = {
  LOW: "text-green-700 bg-green-50 border-green-300",
  MEDIUM: "text-yellow-700 bg-yellow-50 border-yellow-300",
  HIGH: "text-orange-700 bg-orange-50 border-orange-300",
  CRITICAL: "text-red-700 bg-red-50 border-red-300",
};

export default function ForecastPanel() {
  const [h3Cell, setH3Cell] = useState(EXAMPLE_CELLS[0].h3_cell);
  const [vehicleType, setVehicleType] = useState("");
  const [result, setResult] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium">H3 cell ID</label>
        <input
          value={h3Cell}
          onChange={(e) => setH3Cell(e.target.value)}
          className="border border-slate-300 rounded px-3 py-2 text-sm"
        />
        <div className="flex gap-2 flex-wrap">
          {EXAMPLE_CELLS.map((c) => (
            <button
              key={c.h3_cell}
              onClick={() => setH3Cell(c.h3_cell)}
              className="text-xs px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50"
            >
              {c.label}
            </button>
          ))}
        </div>

        <label className="text-sm font-medium mt-2">
          Vehicle type override (optional)
        </label>
        <input
          value={vehicleType}
          onChange={(e) => setVehicleType(e.target.value)}
          placeholder="e.g. LORRY/GOODS VEHICLE"
          className="border border-slate-300 rounded px-3 py-2 text-sm"
        />

        <button
          onClick={() => runForecast(h3Cell)}
          disabled={loading}
          className="self-start mt-2 bg-slate-800 text-white rounded px-4 py-2 text-sm disabled:opacity-50"
        >
          {loading ? "Forecasting…" : "Get forecast"}
        </button>
      </div>

      {error && <div className="text-red-600 text-sm">{error}</div>}

      {result && (
        <div
          className={`border rounded-lg p-4 ${
            BAND_COLOR[result.risk_band] ?? "border-slate-300"
          }`}
        >
          {result.is_cold_start ? (
            <div className="space-y-2">
              <div className="font-semibold">Cold start — no historical data</div>
              <p className="text-sm">{result.note}</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
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
                label="Confidence"
                value={`${(result.confidence * 100).toFixed(1)}%`}
              />
              <Metric label="Risk band" value={result.risk_band} />
              <Metric label="Recommendation" value={result.recommendation} />
              <div className="col-span-2">
                <div className="text-xs font-medium text-slate-500 mb-1">
                  Top contributing factors
                </div>
                <ul className="text-sm space-y-1">
                  {result.top_contributing_factors.map((f) => (
                    <li key={f.factor}>
                      {f.factor}: {f.contribution.toFixed(1)}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}
