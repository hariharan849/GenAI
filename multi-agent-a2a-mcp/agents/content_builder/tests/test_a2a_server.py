import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import claude_service
from main import create_app


class FakeContentBuilder:
    async def generate(self, research_findings: str) -> str:
        return "# Course module"


class FailingContentBuilder:
    async def generate(self, research_findings: str) -> str:
        raise RuntimeError("upstream failed")


def test_agent_card_advertises_streaming_content_builder() -> None:
    app = create_app(builder=FakeContentBuilder(), public_url="https://example.test")

    response = TestClient(app).get("/a2a/agent/.well-known/agent-card.json")

    assert response.status_code == 200
    card = response.json()
    assert card["name"] == "content_builder"
    assert card["url"] == "https://example.test/a2a/agent"
    assert card["capabilities"]["streaming"] is True


def test_health_is_a_liveness_check() -> None:
    app = create_app(builder=FakeContentBuilder(), public_url="https://example.test")

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_default_app_uses_the_demo_bedrock_model(monkeypatch) -> None:
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    monkeypatch.setattr(claude_service, "load_local_environment", lambda: False)
    monkeypatch.setattr(
        claude_service.BedrockContentBuilder,
        "_create_client",
        staticmethod(lambda _: object()),
    )

    assert create_app(public_url="https://example.test")


def test_a2a_message_returns_course_module_artifact() -> None:
    app = create_app(builder=FakeContentBuilder(), public_url="https://example.test")
    request = {
        "jsonrpc": "2.0",
        "id": "request-1",
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": "message-1",
                "role": "user",
                "parts": [{"kind": "text", "text": "Approved findings"}],
            }
        },
    }

    response = TestClient(app).post("/a2a/agent", json=request)

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["status"]["state"] == "completed"
    assert result["artifacts"][0]["name"] == "course-module.md"
    assert result["artifacts"][0]["parts"][0]["text"] == "# Course module"


def test_a2a_stream_emits_completed_course_module() -> None:
    app = create_app(builder=FakeContentBuilder(), public_url="https://example.test")
    request = {
        "jsonrpc": "2.0",
        "id": "request-2",
        "method": "message/stream",
        "params": {
            "message": {
                "kind": "message",
                "messageId": "message-2",
                "role": "user",
                "parts": [{"kind": "text", "text": "Approved findings"}],
            }
        },
    }

    with TestClient(app).stream("POST", "/a2a/agent", json=request) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "course-module.md" in body
    assert "completed" in body


def test_a2a_message_returns_safe_failure_for_generation_error() -> None:
    app = create_app(builder=FailingContentBuilder(), public_url="https://example.test")
    request = {
        "jsonrpc": "2.0",
        "id": "request-3",
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": "message-3",
                "role": "user",
                "parts": [{"kind": "text", "text": "Approved findings"}],
            }
        },
    }

    response = TestClient(app).post("/a2a/agent", json=request)

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["status"]["state"] == "failed"
    assert result["status"]["message"]["parts"][0]["text"] == (
        "Course generation failed. Please retry."
    )
