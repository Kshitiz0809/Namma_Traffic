"use client";

// View D — Analytics View. Risk distribution + model metrics from
// /metrics (all real numbers from docs/leaderboard.csv, never recomputed
// by this page) plus a live risk-band breakdown.

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getMetrics } from "@/lib/api";
import type { MetricsResponse } from "@/lib/types";

const BAND_COLOR: Record<string, string> = {
  LOW: "#2e7d32",
  MEDIUM: "#f9a825",
  HIGH: "#ef6c00",
  CRITICAL: "#c62828",
};

export default function AnalyticsView() {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMetrics()
      .then(setMetrics)
      .catch((err) => setError(String(err)));
  }, []);

  if (error) return <div className="text-red-600">{error}</div>;
  if (!metrics) return <div className="text-slate-500">Loading…</div>;

  const bandData = Object.entries(metrics.live_risk_distribution.band_counts).map(
    ([band, count]) => ({ band, count })
  );
  const modelData = metrics.model.val_comparison;

  return (
    <div className="flex flex-col gap-8">
      <section>
        <h3 className="text-sm font-semibold text-slate-700 mb-2">
          Live risk distribution ({metrics.live_risk_distribution.total_cells}{" "}
          zones)
        </h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={bandData}
                dataKey="count"
                nameKey="band"
                cx="50%"
                cy="50%"
                outerRadius={90}
                label={(entry: { name?: string; value?: number }) =>
                  `${entry.name}: ${entry.value}`
                }
              >
                {bandData.map((entry) => (
                  <Cell key={entry.band} fill={BAND_COLOR[entry.band]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section>
        <h3 className="text-sm font-semibold text-slate-700 mb-2">
          Model comparison (validation PR-AUC) — winner: {metrics.model.winner}
        </h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={modelData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="model" />
              <YAxis domain={[0, 1]} />
              <Tooltip />
              <Bar dataKey="pr_auc" fill="#3b6ea5" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Operating threshold" value={metrics.operating_threshold} />
        <StatCard
          label="Operational horizon"
          value={`${metrics.operational_horizon_minutes} min`}
        />
        <StatCard
          label="Spatial holdout"
          value={metrics.spatial_robustness.holdout_verdict}
          warn={metrics.spatial_robustness.holdout_verdict === "FAIL"}
        />
        <StatCard
          label="Spatial abstraction"
          value={metrics.spatial_robustness.abstraction_verdict}
        />
      </section>

      <section className="text-xs text-slate-500 border-t border-slate-200 pt-3">
        Feature set: {metrics.feature_set} · Data sources: {metrics.data_sources}
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
  warn,
}: {
  label: string;
  value: string | number;
  warn?: boolean;
}) {
  return (
    <div
      className={`border rounded-lg p-3 ${
        warn ? "border-red-300 bg-red-50" : "border-slate-200 bg-white"
      }`}
    >
      <div className="text-xl font-bold">{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}
