// Thin fetch wrappers around the backend API (docs/api_contract.md).
// Base URL is an env var so the same build works against a local backend
// (dev) or a deployed Render URL (production) without code changes.

import type {
  AlertsResponse,
  ForecastResponse,
  HealthResponse,
  MetricsResponse,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function getHealth() {
  return getJson<HealthResponse>("/health");
}

export function getForecast(params: {
  h3_cell?: string;
  lat?: number;
  lon?: number;
  vehicle_type?: string;
}) {
  const qs = new URLSearchParams();
  if (params.h3_cell) qs.set("h3_cell", params.h3_cell);
  if (params.lat !== undefined) qs.set("lat", String(params.lat));
  if (params.lon !== undefined) qs.set("lon", String(params.lon));
  if (params.vehicle_type) qs.set("vehicle_type", params.vehicle_type);
  return getJson<ForecastResponse>(`/forecast?${qs.toString()}`);
}

export function getAlerts(params: {
  level?: string;
  min_band?: string;
  limit?: number;
} = {}) {
  const qs = new URLSearchParams();
  if (params.level) qs.set("level", params.level);
  if (params.min_band) qs.set("min_band", params.min_band);
  qs.set("limit", String(params.limit ?? 100));
  return getJson<AlertsResponse>(`/alerts?${qs.toString()}`);
}

export function getMetrics() {
  return getJson<MetricsResponse>("/metrics");
}

export { API_BASE_URL };
