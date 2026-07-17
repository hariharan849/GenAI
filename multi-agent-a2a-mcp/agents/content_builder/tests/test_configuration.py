from __future__ import annotations

import pytest
from claude_service import BedrockSettings


def test_uses_demo_model_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("claude_service.load_local_environment", lambda: False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    assert BedrockSettings.from_environment().model_id == "amazon.nova-micro-v1:0"
