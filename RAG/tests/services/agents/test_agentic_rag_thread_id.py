"""Regression tests for the thread_id / checkpointer config-key fix.

Mandatory per the Eng Review iron rule (PLAN-agent-memory.md): a prior version of
``agentic_rag.py`` set ``config = {"thread_id": ...}`` at the top level, which
LangGraph silently ignores — it reads thread_id from ``config["configurable"]``.
That made the checkpointer a complete no-op even with a stable id. These tests
guard against that regression.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services.agents.agentic_rag import AgenticRAGService


def _make_service() -> AgenticRAGService:
    """Build an AgenticRAGService with mocked clients (no real I/O)."""
    service = AgenticRAGService(
        opensearch_client=MagicMock(),
        ollama_client=MagicMock(),
        embeddings_client=MagicMock(),
        langfuse_tracer=None,
    )
    service.graph.ainvoke = AsyncMock(return_value={})
    return service


@pytest.mark.asyncio
async def test_thread_id_is_set_under_configurable_key():
    """LangGraph reads thread_id from config['configurable'], not the top level."""
    service = _make_service()

    await service.ask(query="what is attention?", user_id="alice")

    sent_config = service.graph.ainvoke.call_args.kwargs["config"]
    assert "configurable" in sent_config, "thread_id must live under config['configurable'], not the top level"
    assert "thread_id" in sent_config["configurable"]
    assert "thread_id" not in sent_config, "thread_id must not also be set at the top level (LangGraph ignores it there)"


@pytest.mark.asyncio
async def test_thread_id_is_stable_across_calls_for_same_user():
    """thread_id must be derived from user_id, not a per-call timestamp."""
    service = _make_service()

    await service.ask(query="first question", user_id="alice")
    first_thread_id = service.graph.ainvoke.call_args.kwargs["config"]["configurable"]["thread_id"]

    await service.ask(query="second question", user_id="alice")
    second_thread_id = service.graph.ainvoke.call_args.kwargs["config"]["configurable"]["thread_id"]

    assert first_thread_id == second_thread_id, "same user, no session_id, should reuse the same thread_id"


@pytest.mark.asyncio
async def test_session_id_starts_a_fresh_thread():
    """An explicit session_id must produce a different thread_id for the same user."""
    service = _make_service()

    await service.ask(query="q1", user_id="alice", session_id="session-1")
    thread_a = service.graph.ainvoke.call_args.kwargs["config"]["configurable"]["thread_id"]

    await service.ask(query="q2", user_id="alice", session_id="session-2")
    thread_b = service.graph.ainvoke.call_args.kwargs["config"]["configurable"]["thread_id"]

    assert thread_a != thread_b


@pytest.mark.asyncio
async def test_different_users_get_different_thread_ids():
    service = _make_service()

    await service.ask(query="q", user_id="alice")
    thread_alice = service.graph.ainvoke.call_args.kwargs["config"]["configurable"]["thread_id"]

    await service.ask(query="q", user_id="bob")
    thread_bob = service.graph.ainvoke.call_args.kwargs["config"]["configurable"]["thread_id"]

    assert thread_alice != thread_bob
