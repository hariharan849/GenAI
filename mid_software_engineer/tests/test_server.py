from __future__ import annotations

from fastapi.testclient import TestClient

from mid_software_engineer.tracing import AgentTraceStore, TraceEvent
from mid_software_engineer.server import (
    create_app,
    extract_last_message_content,
    format_content_blocks,
    response_from_agent_result,
    should_construct_agent,
)


def test_config_endpoint_exposes_ui_contract() -> None:
    app = create_app(construct_agent=False)
    client = TestClient(app)

    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["chatkit_api_url"] == "/chatkit"
    assert payload["local_agent_endpoint"] == "/api/agent/message"
    assert "CodeInterpreterMiddleware" in payload["middleware"]
    assert payload["traces_endpoint"] == "/api/traces"
    assert payload["trace_db_path"]


def test_traces_endpoint_returns_recent_rows(tmp_path) -> None:
    store = AgentTraceStore(tmp_path / "traces.sqlite3")
    store.insert(
        TraceEvent(
            id="trace-1",
            thread_id="thread-1",
            run_id=None,
            tool_call_id="call-1",
            tool_name="read_file",
            tool_args_json="{}",
            status="success",
            started_at=1.0,
            ended_at=1.1,
            duration_ms=100,
            error=None,
            skill_name=None,
        )
    )
    app = create_app(construct_agent=False, trace_store=store)
    client = TestClient(app)

    response = client.get("/api/traces")

    assert response.status_code == 200
    assert response.json()["traces"][0]["id"] == "trace-1"


def test_index_contains_chatkit_and_fallback_console() -> None:
    app = create_app(construct_agent=False)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "cdn.platform.openai.com/deployments/chatkit/chatkit.js" in response.text
    assert "<chatkit-widget" in response.text
    assert "/api/agent/message" in response.text
    assert "renderAgentResponse" in response.text
    assert "section-card" in response.text
    assert "action-chip" in response.text


def test_agent_endpoint_can_run_without_constructed_agent() -> None:
    app = create_app(construct_agent=False)
    client = TestClient(app)

    response = client.post("/api/agent/message", json={"message": "hello", "thread_id": "t1"})

    assert response.status_code == 200
    assert response.json()["thread_id"] == "t1"
    assert "disabled" in response.json()["content"]


def test_response_from_agent_result_detects_interrupt() -> None:
    response = response_from_agent_result("t1", {"__interrupt__": [{"value": "approval"}]})

    assert response.interrupted is True
    assert "approval" in response.content


def test_extract_last_message_content_supports_object_messages() -> None:
    class Message:
        content = "done"

    assert extract_last_message_content({"messages": [Message()]}) == "done"


def test_format_content_blocks_renders_text_not_dicts() -> None:
    text = "What backend shape do you want?"
    content = format_content_blocks(
        [
            {"type": "text", "text": text, "annotations": [], "id": "1", "phase": "commentary"},
            {"type": "text", "text": text, "annotations": [], "id": "2", "phase": "final_answer"},
        ]
    )

    assert content == text
    assert "{'type': 'text'" not in content


def test_extract_last_message_content_formats_list_blocks() -> None:
    content = extract_last_message_content(
        {
            "messages": [
                {
                    "content": [
                        {"type": "text", "text": "draft", "phase": "commentary"},
                        {"type": "text", "text": "final", "phase": "final_answer"},
                    ]
                }
            ]
        }
    )

    assert content == "final"


def test_should_not_construct_openai_agent_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)
    monkeypatch.delenv("MID_SE_AGENT_SKIP_CONSTRUCT", raising=False)

    assert should_construct_agent("openai:gpt-5.4") is False
