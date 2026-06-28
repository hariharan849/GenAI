import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile

from api.dependencies import AgenticRAGDep
from api.evaluation.dataset import GoldenCase, load_golden_dataset
from api.evaluation.harness import run_harness_from_cases
from api.evaluation.persistence import save_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/eval", tags=["eval"])


async def _run_eval_background(
    request: Request,
    run_id: str,
    cases: List[GoldenCase],
    service: Any,
    judge_model: str,
    results_dir: str,
) -> None:
    try:
        def _progress() -> None:
            request.app.state.eval_runs[run_id]["completed"] += 1

        results = await run_harness_from_cases(service, cases, judge_model, progress_cb=_progress)
        save_run(results, results_dir, run_id=run_id)
        request.app.state.eval_runs[run_id]["status"] = "completed"
    except Exception as e:
        logger.error(f"[eval run {run_id}] failed: {e}")
        request.app.state.eval_runs[run_id] = {"status": "errored", "error": str(e)}


@router.post("/run")
async def start_eval_run(
    upload: UploadFile,
    background_tasks: BackgroundTasks,
    request: Request,
    service: AgenticRAGDep,
) -> Dict[str, str]:
    settings = request.app.state.settings

    f = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")
    try:
        f.write(await upload.read())
        f.close()  # close before reading by path — required on Windows
        try:
            cases = load_golden_dataset(f.name)
        except (yaml.YAMLError, KeyError, TypeError, Exception) as e:
            raise HTTPException(status_code=422, detail=f"Invalid YAML: {e}")
    finally:
        try:
            os.unlink(f.name)
        except OSError:
            pass

    run_id = str(uuid.uuid4())
    request.app.state.eval_runs[run_id] = {
        "status": "running",
        "total": len(cases),
        "completed": 0,
    }

    background_tasks.add_task(
        _run_eval_background,
        request=request,
        run_id=run_id,
        cases=cases,
        service=service,
        judge_model=settings.eval.judge_model,
        results_dir=settings.eval.results_dir,
    )

    return {"run_id": run_id, "status": "running"}


@router.get("/runs")
async def list_runs(request: Request) -> List[Dict]:
    results_dir = request.app.state.settings.eval.results_dir
    summaries_dir = Path(results_dir) / "summaries"
    if not summaries_dir.exists():
        return []

    summaries = sorted(summaries_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for path in summaries:
        try:
            result.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return result


@router.get("/runs/{run_id}/status")
async def get_run_status(run_id: str, request: Request) -> Dict:
    state = request.app.state.eval_runs.get(run_id)
    if state is not None:
        response: Dict = {
            "status": state["status"],
            "total": state.get("total"),
            "completed": state.get("completed"),
            "run_id": run_id if state["status"] == "completed" else None,
        }
        if state["status"] == "errored":
            response["error"] = state.get("error")
        return response

    # Disk-fallback for post-restart: check if the run file was persisted
    results_dir = request.app.state.settings.eval.results_dir
    run_file = Path(results_dir) / f"{run_id}.json"
    if run_file.exists():
        return {"status": "completed", "total": None, "completed": None, "run_id": run_id}

    raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> Dict:
    results_dir = request.app.state.settings.eval.results_dir
    run_file = Path(results_dir) / f"{run_id}.json"
    if not run_file.exists():
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return json.loads(run_file.read_text(encoding="utf-8"))
