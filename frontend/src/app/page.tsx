"use client";

import dynamic from "next/dynamic";
import {
  BarChart3,
  ClipboardList,
  LineChart,
  MapPin,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";

import AnalyticsView from "@/components/AnalyticsView";
import ForecastPanel from "@/components/ForecastPanel";
import OperationsView from "@/components/OperationsView";

// Leaflet touches `window` at import time — must be client-only, no SSR.
const LiveRiskMap = dynamic(() => import("@/components/LiveRiskMap"), {
  ssr: false,
  loading: () => (
    <div className="h-[520px] flex items-center justify-center text-slate-400 card">
      Loading map…
    </div>
  ),
});

const TABS = [
  { id: "map", label: "Live Risk Map", icon: MapPin },
  { id: "forecast", label: "Forecast Panel", icon: LineChart },
  { id: "operations", label: "Operations View", icon: ClipboardList },
  { id: "analytics", label: "Analytics View", icon: BarChart3 },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabId>("map");
  const [forecastCell, setForecastCell] = useState<string | null>(null);
  const [forecastLocation, setForecastLocation] = useState<{ lat: number; lon: number } | null>(
    null
  );

  function handleForecastZone(cell: string) {
    setForecastCell(cell);
    setForecastLocation(null);
    setActiveTab("forecast");
  }

  function handleForecastLocation(lat: number, lon: number) {
    setForecastLocation({ lat, lon });
    setForecastCell(null);
    setActiveTab("forecast");
  }

  return (
    <main className="min-h-screen text-slate-900">
      <header className="bg-gradient-to-r from-slate-900 via-slate-900 to-slate-800 text-white">
        <div className="max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center">
                <ShieldCheck className="w-4.5 h-4.5 text-indigo-300" size={18} />
              </div>
              <h1 className="text-lg font-semibold tracking-tight">
                Parking Intelligence — Decision Support Platform
              </h1>
            </div>
            <p className="text-sm text-slate-400 mt-1 ml-10">
              Parking-Induced Congestion Risk Engine · Bengaluru
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs font-medium text-emerald-300 bg-emerald-500/10 border border-emerald-400/30 rounded-full px-3 py-1.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
            </span>
            System online
          </div>
        </div>
      </header>

      <nav className="bg-white border-b border-slate-200 sticky top-0 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-1">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-3.5 text-sm font-medium border-b-2 transition-all ${
                    active
                      ? "border-indigo-600 text-indigo-700"
                      : "border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50"
                  }`}
                >
                  <Icon size={16} className={active ? "text-indigo-600" : "text-slate-400"} />
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {activeTab === "map" && (
          <LiveRiskMap
            onForecastZone={handleForecastZone}
            onForecastLocation={handleForecastLocation}
          />
        )}
        {activeTab === "forecast" && (
          <ForecastPanel initialCell={forecastCell} initialLocation={forecastLocation} />
        )}
        {activeTab === "operations" && <OperationsView />}
        {activeTab === "analytics" && <AnalyticsView />}
      </div>

      <footer className="max-w-7xl mx-auto px-6 py-5 text-xs text-slate-400 border-t border-slate-200 flex flex-wrap gap-x-2 gap-y-1">
        <span>Internal-data-only</span>
        <span className="text-slate-300">·</span>
        <span>No external predictive data</span>
        <span className="text-slate-300">·</span>
        <span>Feature set frozen (Phase 4 lock)</span>
        <span className="text-slate-300">·</span>
        <span>Models not retrained by this dashboard</span>
      </footer>
    </main>
  );
}
