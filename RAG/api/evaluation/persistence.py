import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from api.evaluation.harness import CaseResult


def _git_commit_hash() -> str:
    """Short commit hash for the current HEAD, or "unknown" outside a git repo."""
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def save_run(results: List[CaseResult], results_dir: str, run_id: Optional[str] = None) -> Path:
    """Persist one eval run as timestamped JSON tagged with the git commit hash.

    :param results: Per-case results from run_harness.
    :param results_dir: Directory to write the run file into (created if missing).
    :param run_id: Optional stem for the output filename. When provided (router path),
        the file is written as ``{run_id}.json`` so the caller controls the ID.
        When omitted (CLI path), the stem is generated as ``run-{timestamp}-{commit}``.
    :returns: Path to the written run file.
    """
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    commit = _git_commit_hash()
    stem = run_id or f"run-{timestamp}-{commit}"
    run_path = Path(results_dir) / f"{stem}.json"

    payload = {
        "run_id": stem,
        "timestamp": timestamp,
        "commit": commit,
        "cases": [asdict(r) for r in results],
    }
    run_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Write a lightweight summary sidecar for fast listing (GET /eval/runs).
    # Stored in a summaries/ subdirectory so the existing glob("run-*.json") in
    # latest_run() is unaffected — it scans the top level only.
    scored = [r for r in results if r.status == "scored"]
    metrics_seen = sorted({m for r in scored for m in r.scores})
    avg_scores = {
        m: sum(r.scores[m] for r in scored if m in r.scores) / max(len(scored), 1)
        for m in metrics_seen
    }
    summary_dir = Path(results_dir) / "summaries"
    summary_dir.mkdir(exist_ok=True)
    summary = {
        "run_id": stem,
        "timestamp": timestamp,
        "commit": commit,
        "case_count": len(results),
        "avg_scores": avg_scores,
    }
    (summary_dir / f"{stem}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return run_path


def load_run(path: str) -> dict:
    """Load a persisted run JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest_run(results_dir: str, exclude: Optional[Path] = None) -> Optional[Path]:
    """Find the most recently written run file in results_dir.

    :param exclude: A run path to skip (used to find the second-newest run as
        a default baseline when comparing against "the current run").
    """
    runs = sorted(Path(results_dir).glob("run-*.json"))
    if exclude is not None:
        runs = [r for r in runs if r != exclude]
    return runs[-1] if runs else None
