"""Tracing helpers for DeepAgent tool and skill usage."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from langchain.agents.middleware import wrap_tool_call


DEFAULT_TRACE_DB = "./agent_traces.sqlite3"
DEFAULT_LANGSMITH_PROJECT = "mid-software-engineer"


@dataclass(frozen=True)
class TraceEvent:
    id: str
    thread_id: str | None
    run_id: str | None
    tool_call_id: str | None
    tool_name: str
    tool_args_json: str
    status: str
    started_at: float
    ended_at: float
    duration_ms: int
    error: str | None
    skill_name: str | None


class AgentTraceStore:
    """Small SQLite trace store for local agent observability."""

    def __init__(self, db_path: str | Path = DEFAULT_TRACE_DB) -> None:
        self.db_path = str(db_path)
        db_parent = Path(self.db_path).expanduser().resolve().parent
        db_parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_tool_traces (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT,
                    run_id TEXT,
                    tool_call_id TEXT,
                    tool_name TEXT NOT NULL,
                    tool_args_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    error TEXT,
                    skill_name TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_tool_traces_started_at
                ON agent_tool_traces(started_at DESC)
                """
            )

    def insert(self, event: TraceEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_tool_traces (
                    id, thread_id, run_id, tool_call_id, tool_name, tool_args_json,
                    status, started_at, ended_at, duration_ms, error, skill_name
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.thread_id,
                    event.run_id,
                    event.tool_call_id,
                    event.tool_name,
                    event.tool_args_json,
                    event.status,
                    event.started_at,
                    event.ended_at,
                    event.duration_ms,
                    event.error,
                    event.skill_name,
                ),
            )

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 500))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, thread_id, run_id, tool_call_id, tool_name, tool_args_json,
                       status, started_at, ended_at, duration_ms, error, skill_name
                FROM agent_tool_traces
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in rows]


def configure_langsmith(project_name: str = DEFAULT_LANGSMITH_PROJECT) -> None:
    """Set LangSmith tracing defaults without overwriting explicit user config."""

    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", project_name)


def create_trace_middleware(trace_store: AgentTraceStore):
    """Create LangChain middleware that records every tool call to SQLite."""

    @wrap_tool_call(name="AgentTraceMiddleware")
    def trace_tool_call(request, handler):
        started = time.time()
        tool_call = getattr(request, "tool_call", {}) or {}
        tool_name = str(tool_call.get("name") or getattr(getattr(request, "tool", None), "name", "unknown"))
        tool_args = tool_call.get("args") or {}
        tool_call_id = tool_call.get("id")
        thread_id = extract_thread_id(request)
        run_id = extract_run_id(request)
        skill_name = infer_skill_name(tool_name, tool_args)

        try:
            result = handler(request)
        except Exception as exc:
            ended = time.time()
            trace_store.insert(
                TraceEvent(
                    id=str(uuid.uuid4()),
                    thread_id=thread_id,
                    run_id=run_id,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    tool_args_json=safe_json(tool_args),
                    status="error",
                    started_at=started,
                    ended_at=ended,
                    duration_ms=int((ended - started) * 1000),
                    error=str(exc),
                    skill_name=skill_name,
                )
            )
            raise

        ended = time.time()
        trace_store.insert(
            TraceEvent(
                id=str(uuid.uuid4()),
                thread_id=thread_id,
                run_id=run_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                tool_args_json=safe_json(tool_args),
                status="success",
                started_at=started,
                ended_at=ended,
                duration_ms=int((ended - started) * 1000),
                error=None,
                skill_name=skill_name,
            )
        )
        return result

    return trace_tool_call


def extract_thread_id(request: Any) -> str | None:
    state = getattr(request, "state", None)
    if isinstance(state, dict):
        for key in ("thread_id", "conversation_id"):
            value = state.get(key)
            if value:
                return str(value)

    runtime = getattr(request, "runtime", None)
    context = getattr(runtime, "context", None)
    if isinstance(context, dict):
        for key in ("thread_id", "conversation_id"):
            value = context.get(key)
            if value:
                return str(value)
    return None


def extract_run_id(request: Any) -> str | None:
    runtime = getattr(request, "runtime", None)
    for attr in ("run_id", "id"):
        value = getattr(runtime, attr, None)
        if value:
            return str(value)
    return None


def infer_skill_name(tool_name: str, tool_args: Any) -> str | None:
    text = " ".join(str(value) for value in flatten_values(tool_args))
    if tool_name in {"read_file", "open_file"} or "SKILL.md" in text:
        normalized = text.replace("\\", "/").lower()
        for skill_name in ("office-hours", "autoplan", "ship"):
            if f"/{skill_name}/skill.md" in normalized or f"/{skill_name}/" in normalized:
                return skill_name
    return None


def flatten_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for nested in value.values():
            yield from flatten_values(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from flatten_values(nested)
    else:
        yield value


def safe_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value))
