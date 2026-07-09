import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from api.db.interfaces.postgresql import Base


class NukeParentDocument(Base):
    __tablename__ = "nuke_parent_documents"

    parent_doc_id = Column(String, primary_key=True)
    page_id = Column(UUID(as_uuid=True), ForeignKey("nuke_pages.id", ondelete="CASCADE"), nullable=True, index=True)
    url = Column(String, nullable=False, index=True)
    doc_metadata = Column(JSONB, nullable=False, default=dict)
    page_content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


def parse_optional_uuid(value: object) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
