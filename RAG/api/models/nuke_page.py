import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from api.db.interfaces.postgresql import Base


class NukePage(Base):
    __tablename__ = "nuke_pages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(String, unique=True, nullable=False, index=True)
    node_name = Column(String, nullable=False)
    section = Column(String, nullable=False)
    raw_content = Column(Text, nullable=False)
    nuke_version = Column(String, nullable=False)
    scraped_at = Column(DateTime, nullable=False)
    nuke_pages_indexed = Column(Boolean, default=False, nullable=False, index=True)
    indexed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
