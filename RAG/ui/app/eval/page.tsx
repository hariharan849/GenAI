"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface CaseResult {
  case_id: string;
  question: string;
  status: string;
  scores: Record<string, number>;
  error?: string;
}

interface RunDetail {
  run_id: string;
  timestamp: string;
  commit: string;
  cases: CaseResult[];
}

interface RunSummary {
  run_id: string;
  timestamp: string;
  commit: string;
  case_count: number;
  avg_scores: Record<string, number>;
}

interface RunStatus {
  status: string;
  total: number | null;
  completed: number | null;
  run_id: string | null;
  error?: string;
}

const POLL_INTERVAL_MS = 3000;

export default function EvalPage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [pastRuns, setPastRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const loadRunDetail = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/eval/runs/${id}`);
      if (!res.ok) throw new Error(`Failed to load run: ${res.status}`);
      setRunDetail(await res.json());
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const loadPastRuns = useCallback(async () => {
    try {
      const res = await fetch("/api/eval/runs");
      if (res.ok) setPastRuns(await res.json());
    } catch {
      // non-blocking
    }
  }, []);

  useEffect(() => {
    loadPastRuns();
  }, [loadPastRuns]);

  useEffect(() => {
    if (!runId) return;
    stopPolling();

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/eval/runs/${runId}/status`);
        if (!res.ok) {
          stopPolling();
          setError(`Status check failed: ${res.status}`);
          return;
        }
        const status: RunStatus = await res.json();
        setRunStatus(status);

        if (status.status === "completed" && status.run_id) {
          stopPolling();
          await loadRunDetail(status.run_id);
          await loadPastRuns();
        } else if (status.status === "errored") {
          stopPolling();
          setError(status.error ?? "Eval run errored — check server logs");
        }
      } catch (e) {
        stopPolling();
        setError(String(e));
      }
    }, POLL_INTERVAL_MS);

    return stopPolling;
  }, [runId, stopPolling, loadRunDetail, loadPastRuns]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) setFile(e.target.files[0]);
  };

  const handleRun = async () => {
    if (!file) return;
    setError(null);
    setRunDetail(null);
    setRunStatus(null);

    const form = new FormData();
    form.append("upload", file);

    try {
      const res = await fetch("/api/eval/run", { method: "POST", body: form });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: "Unknown error" }));
        setError(body.detail ?? `Upload failed: ${res.status}`);
        return;
      }
      const data = await res.json();
      setRunId(data.run_id);
    } catch (e) {
      setError(String(e));
    }
  };

  const isRunning = runStatus?.status === "running";
  const allMetrics = runDetail
    ? Array.from(new Set(runDetail.cases.flatMap((c) => Object.keys(c.scores)))).sort()
    : [];

  return (
    <main className="max-w-5xl mx-auto p-6 space-y-8 font-sans">
      <h1 className="text-2xl font-bold">Eval Runner</h1>

      {/* Upload zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
          ${dragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400"}`}
        onClick={() => document.getElementById("yaml-input")?.click()}
      >
        <input
          id="yaml-input"
          type="file"
          accept=".yaml,.yml"
          className="hidden"
          onChange={handleFileChange}
        />
        {file ? (
          <p className="text-sm text-gray-700">
            Selected: <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)
          </p>
        ) : (
          <p className="text-sm text-gray-500">
            Drag & drop a <code>.yaml</code> golden dataset, or click to browse
          </p>
        )}
      </div>

      <button
        onClick={handleRun}
        disabled={!file || isRunning}
        className="px-4 py-2 bg-blue-600 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-blue-700"
      >
        {isRunning ? "Running..." : "Run Eval"}
      </button>

      {/* Progress */}
      {isRunning && runStatus && (
        <p className="text-sm text-gray-600">
          Running...{" "}
          {runStatus.completed !== null && runStatus.total !== null
            ? `(case ${runStatus.completed}/${runStatus.total})`
            : ""}
        </p>
      )}

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Results table */}
      {runDetail && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">
            Run results — {runDetail.timestamp} @ {runDetail.commit}
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-gray-100 text-left">
                  <th className="p-2 border">Case ID</th>
                  <th className="p-2 border">Question</th>
                  {allMetrics.map((m) => (
                    <th key={m} className="p-2 border">{m.replace("Metric", "")}</th>
                  ))}
                  <th className="p-2 border">Status</th>
                </tr>
              </thead>
              <tbody>
                {runDetail.cases.map((c) => (
                  <tr key={c.case_id} className={c.status === "errored" ? "bg-red-50" : ""}>
                    <td className="p-2 border font-mono text-xs">{c.case_id}</td>
                    <td className="p-2 border max-w-xs truncate" title={c.question}>
                      {c.question}
                    </td>
                    {allMetrics.map((m) => (
                      <td key={m} className="p-2 border text-center">
                        {c.scores[m] !== undefined ? c.scores[m].toFixed(3) : "—"}
                      </td>
                    ))}
                    <td className="p-2 border">
                      <span className={c.status === "errored" ? "text-red-600" : "text-green-600"}>
                        {c.status}
                      </span>
                      {c.error && (
                        <span className="block text-xs text-gray-500 truncate" title={c.error}>
                          {c.error}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Past runs */}
      {pastRuns.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Past runs</h2>
          <ul className="space-y-1">
            {pastRuns.map((run) => (
              <li key={run.run_id}>
                <button
                  onClick={() => loadRunDetail(run.run_id)}
                  className="text-left w-full p-2 rounded hover:bg-gray-50 border text-sm"
                >
                  <span className="font-mono text-xs text-gray-500 mr-2">
                    {run.timestamp} @ {run.commit}
                  </span>
                  <span className="mr-2">{run.case_count} cases</span>
                  {Object.entries(run.avg_scores).map(([m, v]) => (
                    <span key={m} className="mr-2 text-gray-600">
                      {m.replace("Metric", "")}: {v.toFixed(3)}
                    </span>
                  ))}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
