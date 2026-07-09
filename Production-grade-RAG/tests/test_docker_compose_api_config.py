from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_api_compose_disables_llama_guard_by_default_for_local_stack():
    compose = (ROOT / "docker-compose.yaml").read_text()

    assert "GUARDRAILS__LLAMA_GUARD_ENABLED=${GUARDRAILS__LLAMA_GUARD_ENABLED:-false}" in compose


def test_env_example_documents_llama_guard_opt_in():
    env_example = (ROOT / ".env_example").read_text()

    assert "GUARDRAILS__LLAMA_GUARD_ENABLED=false" in env_example
    assert "GUARDRAILS__LLAMA_GUARD_FAIL_CLOSED_INPUT=true" in env_example
