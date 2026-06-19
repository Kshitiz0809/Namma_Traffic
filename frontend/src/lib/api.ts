// Thin fetch wrappers around the backend API (docs/api_contract.md).
// Base URL is an env var so the same build works against a local backend
// (dev) or a deployed Render URL (production) without code changes.

import type {
  AlertsResponse,
  AppendResult,
  ForecastResponse,
  HealthResponse,
  MetricsResponse,
  ReplayResponse,
  RetrainJob,
  StagingDetail,
  StagingRecord,
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

export function getReplay(scenario: string) {
  return getJson<ReplayResponse>(`/replay/${scenario}`);
}

// --- Admin API (retraining pipeline) ---
// Every call here sends X-Admin-Token; the backend returns 503 if
// ADMIN_API_TOKEN isn't configured server-side, or 401 if the token is wrong.
async function adminFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { ...(init.headers || {}), "X-Admin-Token": token },
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function uploadStagingFile(file: File, token: string) {
  const form = new FormData();
  form.append("file", file);
  return adminFetch<StagingRecord>("/admin/staging/upload", token, { method: "POST", body: form });
}

export function listStaging(token: string) {
  return adminFetch<{ staged: StagingRecord[] }>("/admin/staging", token);
}

export function getStaging(stagingId: string, token: string) {
  return adminFetch<StagingDetail>(`/admin/staging/${stagingId}`, token);
}

export function approveStaging(stagingId: string, token: string) {
  return adminFetch<AppendResult>(`/admin/staging/${stagingId}/approve`, token, { method: "POST" });
}

export function rejectStaging(stagingId: string, token: string, reason?: string) {
  const qs = reason ? `?reason=${encodeURIComponent(reason)}` : "";
  return adminFetch<StagingRecord>(`/admin/staging/${stagingId}/reject${qs}`, token, { method: "POST" });
}

export function triggerRetrain(token: string) {
  return adminFetch<{ job_id: string; status: string }>("/admin/retrain", token, { method: "POST" });
}

export function getRetrainStatus(jobId: string, token: string) {
  return adminFetch<RetrainJob>(`/admin/retrain/${jobId}`, token);
}

export { API_BASE_URL };
