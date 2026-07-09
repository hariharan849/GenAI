from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from api.services.agents.nodes.grade_documents_node import ainvoke_grade_documents_step


class BrokenOllamaClient:
    pass


@pytest.mark.asyncio
async def test_grade_documents_fallback_sets_score():
    state = {
        "messages": [
            HumanMessage(content="How does Blur work?"),
            ToolMessage(
                content="Blur adds blur to an image using gaussian and other filters. " * 3,
                tool_call_id="retrieve_1",
                name="retrieve_papers",
            ),
        ],
        "retrieved_documents": None,
    }
    runtime = SimpleNamespace(
        context=SimpleNamespace(
            ollama_client=BrokenOllamaClient(),
            model_name="llama3.2:1b",
            langfuse_tracer=None,
        )
    )

    result = await ainvoke_grade_documents_step(state, runtime)

    assert result["routing_decision"] == "generate_answer"
    assert result["grading_results"][0].is_relevant is True
    assert result["grading_results"][0].score == 1.0
