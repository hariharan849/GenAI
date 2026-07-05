"""Shared search indexing payloads."""

from typing import Any

from pydantic import BaseModel, Field


class ChunkIndexPayload(BaseModel):
    """Backend-neutral chunk payload accepted by search clients."""

    chunk_data: dict[str, Any]
    embedding: list[float] = Field(min_length=1)
