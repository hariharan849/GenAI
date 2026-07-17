# ruff: noqa: E402

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

JUDGE_DIR = Path(__file__).parents[1] / "agents" / "judge"
sys.path.insert(0, str(JUDGE_DIR))

from judge_service.app import AGENT_CARD_PATH, AGENT_PATH, create_app
from judge_service.service import JudgeService


class FakeSourceClient:
    enabled = True

    async def verify_citations(self, urls: list[str]) -> dict[str, object]:
        return {
            "citations": [
                {"submitted_url": url, "status": "verified", "evidence": "Evidence."}
                for url in urls
            ]
        }


def test_judge_a2a_card_and_message_response(monkeypatch) -> None:
    monkeypatch.setenv("A2A_PUBLIC_URL", "http://testserver")
    service = JudgeService(
        lambda _: '{"status":"pass","feedback":"Ready."}', FakeSourceClient()
    )

    with TestClient(create_app(service)) as client:
        card = client.get(AGENT_CARD_PATH)
        response = client.post(
            AGENT_PATH,
            json={
                "jsonrpc": "2.0",
                "id": "request-1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": "message-1",
                        "role": "user",
                        "parts": [
                            {
                                "kind": "text",
                                "text": "research\n\n## Sources\n- https://example.com/source",
                            }
                        ],
                    }
                },
            },
        )

    assert card.status_code == 200
    assert card.json()["url"] == "http://testserver/a2a/agent"
    assert card.json()["capabilities"]["streaming"] is True
    assert response.status_code == 200
    artifact_text = response.json()["result"]["artifacts"][0]["parts"][0]["text"]
    assert json.loads(artifact_text) == {"status": "pass", "feedback": "Ready."}
