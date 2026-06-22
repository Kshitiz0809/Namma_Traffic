"use client";

// View C — Operations View. Recommendations queue, alert list, and an
// intervention-type summary (counts per recommendation action), the way
// an operator/dispatcher would actually look at this.

import { ClipboardList, Flame, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";

import { getAlerts } from "@/lib/api";
import type { Alert } from "@/lib/types";

const LEVEL_BADGE: Record<Alert["alert_level"], string> = {
  GREEN: "bg-green-100 text-green-800",
  YELLOW: "bg-yellow-100 text-yellow-800",
  ORANGE: "bg-orange-100 text-orange-800",
  RED: "bg-red-100 text-red-800",
};

const LEVEL_DOT: Record<Alert["alert_level"], string> = {
  GREEN: "bg-green-500",
  YELLOW: "bg-yellow-500",
  ORANGE: "bg-orange-500",
  RED: "bg-red-500",
};

const IMPACT_BADGE: Record<Alert["carriageway_impact_label"], string> = {
  Minimal: "bg-slate-100 text-slate-700",
  Moderate: "bg-yellow-100 text-yellow-800",
  Significant: "bg-orange-100 text-orange-800",
  Severe: "bg-red-100 text-red-800",
};

// ADR-026 — EMERGING: recent activity far exceeds this cell's own
// historical norm (a patrol redirect here changes the outcome). STEADY:
// a known, chronic risk area, presumably already part of routine patrol.
const TREND_BADGE: Record<Alert["hotspot_trend"], string> = {
  EMERGING: "bg-red-100 text-red-800",
  STEADY: "bg-slate-100 text-slate-600",
  STABLE: "bg-slate-50 text-slate-400",
};

const CARD_ACCENT = [
  "from-indigo-500 to-indigo-400",
  "from-sky-500 to-sky-400",
  "from-violet-500 to-violet-400",
  "from-rose-500 to-rose-400",
];

export default function OperationsView() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAlerts({ min_band: "MEDIUM", limit: 100 })
      .then((res) => setAlerts(res.alerts))
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  const interventionCounts = alerts.reduce<Record<string, number>>((acc, a) => {
    acc[a.recommendation] = (acc[a.recommendation] || 0) + 1;
    return acc;
  }, {});

  const escalatedCount = alerts.filter((a) => a.escalated).length;
  const emergingCount = alerts.filter((a) => a.hotspot_trend === "EMERGING").length;

  if (loading)
    return <div className="card p-10 text-center text-slate-400">Loading…</div>;
  if (error)
    return (
      <div className="card p-4 text-red-700 bg-red-50 border-red-200">{error}</div>
    );

  return (
    <div className="flex flex-col gap-6">
      <section>
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">
          <TrendingUp size={16} className="text-indigo-500" />
          Intervention summary
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(interventionCounts).map(([action, count], i) => (
            <div key={action} className="card p-4 relative overflow-hidden">
              <div
                className={`absolute top-0 left-0 h-1 w-full bg-gradient-to-r ${CARD_ACCENT[i % CARD_ACCENT.length]}`}
              />
              <div className="text-2xl font-bold text-slate-800">{count}</div>
              <div className="text-xs text-slate-500 mt-0.5">{action}</div>
            </div>
          ))}
          <div className="card p-4 relative overflow-hidden">
            <div className="absolute top-0 left-0 h-1 w-full bg-gradient-to-r from-red-500 to-orange-400" />
            <div className="text-2xl font-bold text-slate-800">{escalatedCount}</div>
            <div className="text-xs text-slate-500 mt-0.5">
              Escalated by rule engine
            </div>
          </div>
          <div className="card p-4 relative overflow-hidden">
            <div className="absolute top-0 left-0 h-1 w-full bg-gradient-to-r from-red-600 to-red-400" />
            <div className="flex items-center gap-1.5">
              <Flame size={16} className="text-red-500" />
              <div className="text-2xl font-bold text-slate-800">{emergingCount}</div>
            </div>
            <div className="text-xs text-slate-500 mt-0.5">
              Emerging (new spike, not chronic)
            </div>
          </div>
        </div>
      </section>

      <section>
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">
          <ClipboardList size={16} className="text-indigo-500" />
          Alert queue ({alerts.length})
        </h3>
        <div className="card overflow-x-auto">
          <table className="w-full text-sm text-slate-900">
            <thead className="bg-slate-50 text-left text-slate-500 font-semibold text-xs uppercase tracking-wide">
              <tr>
                <th className="px-4 py-3">Level</th>
                <th className="px-4 py-3">Junction</th>
                <th className="px-4 py-3">Risk score</th>
                <th className="px-4 py-3">Probability</th>
                <th className="px-4 py-3" title="Estimated carriageway width consumed by concurrently parked vehicles — a proxy, not measured traffic flow">
                  Carriageway impact
                </th>
                <th className="px-4 py-3">Recommendation</th>
                <th className="px-4 py-3">Escalated</th>
                <th className="px-4 py-3" title="EMERGING: activity well above this cell's own historical norm. STEADY: a known, chronic risk area.">
                  Trend
                </th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.zone} className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${LEVEL_BADGE[a.alert_level]}`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${LEVEL_DOT[a.alert_level]}`} />
                      {a.alert_level}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-medium">{a.junction_name}</td>
                  <td className="px-4 py-3">{a.risk_score.toFixed(1)}</td>
                  <td className="px-4 py-3">
                    {(a.probability * 100).toFixed(1)}%
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium ${IMPACT_BADGE[a.carriageway_impact_label]}`}
                      title={`carriageway_impact_score = ${a.carriageway_impact_score}`}
                    >
                      {a.carriageway_impact_label}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{a.recommendation}</td>
                  <td className="px-4 py-3">
                    {a.escalated ? (
                      <span className="text-red-600 font-medium">Yes</span>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${TREND_BADGE[a.hotspot_trend]}`}>
                      {a.hotspot_trend}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-slate-400 mt-2 px-1">
          Carriageway impact estimates how much road width is concurrently
          consumed by parked vehicles (vehicle-size-weighted, dataset-only
          proxy) — not measured traffic speed/volume, which this dataset
          doesn&apos;t contain.
        </p>
      </section>
    </div>
  );
}
