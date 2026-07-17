"""Configuration for the researcher service."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_MODEL = "gpt-5.5"
MAX_REQUEST_CHARS = 32_000


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    openai_api_key: str
    openai_model: str
    public_url: str

    @classmethod
    def from_environment(cls) -> Settings:
        """Load local `.env` values without overriding deployment environment."""
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY must be configured before research can run."
            )

        port = os.getenv("PORT", "8001")
        return cls(
            openai_api_key=api_key,
            openai_model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            public_url=os.getenv("A2A_PUBLIC_URL", f"http://localhost:{port}").rstrip(
                "/"
            ),
        )
