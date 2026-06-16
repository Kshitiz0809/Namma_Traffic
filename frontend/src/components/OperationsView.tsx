"use client";

// View C — Operations View. Recommendations queue, alert list, and an
// intervention-type summary (counts per recommendation action), the way
// an operator/dispatcher would actually look at this.

import { useEffect, useState } from "react";

import { getAlerts } from "@/lib/api";
import type { Alert } from "@/lib/types";

const LEVEL_BADGE: Record<Alert["alert_level"], string> = {
  GREEN: "bg-green-100 text-green-800",
  YELLOW: "bg-yellow-100 text-yellow-800",
  ORANGE: "bg-orange-100 text-orange-800",
  RED: "bg-red-100 text-red-800",
};

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

  if (loading) return <div className="text-slate-500">Loading…</div>;
  if (error) return <div className="text-red-600">{error}</div>;

  return (
    <div className="flex flex-col gap-6">
      <section>
        <h3 className="text-sm font-semibold text-slate-700 mb-2">
          Intervention summary
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(interventionCounts).map(([action, count]) => (
            <div
              key={action}
              className="border border-slate-200 rounded-lg p-3 bg-white"
            >
              <div className="text-2xl font-bold">{count}</div>
              <div className="text-xs text-slate-500">{action}</div>
            </div>
          ))}
          <div className="border border-slate-200 rounded-lg p-3 bg-white">
            <div className="text-2xl font-bold">{escalatedCount}</div>
            <div className="text-xs text-slate-500">
              Escalated by rule engine
            </div>
          </div>
        </div>
      </section>

      <section>
        <h3 className="text-sm font-semibold text-slate-700 mb-2">
          Alert queue ({alerts.length})
        </h3>
        <div className="overflow-x-auto border border-slate-200 rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left">
              <tr>
                <th className="px-3 py-2">Level</th>
                <th className="px-3 py-2">Junction</th>
                <th className="px-3 py-2">Risk score</th>
                <th className="px-3 py-2">Probability</th>
                <th className="px-3 py-2">Recommendation</th>
                <th className="px-3 py-2">Escalated</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.zone} className="border-t border-slate-100">
                  <td className="px-3 py-2">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${LEVEL_BADGE[a.alert_level]}`}
                    >
                      {a.alert_level}
                    </span>
                  </td>
                  <td className="px-3 py-2">{a.junction_name}</td>
                  <td className="px-3 py-2">{a.risk_score.toFixed(1)}</td>
                  <td className="px-3 py-2">
                    {(a.probability * 100).toFixed(1)}%
                  </td>
                  <td className="px-3 py-2">{a.recommendation}</td>
                  <td className="px-3 py-2">{a.escalated ? "Yes" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
