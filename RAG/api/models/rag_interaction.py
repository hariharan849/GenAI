import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from api.db.interfaces.postgresql import Base


class RAGInteraction(Base):
    __tablename__ = "rag_interactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint = Column(String, nullable=False, index=True)
    user_request = Column(Text, nullable=False)
    user_metadata = Column(JSONB, nullable=False, default=dict)
    final_response = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
