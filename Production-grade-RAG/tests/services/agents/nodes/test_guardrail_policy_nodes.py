from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from api.services.agents.context import Context
from api.services.agents.models import GuardrailScoring, SourceItem
from api.services.agents.nodes.input_guardrail_node import ainvoke_input_guardrail_step, continue_after_input_guardrail
from api.services.agents.nodes.output_guardrail_node import ainvoke_output_guardrail_step, continue_after_output_guardrail
from api.services.guardrails.models import GuardrailLayer, PolicyAction, PolicyDecision


class FakePolicy:
    def __init__(self, input_decision=None, output_decision=None):
        self.input_decision = input_decision
        self.output_decision = output_decision
        self.output_prompt = None
        self.output_response = None

    async def check_input(self, text: str):
        return self.input_decision

    async def check_output(self, prompt: str, response: str):
        self.output_prompt = prompt
        self.output_response = response
        return self.output_decision

    def grounding_failed(self, reason: str):
        return PolicyDecision(
            layer=GuardrailLayer.OUTPUT,
            action=PolicyAction.BLOCK,
            reason=reason,
            categories=["grounding_failed"],
        )


def runtime(policy):
    return SimpleNamespace(
        context=Context(
            ollama_client=None,
            opensearch_client=None,
            embeddings_client=None,
            langfuse_tracer=None,
            guardrail_policy=policy,
        )
    )


@pytest.mark.asyncio
async def test_input_node_writes_sanitized_query_and_metadata():
    policy = FakePolicy(
        input_decision=PolicyDecision(
            layer=GuardrailLayer.INPUT,
            action=PolicyAction.REDACT,
            reason="PII redacted; input allowed",
            sanitized_text="[PERSON] asks about Merge",
            pii_redacted=True,
        )
    )
    state = {"messages": [HumanMessage(content="Alex asks about Merge")], "metadata": {}}

    result = await ainvoke_input_guardrail_step(state, runtime(policy))

    assert result["guardrail_result"].score == 100
    assert result["pii_redacted"] is True
    assert result["sanitized_query"] == "[PERSON] asks about Merge"
    assert result["metadata"]["guardrails"]["input"]["action"] == "redact"


def test_input_route_uses_safety_refusal_for_block():
    state = {"guardrail_result": GuardrailScoring(score=0, reason="unsafe")}

    assert continue_after_input_guardrail(state, runtime(None)) == "safety_refusal"


@pytest.mark.asyncio
async def test_output_node_routes_unsafe_to_safety_refusal():
    policy = FakePolicy(
        output_decision=PolicyDecision(
            layer=GuardrailLayer.OUTPUT,
            action=PolicyAction.BLOCK,
            reason="Llama Guard classified content as unsafe",
            categories=["S1"],
        )
    )
    state = {
        "messages": [HumanMessage(content="How do I use Merge?"), AIMessage(content="unsafe answer")],
        "sanitized_query": "[PERSON] asks about Merge",
        "relevant_sources": [],
        "metadata": {},
    }

    result = await ainvoke_output_guardrail_step(state, runtime(policy))

    assert result["output_guardrail_result"].score == 0
    assert result["metadata"]["guardrails"]["output"]["categories"] == ["S1"]
    assert continue_after_output_guardrail(result, runtime(policy)) == "safety_refusal"
    assert policy.output_prompt == "[PERSON] asks about Merge"


@pytest.mark.asyncio
async def test_grounding_failure_routes_to_out_of_scope_not_safety():
    state = {
        "messages": [HumanMessage(content="How do I use Merge?"), AIMessage(content="No citation here")],
        "relevant_sources": [SourceItem(url="https://example.test/merge", node_name="Merge")],
        "metadata": {},
    }

    result = await ainvoke_output_guardrail_step(state, runtime(FakePolicy()))

    assert result["output_guardrail_result"].score == 0
    assert continue_after_output_guardrail(result, runtime(None)) == "out_of_scope"
