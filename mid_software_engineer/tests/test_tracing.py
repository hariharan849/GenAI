from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

import pytest
from langchain_core.messages import ToolMessage

from mid_software_engineer.tracing import (
    AgentTraceStore,
    TraceEvent,
    configure_langsmith,
    create_trace_middleware,
    infer_skill_name,
)


@dataclass
class FakeRequest:
    tool_call: dict
    state: dict | None = None
    runtime: object | None = None
    tool: object | None = None


def test_trace_store_creates_schema_and_returns_recent(tmp_path: Path) -> None:
    store = AgentTraceStore(tmp_path / "traces.sqlite3")

    store.insert(
        TraceEvent(
            id="trace-1",
            thread_id="thread-1",
            run_id="run-1",
            tool_call_id="call-1",
            tool_name="read_file",
            tool_args_json='{"path": "SKILL.md"}',
            status="success",
            started_at=1.0,
            ended_at=1.2,
            duration_ms=200,
            error=None,
            skill_name="office-hours",
        )
    )

    rows = store.recent()
    assert rows[0]["id"] == "trace-1"
    assert rows[0]["tool_name"] == "read_file"
    assert rows[0]["skill_name"] == "office-hours"


def test_trace_middleware_records_success(tmp_path: Path) -> None:
    store = AgentTraceStore(tmp_path / "traces.sqlite3")
    middleware = create_trace_middleware(store)
    request = FakeRequest(
        tool_call={
            "id": "call-1",
            "name": "read_file",
            "args": {"path": "C:/Users/HARI/.agents/skills/office-hours/SKILL.md"},
        },
        state={"thread_id": "thread-1"},
    )

    result = middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(content="ok", tool_call_id="call-1"),
    )

    rows = store.recent()
    assert result.content == "ok"
    assert rows[0]["status"] == "success"
    assert rows[0]["thread_id"] == "thread-1"
    assert rows[0]["tool_call_id"] == "call-1"
    assert rows[0]["skill_name"] == "office-hours"


def test_trace_middleware_records_error(tmp_path: Path) -> None:
    store = AgentTraceStore(tmp_path / "traces.sqlite3")
    middleware = create_trace_middleware(store)
    request = FakeRequest(tool_call={"id": "call-1", "name": "write_file", "args": {"path": "x.py"}})

    def fail(_request):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        middleware.wrap_tool_call(request, fail)

    rows = store.recent()
    assert rows[0]["status"] == "error"
    assert rows[0]["tool_name"] == "write_file"
    assert rows[0]["error"] == "boom"


def test_infer_skill_name_from_skill_path() -> None:
    assert (
        infer_skill_name("read_file", {"path": "C:\\Users\\HARI\\.agents\\skills\\autoplan\\SKILL.md"})
        == "autoplan"
    )
    assert infer_skill_name("read_file", {"path": "C:/tmp/README.md"}) is None


def test_configure_langsmith_sets_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)

    configure_langsmith("custom-project")

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_PROJECT"] == "custom-project"
