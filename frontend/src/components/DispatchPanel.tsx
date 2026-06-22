"use client";

// View F — Dispatch Panel (ADR-026). Turns the live risk snapshot into an
// actual patrol assignment: given N available units, shows which unit
// should go to which hotspot to maximize distinct-hotspot coverage,
// instead of leaving "where do I send my patrols" as a manual judgment
// call. See backend/app/models/dispatch.py.

import { Navigation, Radio, Target } from "lucide-react";
import { useState } from "react";

import { getDispatchPlan } from "@/lib/api";
import type { DispatchPlan } from "@/lib/types";

const BAND_BADGE: Record<string, string> = {
  LOW: "bg-green-100 text-green-800",
  MEDIUM: "bg-yellow-100 text-yellow-800",
  HIGH: "bg-orange-100 text-orange-800",
  CRITICAL: "bg-red-100 text-red-800",
};

export default function DispatchPanel() {
  const [nUnits, setNUnits] = useState(5);
  const [minBand, setMinBand] = useState("MEDIUM");
  const [plan, setPlan] = useState<DispatchPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCompute() {
    setLoading(true);
    setError(null);
    try {
      const result = await getDispatchPlan(nUnits, minBand);
      setPlan(result);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="card p-5 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center">
            <Navigation size={16} className="text-indigo-600" />
          </div>
          <h2 className="font-semibold text-slate-800">Patrol dispatch optimizer</h2>
        </div>
        <p className="text-xs text-slate-500">
          Assigns each available unit to a distinct hotspot, minimizing
          total travel distance — instead of every unit converging on the
          single highest-risk cell. Unit origins are each police
          station&apos;s own historical violation centroid; ETA assumes a
          {" "}{25} km/h urban average (straight-line distance, no external
          routing API).
        </p>
        <div className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500">Available units</label>
            <input
              type="number"
              min={1}
              max={50}
              value={nUnits}
              onChange={(e) => setNUnits(Number(e.target.value))}
              className="border border-slate-300 rounded-lg px-3 py-2 text-sm w-28 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500">Minimum risk band</label>
            <select
              value={minBand}
              onChange={(e) => setMinBand(e.target.value)}
              className="border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400"
            >
              <option value="LOW">LOW+</option>
              <option value="MEDIUM">MEDIUM+</option>
              <option value="HIGH">HIGH+</option>
              <option value="CRITICAL">CRITICAL only</option>
            </select>
          </div>
          <button
            onClick={handleCompute}
            disabled={loading}
            className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-4 py-2.5 text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {loading ? "Computing…" : "Compute dispatch plan"}
          </button>
        </div>
        {error && (
          <div className="text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm">
            {error}
          </div>
        )}
      </div>

      {plan && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="card p-4">
              <div className="text-2xl font-bold text-slate-800">{plan.summary.distinct_hotspots_covered}</div>
              <div className="text-xs text-slate-500 mt-0.5">Distinct hotspots covered</div>
            </div>
            <div className="card p-4">
              <div className="text-2xl font-bold text-green-700">{plan.summary.total_risk_covered.toFixed(1)}</div>
              <div className="text-xs text-slate-500 mt-0.5">
                Total risk covered (vs {plan.summary.naive_single_target_risk_covered.toFixed(1)} naive)
              </div>
            </div>
            <div className="card p-4">
              <div className="text-2xl font-bold text-slate-800">{plan.summary.avg_eta_minutes.toFixed(1)} min</div>
              <div className="text-xs text-slate-500 mt-0.5">Average ETA per unit</div>
            </div>
            <div className="card p-4">
              <div className="text-2xl font-bold text-slate-800">{plan.summary.total_distance_km.toFixed(1)} km</div>
              <div className="text-xs text-slate-500 mt-0.5">Total travel distance</div>
            </div>
          </div>

          <div className="card overflow-x-auto">
            <table className="w-full text-sm text-slate-900">
              <thead className="bg-slate-50 text-left text-slate-500 font-semibold text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3">Unit</th>
                  <th className="px-4 py-3">
                    <span className="inline-flex items-center gap-1"><Radio size={12} /> From station</span>
                  </th>
                  <th className="px-4 py-3">
                    <span className="inline-flex items-center gap-1"><Target size={12} /> To hotspot</span>
                  </th>
                  <th className="px-4 py-3">Risk band</th>
                  <th className="px-4 py-3">Risk score</th>
                  <th className="px-4 py-3">Distance</th>
                  <th className="px-4 py-3">ETA</th>
                </tr>
              </thead>
              <tbody>
                {plan.assignments.map((a) => (
                  <tr key={a.unit_id} className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 font-medium">#{a.unit_id}</td>
                    <td className="px-4 py-3">{a.origin_station}</td>
                    <td className="px-4 py-3 font-medium">{a.target_junction}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${BAND_BADGE[a.target_risk_band]}`}>
                        {a.target_risk_band}
                      </span>
                    </td>
                    <td className="px-4 py-3">{a.target_risk_score.toFixed(1)}</td>
                    <td className="px-4 py-3">{a.distance_km.toFixed(2)} km</td>
                    <td className="px-4 py-3">{a.eta_minutes.toFixed(1)} min</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
