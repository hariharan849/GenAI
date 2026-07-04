import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from api.dependencies import AgenticRAGDep
from api.evaluation.dataset import GoldenCase, load_golden_dataset
from api.evaluation.harness import run_harness_from_cases
from api.evaluation.persistence import save_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/eval", tags=["eval"])


class EvalRunStartResponse(BaseModel):
    run_id: str
    status: Literal["running"]


class EvalRunStatusResponse(BaseModel):
    status: Literal["running", "completed", "errored"]
    total: Optional[int] = None
    completed: Optional[int] = None
    run_id: Optional[str] = None
    error: Optional[str] = None


class EvalRunSummary(BaseModel):
    run_id: str
    timestamp: str
    commit: str
    case_count: int
    avg_scores: Dict[str, float] = Field(default_factory=dict)


class EvalRunDetail(BaseModel):
    run_id: str
    timestamp: Optional[str] = None
    commit: Optional[str] = None
    cases: List[Dict[str, Any]] = Field(default_factory=list)


def _eval_runs_state(request: Request) -> Dict[str, Dict[str, Any]]:
    if not hasattr(request.app.state, "eval_runs"):
        request.app.state.eval_runs = {}
    return request.app.state.eval_runs


def _results_dir(request: Request) -> str:
    return request.app.state.settings.eval.results_dir


def _load_uploaded_cases(upload: UploadFile, content: bytes) -> List[GoldenCase]:
    if not upload.filename:
        raise HTTPException(status_code=422, detail="Invalid YAML: missing filename")

    f = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")
    try:
        f.write(content)
        f.close()  # Windows requires close before reading by path.
        cases = load_golden_dataset(f.name)
    except (yaml.YAMLError, KeyError, TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {e}") from e
    finally:
        try:
            os.unlink(f.name)
        except OSError:
            pass

    if not cases:
        raise HTTPException(status_code=422, detail="Invalid YAML: cases must contain at least one case")
    return cases


async def _run_eval_background(
    request: Request,
    run_id: str,
    cases: List[GoldenCase],
    service: Any,
    judge_model: str,
    results_dir: str,
) -> None:
    runs = _eval_runs_state(request)
    try:
        def _progress() -> None:
            runs[run_id]["completed"] += 1

        results = await run_harness_from_cases(service, cases, judge_model, progress_cb=_progress)
        save_run(results, results_dir, run_id=run_id)
        runs[run_id]["status"] = "completed"
    except Exception as e:
        logger.exception("[eval run %s] failed", run_id)
        runs[run_id] = {
            "status": "errored",
            "total": len(cases),
            "completed": runs.get(run_id, {}).get("completed", 0),
            "error": str(e),
        }


@router.post("/run", response_model=EvalRunStartResponse)
async def start_eval_run(
    upload: UploadFile,
    background_tasks: BackgroundTasks,
    request: Request,
    service: AgenticRAGDep,
) -> EvalRunStartResponse:
    settings = request.app.state.settings
    cases = _load_uploaded_cases(upload, await upload.read())

    run_id = str(uuid.uuid4())
    _eval_runs_state(request)[run_id] = {
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

    return EvalRunStartResponse(run_id=run_id, status="running")


@router.get("/runs", response_model=List[EvalRunSummary])
async def list_runs(request: Request) -> List[EvalRunSummary]:
    summaries_dir = Path(_results_dir(request)) / "summaries"
    if not summaries_dir.exists():
        return []

    summaries = sorted(summaries_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    result: List[EvalRunSummary] = []
    for path in summaries:
        try:
            result.append(EvalRunSummary.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception:
            logger.warning("Skipping unreadable eval summary %s", path)
    return result


@router.get("/runs/{run_id}/status", response_model=EvalRunStatusResponse)
async def get_run_status(run_id: str, request: Request) -> EvalRunStatusResponse:
    state = _eval_runs_state(request).get(run_id)
    if state is not None:
        return EvalRunStatusResponse(
            status=state["status"],
            total=state.get("total"),
            completed=state.get("completed"),
            run_id=run_id if state["status"] == "completed" else None,
            error=state.get("error"),
        )

    run_file = Path(_results_dir(request)) / f"{run_id}.json"
    if run_file.exists():
        return EvalRunStatusResponse(status="completed", run_id=run_id)

    raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")


@router.get("/runs/{run_id}", response_model=EvalRunDetail)
async def get_run(run_id: str, request: Request) -> EvalRunDetail:
    run_file = Path(_results_dir(request)) / f"{run_id}.json"
    if not run_file.exists():
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return EvalRunDetail.model_validate(json.loads(run_file.read_text(encoding="utf-8")))
