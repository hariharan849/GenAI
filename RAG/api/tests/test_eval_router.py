import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.eval import router

VALID_YAML = b"""
cases:
  - case_id: test-1
    url: https://docs.foundry.com/nuke/node
    question: What does Merge do?
    expected_output: Composites two inputs.
"""

MALFORMED_YAML = b"cases: [this is not valid yaml: :"

MISSING_CASES_KEY_YAML = b"""
items:
  - case_id: test-1
    url: https://example.com
    question: q
    expected_output: a
"""


def _make_app(results_dir: str) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    # Minimal settings mock
    settings = MagicMock()
    settings.eval.judge_model = "gpt-4o-mini"
    settings.eval.results_dir = results_dir

    @app.on_event("startup")
    async def _startup() -> None:
        app.state.settings = settings
        app.state.eval_runs = {}

    return app


@pytest.fixture
def client(tmp_results_dir: Path) -> TestClient:
    app = _make_app(str(tmp_results_dir))
    return TestClient(app, raise_server_exceptions=False)


def test_post_run_valid_yaml_returns_run_id(client: TestClient) -> None:
    with patch("api.routers.eval.run_harness_from_cases", new_callable=AsyncMock):
        with patch("api.routers.eval.save_run", return_value=Path("/tmp/fake.json")):
            res = client.post(
                "/api/v1/eval/run",
                files={"upload": ("golden.yaml", io.BytesIO(VALID_YAML), "application/yaml")},
            )
    assert res.status_code == 200
    body = res.json()
    assert "run_id" in body
    assert body["status"] == "running"


def test_post_run_malformed_yaml_returns_422(client: TestClient) -> None:
    res = client.post(
        "/api/v1/eval/run",
        files={"upload": ("bad.yaml", io.BytesIO(MALFORMED_YAML), "application/yaml")},
    )
    assert res.status_code == 422
    assert "Invalid YAML" in res.json()["detail"]


def test_post_run_missing_cases_key_returns_422(client: TestClient) -> None:
    res = client.post(
        "/api/v1/eval/run",
        files={"upload": ("no_cases.yaml", io.BytesIO(MISSING_CASES_KEY_YAML), "application/yaml")},
    )
    assert res.status_code == 422


def test_get_run_unknown_id_returns_404(client: TestClient) -> None:
    res = client.get("/api/v1/eval/runs/unknown-run-id")
    assert res.status_code == 404


def test_get_run_status_unknown_id_returns_404(client: TestClient) -> None:
    res = client.get("/api/v1/eval/runs/unknown-run-id/status")
    assert res.status_code == 404


def test_get_runs_empty_returns_list(client: TestClient) -> None:
    res = client.get("/api/v1/eval/runs")
    assert res.status_code == 200
    assert res.json() == []


def test_get_run_status_in_memory_running(client: TestClient) -> None:
    app = client.app
    run_id = "test-run-123"
    app.state.eval_runs[run_id] = {"status": "running", "total": 5, "completed": 2}

    res = client.get(f"/api/v1/eval/runs/{run_id}/status")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "running"
    assert body["total"] == 5
    assert body["completed"] == 2
    assert body["run_id"] is None


def test_get_run_status_disk_fallback(tmp_results_dir: Path) -> None:
    """Post-restart: no in-memory state but file exists on disk."""
    tmp_results_dir.mkdir(parents=True, exist_ok=True)
    run_id = "disk-fallback-run"
    run_file = tmp_results_dir / f"{run_id}.json"
    run_file.write_text(json.dumps({"run_id": run_id, "cases": []}), encoding="utf-8")

    app = _make_app(str(tmp_results_dir))

    @app.on_event("startup")
    async def _startup() -> None:
        app.state.settings = MagicMock()
        app.state.settings.eval.results_dir = str(tmp_results_dir)
        app.state.eval_runs = {}  # empty — simulates post-restart state

    with TestClient(app, raise_server_exceptions=False) as c:
        res = c.get(f"/api/v1/eval/runs/{run_id}/status")

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["run_id"] == run_id
