from unittest.mock import MagicMock

from api.repositories.rag_interaction import record_rag_interaction
from api.schemas.api.ask import AskRequest


def test_record_rag_interaction_stores_only_request_metadata_and_final_response() -> None:
    session = MagicMock()
    request = AskRequest(
        query="How do I use Blur?",
        top_k=5,
        use_hybrid=False,
        model="llama3.2:1b",
        categories=["filter"],
        user_id="alice",
        session_id="session-1",
    )

    record_rag_interaction(session, "/ask", request, "Use the Blur node to soften an image.")

    interaction = session.add.call_args.args[0]
    assert interaction.endpoint == "/ask"
    assert interaction.user_request == "How do I use Blur?"
    assert interaction.final_response == "Use the Blur node to soften an image."
    assert interaction.user_metadata == {
        "user_id": "alice",
        "session_id": "session-1",
        "model": "llama3.2:1b",
        "top_k": 5,
        "use_hybrid": False,
        "categories": ["filter"],
        "knowledge_source": "nuke",
    }
    session.commit.assert_called_once()


def test_record_rag_interaction_rolls_back_when_capture_fails() -> None:
    session = MagicMock()
    session.commit.side_effect = RuntimeError("database unavailable")

    record_rag_interaction(session, "/ask-agentic", AskRequest(query="What is Merge?"), "Merge composites images.")

    session.rollback.assert_called_once()
