"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type Scores = Record<string, number>;

interface CaseResult {
  case_id: string;
  question: string;
  status: "scored" | "errored" | string;
  expected_output?: string;
  expected_retrieval_context?: string[] | null;
  actual_output?: string | null;
  retrieval_context?: string[];
  scores: Scores;
  error?: string | null;
}

interface RunDetail {
  run_id: string;
  timestamp?: string | null;
  commit?: string | null;
  cases: CaseResult[];
}

interface RunSummary {
  run_id: string;
  timestamp: string;
  commit: string;
  case_count: number;
  avg_scores: Scores;
}

interface RunStatus {
  status: "running" | "completed" | "errored";
  total: number | null;
  completed: number | null;
  run_id: string | null;
  error?: string | null;
}

const POLL_INTERVAL_MS = 2500;

function formatMetricName(metric: string): string {
  return metric.replace(/Metric$/, "").replace(/([a-z])([A-Z])/g, "$1 $2");
}

function formatScore(score: number | undefined): string {
  return typeof score === "number" ? score.toFixed(3) : "-";
}

export default function EvalPage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [pastRuns, setPastRuns] = useState<RunSummary[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const selectedCase = useMemo(() => {
    if (!runDetail) return null;
    return runDetail.cases.find((item) => item.case_id === selectedCaseId) ?? runDetail.cases[0] ?? null;
  }, [runDetail, selectedCaseId]);

  const allMetrics = useMemo(() => {
    if (!runDetail) return [];
    return Array.from(new Set(runDetail.cases.flatMap((item) => Object.keys(item.scores ?? {})))).sort();
  }, [runDetail]);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const loadPastRuns = useCallback(async () => {
    try {
      const res = await fetch("/api/eval/runs", { cache: "no-store" });
      if (res.ok) setPastRuns(await res.json());
    } catch {
      // Past runs are non-critical for the run launcher.
    }
  }, []);

  const loadRunDetail = useCallback(async (id: string) => {
    const res = await fetch(`/api/eval/runs/${id}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`Failed to load run ${id}: ${res.status}`);
    const detail: RunDetail = await res.json();
    setRunDetail(detail);
    setSelectedCaseId(detail.cases[0]?.case_id ?? null);
  }, []);

  useEffect(() => {
    loadPastRuns();
    return stopPolling;
  }, [loadPastRuns, stopPolling]);

  useEffect(() => {
    if (!runId) return;
    stopPolling();

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/eval/runs/${runId}/status`, { cache: "no-store" });
        if (!res.ok) throw new Error(`Status check failed: ${res.status}`);
        const status: RunStatus = await res.json();
        setRunStatus(status);

        if (status.status === "completed" && status.run_id) {
          stopPolling();
          await loadRunDetail(status.run_id);
          await loadPastRuns();
        }
        if (status.status === "errored") {
          stopPolling();
          setError(status.error ?? "Eval run failed. Check backend logs for details.");
        }
      } catch (err) {
        stopPolling();
        setError((err as Error).message);
      }
    }, POLL_INTERVAL_MS);

    return stopPolling;
  }, [runId, stopPolling, loadRunDetail, loadPastRuns]);

  function onDrop(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  }

  async function runEval() {
    if (!file) return;
    setError(null);
    setRunDetail(null);
    setRunStatus(null);
    setSelectedCaseId(null);

    const form = new FormData();
    form.append("upload", file);

    try {
      const res = await fetch("/api/eval/run", { method: "POST", body: form });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail ?? body.error ?? `Upload failed: ${res.status}`);
      setRunId(body.run_id);
      setRunStatus({ status: "running", total: null, completed: 0, run_id: null });
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const erroredCases = runDetail?.cases.filter((item) => item.status === "errored").length ?? 0;

  return (
    <main className="eval-shell">
      <section className="eval-header">
        <div>
          <p className="eval-kicker">Admin</p>
          <h1>Eval Console</h1>
          <p>Run golden datasets and inspect the evidence behind every RAG score.</p>
        </div>
        <a href="/" className="eval-link">Back to assistant</a>
      </section>

      <section className="eval-grid">
        <div className="eval-panel">
          <div className="eval-panel-title">
            <h2>Run eval</h2>
            {runStatus?.status === "running" && (
              <span className="eval-pill running">
                Running {runStatus.completed ?? 0}
                {runStatus.total ? `/${runStatus.total}` : ""}
              </span>
            )}
          </div>

          <label
            className={`eval-dropzone${dragging ? " dragging" : ""}`}
            onDrop={onDrop}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
          >
            <input
              type="file"
              accept=".yaml,.yml"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <span>{file ? file.name : "Choose or drop a golden YAML file"}</span>
            <small>{file ? `${(file.size / 1024).toFixed(1)} KB` : "Expected shape: cases[]"}</small>
          </label>

          <button className="eval-primary" onClick={runEval} disabled={!file || runStatus?.status === "running"}>
            {runStatus?.status === "running" ? "Running..." : "Run Eval"}
          </button>

          {error && <div className="eval-error">{error}</div>}
        </div>

        <div className="eval-panel">
          <div className="eval-panel-title">
            <h2>Past runs</h2>
            <button className="eval-link-button" onClick={loadPastRuns}>Refresh</button>
          </div>
          <div className="eval-run-list">
            {pastRuns.length === 0 && <p className="eval-muted">No saved runs yet.</p>}
            {pastRuns.map((run) => (
              <button
                key={run.run_id}
                className="eval-run-item"
                onClick={async () => {
                  setError(null);
                  setRunId(null);
                  setRunStatus(null);
                  await loadRunDetail(run.run_id);
                }}
              >
                <span>{run.timestamp}</span>
                <strong>{run.case_count} cases</strong>
                <small>{run.commit}</small>
              </button>
            ))}
          </div>
        </div>
      </section>

      {runDetail && (
        <section className="eval-results">
          <div className="eval-summary">
            <div>
              <p className="eval-kicker">Run</p>
              <h2>{runDetail.run_id}</h2>
              <p>{runDetail.timestamp ?? "unknown timestamp"} at {runDetail.commit ?? "unknown commit"}</p>
            </div>
            <div className="eval-score-strip">
              <div><strong>{runDetail.cases.length}</strong><span>Cases</span></div>
              <div><strong>{erroredCases}</strong><span>Errors</span></div>
              {allMetrics.slice(0, 3).map((metric) => {
                const scored = runDetail.cases.filter((item) => typeof item.scores?.[metric] === "number");
                const avg = scored.length
                  ? scored.reduce((sum, item) => sum + item.scores[metric], 0) / scored.length
                  : undefined;
                return <div key={metric}><strong>{formatScore(avg)}</strong><span>{formatMetricName(metric)}</span></div>;
              })}
            </div>
          </div>

          <div className="eval-detail-grid">
            <div className="eval-panel">
              <h2>Cases</h2>
              <div className="eval-case-table">
                <div className="eval-case-row header">
                  <span>Case</span>
                  <span>Status</span>
                  {allMetrics.map((metric) => <span key={metric}>{formatMetricName(metric)}</span>)}
                </div>
                {runDetail.cases.map((item) => (
                  <button
                    className={`eval-case-row${selectedCase?.case_id === item.case_id ? " selected" : ""}`}
                    key={item.case_id}
                    onClick={() => setSelectedCaseId(item.case_id)}
                  >
                    <span title={item.question}>{item.case_id}</span>
                    <span className={`eval-pill ${item.status === "errored" ? "error" : "ok"}`}>{item.status}</span>
                    {allMetrics.map((metric) => <span key={metric}>{formatScore(item.scores?.[metric])}</span>)}
                  </button>
                ))}
              </div>
            </div>

            <aside className="eval-panel eval-case-detail">
              <h2>Evidence</h2>
              {!selectedCase && <p className="eval-muted">Select a case.</p>}
              {selectedCase && (
                <>
                  <h3>{selectedCase.case_id}</h3>
                  <p className="eval-question">{selectedCase.question}</p>

                  <h4>Generated answer</h4>
                  <pre>{selectedCase.actual_output || "(no answer captured)"}</pre>

                  <h4>Expected answer</h4>
                  <pre>{selectedCase.expected_output || "(no expected answer)"}</pre>

                  <h4>Retrieved context</h4>
                  {(selectedCase.retrieval_context ?? []).length === 0 ? (
                    <p className="eval-muted">No retrieval context captured.</p>
                  ) : (
                    selectedCase.retrieval_context!.map((chunk, index) => <pre key={index}>{chunk}</pre>)
                  )}

                  {selectedCase.error && (
                    <>
                      <h4>Error</h4>
                      <pre className="eval-error-text">{selectedCase.error}</pre>
                    </>
                  )}
                </>
              )}
            </aside>
          </div>
        </section>
      )}
    </main>
  );
}
