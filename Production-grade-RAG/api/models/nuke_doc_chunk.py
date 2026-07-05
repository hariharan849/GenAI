import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, REAL, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from api.db.interfaces.postgresql import Base


class NukeDocChunk(Base):
    __tablename__ = "nuke_doc_chunks"

    chunk_id = Column(String, primary_key=True)
    page_id = Column(UUID(as_uuid=True), ForeignKey("nuke_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_doc_id = Column(String, nullable=True, index=True)
    url = Column(String, nullable=False, index=True)
    nuke_node_name = Column(String, nullable=False, index=True)
    section = Column(String, nullable=False, index=True)
    section_name = Column(String, nullable=True)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(ARRAY(REAL), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


Index("ix_nuke_doc_chunks_url_chunk_index", NukeDocChunk.url, NukeDocChunk.chunk_index, unique=True)
