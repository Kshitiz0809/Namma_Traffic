"use client";

// Admin view — closes the "models are frozen, no way to retrain on new
// data" gap. A police-uploaded CSV lands here as PENDING first; a reviewer
// approves (merges into the master raw dataset) or rejects it, and
// retraining is a separate, explicit action that can batch up several
// approved uploads. See backend/app/serving/admin_service.py and
// backend/app/ingestion/staging_store.py.

import {
  CheckCircle2,
  KeyRound,
  RefreshCw,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  approveStaging,
  getRetrainStatus,
  listStaging,
  rejectStaging,
  triggerRetrain,
  uploadStagingFile,
} from "@/lib/api";
import type { RetrainJob, StagingRecord } from "@/lib/types";

const TOKEN_STORAGE_KEY = "parking-intel-admin-token";

const STATUS_STYLE: Record<string, { bg: string; text: string }> = {
  PENDING: { bg: "bg-yellow-50 border-yellow-200", text: "text-yellow-800" },
  APPROVED: { bg: "bg-green-50 border-green-200", text: "text-green-800" },
  REJECTED: { bg: "bg-red-50 border-red-200", text: "text-red-800" },
};

export default function AdminPanel() {
  const [token, setToken] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [staged, setStaged] = useState<StagingRecord[]>([]);
  const [stagedError, setStagedError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const [retrainJob, setRetrainJob] = useState<RetrainJob | null>(null);
  const [retrainError, setRetrainError] = useState<string | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (saved) setToken(saved);
  }, []);

  function updateToken(value: string) {
    setToken(value);
    localStorage.setItem(TOKEN_STORAGE_KEY, value);
  }

  async function refreshStaged() {
    if (!token) return;
    try {
      const res = await listStaging(token);
      setStaged(res.staged);
      setStagedError(null);
    } catch (err) {
      setStagedError(String(err));
    }
  }

  useEffect(() => {
    if (token) refreshStaged();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleUpload() {
    if (!file || !token) return;
    setUploading(true);
    setUploadError(null);
    try {
      await uploadStagingFile(file, token);
      setFile(null);
      await refreshStaged();
    } catch (err) {
      setUploadError(String(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleApprove(stagingId: string) {
    setPendingAction(stagingId);
    try {
      await approveStaging(stagingId, token);
      await refreshStaged();
    } catch (err) {
      setStagedError(String(err));
    } finally {
      setPendingAction(null);
    }
  }

  async function handleReject(stagingId: string) {
    setPendingAction(stagingId);
    try {
      await rejectStaging(stagingId, token, "Rejected via dashboard");
      await refreshStaged();
    } catch (err) {
      setStagedError(String(err));
    } finally {
      setPendingAction(null);
    }
  }

  async function handleRetrain() {
    setRetrainError(null);
    try {
      const { job_id } = await triggerRetrain(token);
      setRetrainJob({ job_id, status: "PENDING", started_at: new Date().toISOString(), finished_at: null, result: null, error: null });
      poll(job_id);
    } catch (err) {
      setRetrainError(String(err));
    }
  }

  function poll(jobId: string) {
    const interval = setInterval(async () => {
      try {
        const job = await getRetrainStatus(jobId, token);
        setRetrainJob(job);
        if (job.status === "SUCCESS" || job.status === "FAILED") {
          clearInterval(interval);
          if (job.status === "SUCCESS") refreshStaged();
        }
      } catch (err) {
        setRetrainError(String(err));
        clearInterval(interval);
      }
    }, 3000);
  }

  const pendingCount = staged.filter((s) => s.status === "PENDING").length;

  return (
    <div className="flex flex-col gap-6">
      <div className="card p-5 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center">
            <KeyRound size={16} className="text-indigo-600" />
          </div>
          <h2 className="font-semibold text-slate-800">Admin token</h2>
        </div>
        <p className="text-xs text-slate-500">
          Required for all admin actions below. The backend disables these
          routes entirely (503) unless <code>ADMIN_API_TOKEN</code> is
          configured server-side.
        </p>
        <input
          type="password"
          value={token}
          onChange={(e) => updateToken(e.target.value)}
          placeholder="X-Admin-Token"
          className="border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400"
        />
      </div>

      <div className="card p-5 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center">
            <UploadCloud size={16} className="text-indigo-600" />
          </div>
          <h2 className="font-semibold text-slate-800">Upload new violations CSV</h2>
        </div>
        <p className="text-xs text-slate-500">
          Lands as PENDING — it does not affect the model until a reviewer
          approves it below.
        </p>
        <div className="flex items-center gap-3">
          <input
            type="file"
            accept=".csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm flex-1"
          />
          <button
            onClick={handleUpload}
            disabled={!file || !token || uploading}
            className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-4 py-2.5 text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
        {uploadError && (
          <div className="text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm">
            {uploadError}
          </div>
        )}
      </div>

      <div className="card p-5 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-slate-800">Staged uploads</h2>
          <button
            onClick={refreshStaged}
            disabled={!token}
            className="text-xs flex items-center gap-1 text-slate-500 hover:text-indigo-600 disabled:opacity-50"
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
        {stagedError && (
          <div className="text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm">
            {stagedError}
          </div>
        )}
        {staged.length === 0 && !stagedError && (
          <p className="text-sm text-slate-400">No staged uploads yet.</p>
        )}
        <ul className="flex flex-col gap-2">
          {staged.map((s) => {
            const style = STATUS_STYLE[s.status];
            return (
              <li
                key={s.staging_id}
                className={`flex items-center justify-between border rounded-lg px-3 py-2 ${style.bg}`}
              >
                <div className="flex flex-col">
                  <span className="text-sm font-medium text-slate-700">{s.original_filename}</span>
                  <span className="text-xs text-slate-500">
                    {s.row_count} rows · {s.schema_valid ? "schema OK" : "schema INVALID"} ·{" "}
                    {new Date(s.uploaded_at).toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-semibold uppercase ${style.text}`}>{s.status}</span>
                  {s.status === "PENDING" && (
                    <>
                      <button
                        onClick={() => handleApprove(s.staging_id)}
                        disabled={pendingAction === s.staging_id}
                        className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg bg-green-600 hover:bg-green-700 text-white disabled:opacity-50"
                      >
                        <CheckCircle2 size={13} /> Approve
                      </button>
                      <button
                        onClick={() => handleReject(s.staging_id)}
                        disabled={pendingAction === s.staging_id}
                        className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg bg-slate-500 hover:bg-slate-600 text-white disabled:opacity-50"
                      >
                        <XCircle size={13} /> Reject
                      </button>
                    </>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="card p-5 flex flex-col gap-3">
        <h2 className="font-semibold text-slate-800">Retrain</h2>
        <p className="text-xs text-slate-500">
          Retrains on everything currently in the master dataset (all
          approved uploads), refits risk weights, and re-checks spatial
          generalization. Runs in the background — this can take several
          minutes.
        </p>
        <button
          onClick={handleRetrain}
          disabled={!token || (retrainJob !== null && retrainJob.status !== "SUCCESS" && retrainJob.status !== "FAILED")}
          className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-4 py-2.5 text-sm font-medium disabled:opacity-50 transition-colors self-start"
        >
          {pendingCount > 0 ? `Retrain now (${pendingCount} approved since last run)` : "Retrain now"}
        </button>
        {retrainError && (
          <div className="text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm">
            {retrainError}
          </div>
        )}
        {retrainJob && (
          <div className="text-sm border border-slate-200 rounded-lg p-3 bg-slate-50">
            <div className="font-medium text-slate-700">
              Job {retrainJob.job_id.slice(0, 8)} — {retrainJob.status}
            </div>
            {retrainJob.status === "FAILED" && (
              <div className="text-red-700 text-xs mt-1">{retrainJob.error}</div>
            )}
            {retrainJob.status === "SUCCESS" && retrainJob.result && (
              <pre className="text-xs text-slate-600 mt-2 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(retrainJob.result, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
