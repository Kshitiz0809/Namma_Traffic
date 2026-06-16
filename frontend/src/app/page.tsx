"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import AnalyticsView from "@/components/AnalyticsView";
import ForecastPanel from "@/components/ForecastPanel";
import OperationsView from "@/components/OperationsView";

// Leaflet touches `window` at import time — must be client-only, no SSR.
const LiveRiskMap = dynamic(() => import("@/components/LiveRiskMap"), {
  ssr: false,
  loading: () => (
    <div className="h-[520px] flex items-center justify-center text-slate-400">
      Loading map…
    </div>
  ),
});

const TABS = [
  { id: "map", label: "Live Risk Map" },
  { id: "forecast", label: "Forecast Panel" },
  { id: "operations", label: "Operations View" },
  { id: "analytics", label: "Analytics View" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabId>("map");

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="bg-slate-900 text-white px-6 py-4">
        <h1 className="text-xl font-semibold">
          Parking Intelligence — Decision Support Platform
        </h1>
        <p className="text-sm text-slate-300">
          Parking-Induced Congestion Risk Engine · Bengaluru
        </p>
      </header>

      <nav className="bg-white border-b border-slate-200 px-6">
        <div className="flex gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-slate-800 text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </nav>

      <div className="p-6">
        {activeTab === "map" && <LiveRiskMap />}
        {activeTab === "forecast" && <ForecastPanel />}
        {activeTab === "operations" && <OperationsView />}
        {activeTab === "analytics" && <AnalyticsView />}
      </div>

      <footer className="px-6 py-4 text-xs text-slate-400 border-t border-slate-200">
        Internal-data-only · No external predictive data · Feature set frozen
        (Phase 4 lock) · Models not retrained by this dashboard
      </footer>
    </main>
  );
}
