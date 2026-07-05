import logging
from typing import Any

from sqlalchemy.orm import Session

from api.models.rag_interaction import RAGInteraction
from api.schemas.api.ask import AskRequest

logger = logging.getLogger(__name__)


class RAGInteractionRepository:
    def __init__(self, session: Session):
        self.session = session

    def record_final_response(self, endpoint: str, request: AskRequest, final_response: str) -> RAGInteraction:
        interaction = RAGInteraction(
            endpoint=endpoint,
            user_request=request.query,
            user_metadata=_build_user_metadata(request),
            final_response=final_response,
        )
        self.session.add(interaction)
        self.session.commit()
        self.session.refresh(interaction)
        return interaction


def _build_user_metadata(request: AskRequest) -> dict[str, Any]:
    return {
        "user_id": request.user_id,
        "session_id": request.session_id,
        "model": request.model,
        "top_k": request.top_k,
        "use_hybrid": request.use_hybrid,
        "categories": request.categories,
        "knowledge_source": request.knowledge_source,
    }


def record_rag_interaction(session: Session, endpoint: str, request: AskRequest, final_response: str) -> None:
    try:
        RAGInteractionRepository(session).record_final_response(endpoint, request, final_response)
    except Exception as exc:
        session.rollback()
        logger.warning("Failed to record RAG interaction for %s: %s", endpoint, exc)
