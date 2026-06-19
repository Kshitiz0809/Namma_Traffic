// TypeScript types mirroring docs/api_contract.md exactly. Kept hand-written
// rather than auto-generated from the OpenAPI schema — the API surface is
// small (4 endpoints) and stable (frozen models, Phase 4 lock), so codegen
// tooling would add more setup cost than it saves here.

export interface ContributingFactor {
  factor: string;
  contribution: number;
}

export interface ForecastResponse {
  zone: string;
  hotspot_probability: number | null;
  predicted_count: number | null;
  congestion_risk: number;
  risk_band: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  recommendation: string;
  confidence: number;
  top_contributing_factors: ContributingFactor[];
  is_cold_start: boolean;
  last_known_event?: string;
  escalated?: boolean;
  note?: string;
  // Phase 7 — proxy for carriageway-width consumed by concurrently parked
  // vehicles in this zone (not measured traffic flow; the dataset has no
  // speed/volume/queue data). See docs/risk_definition.md.
  carriageway_impact_score: number;
  carriageway_impact_label: "Minimal" | "Moderate" | "Significant" | "Severe";
}

export interface Alert {
  zone: string;
  junction_name: string;
  police_station: string;
  latitude: number;
  longitude: number;
  alert_level: "GREEN" | "YELLOW" | "ORANGE" | "RED";
  probability: number;
  risk_score: number;
  risk_band: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  recommendation: string;
  escalated: boolean;
  top_contributing_factors: ContributingFactor[];
  last_known_event: string;
  carriageway_impact_score: number;
  carriageway_impact_label: "Minimal" | "Moderate" | "Significant" | "Severe";
}

export interface AlertsResponse {
  count: number;
  total_cells_evaluated: number;
  alerts: Alert[];
}

// Phase 7 — /replay/{scenario}: a real historical event sequence (not
// synthetic, not live) replayed point-by-point for the dashboard's replay
// mode. See backend/app/serving/replay_service.py.
export interface ReplayPoint {
  timestamp: string;
  latitude: number;
  longitude: number;
  junction_name: string;
  vehicle_type: string;
  violations_last_15m: number;
  rolling_hotspot_intensity: number;
  carriageway_impact_score: number;
  carriageway_impact_label: "Minimal" | "Moderate" | "Significant" | "Severe";
  hotspot_probability: number;
  predicted_count: number;
  risk_score: number;
  risk_band: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  recommendation: string;
  escalated: boolean;
}

export interface ReplayResponse {
  scenario: string;
  label: string;
  cell: string;
  is_real_data: boolean;
  point_count: number;
  points: ReplayPoint[];
}

export interface ModelMetric {
  model: string;
  pr_auc: number;
  precision: number;
  recall: number;
  f1: number;
  brier_score?: number;
}

export interface MetricsResponse {
  model: {
    winner: string;
    test_metrics: ModelMetric[];
    val_comparison: ModelMetric[];
  };
  operating_threshold: number;
  operational_horizon_minutes: number;
  spatial_robustness: {
    holdout_verdict: string;
    holdout_pr_auc_drop_pct: number;
    abstraction_verdict: string;
    abstraction_pr_auc_drop_pct: number | null;
  };
  live_risk_distribution: {
    total_cells: number;
    band_counts: Record<string, number>;
    band_pct: Record<string, number>;
  };
  feature_set: string;
  data_sources: string;
  temporal_distribution: {
    by_hour: { hour: number; count: number }[];
    by_weekday: { weekday: number; label: string; count: number }[];
  };
}

export interface HealthResponse {
  status: string;
  rows_loaded: number;
  schema_valid: boolean;
  missing_columns: string[];
}

// Admin API (retraining pipeline) — see backend/app/serving/admin_service.py
// and backend/app/ingestion/staging_store.py. Uploaded CSVs land here as
// PENDING before a reviewer approves (merges into the master raw dataset)
// or rejects them; retraining is a separate, explicit action on top.
export interface AppendResult {
  rows_received: number;
  rows_added: number;
  rows_duplicate: number;
  rows_invalid: number;
  invalid_reasons: string[];
  master_row_count: number;
  master_path: string;
}

export interface StagingRecord {
  staging_id: string;
  original_filename: string;
  uploaded_at: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  row_count: number;
  schema_valid: boolean;
  missing_columns: string[];
  null_counts: Record<string, number>;
  resolved_at: string | null;
  merge_result: AppendResult | null;
  reject_reason: string | null;
}

export interface StagingDetail extends StagingRecord {
  preview_rows: Record<string, string>[];
}

export interface RetrainJob {
  job_id: string;
  status: "PENDING" | "RUNNING" | "SUCCESS" | "FAILED";
  started_at: string;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
}
