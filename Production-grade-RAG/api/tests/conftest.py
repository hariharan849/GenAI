import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio


@pytest.fixture
def tmp_results_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs"


@pytest.fixture
def mock_agentic_rag_service() -> MagicMock:
    service = MagicMock()
    service.ask = AsyncMock(
        return_value={
            "answer": "Nuke uses nodes for compositing.",
            "sources": [],
            "retrieval_context": ["Context chunk 1", "Context chunk 2"],
            "reasoning_steps": [],
            "retrieval_attempts": 1,
            "trace_id": "test-trace-id",
        }
    )
    return service
