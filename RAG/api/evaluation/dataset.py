from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass
class GoldenCase:
    """A single hand-curated RAG eval case, pinned to an already-indexed Nuke docs page.

    :param case_id: Stable identifier for this case, used in run results and diffs.
    :param url: The Nuke documentation URL this question targets —
        pinned so before/after diffs reflect code changes, not ingestion drift.
    :param question: The question put to the agentic RAG pipeline.
    :param expected_output: Reference answer, used by faithfulness/answer-relevancy metrics.
    :param expected_retrieval_context: Optional ground-truth context chunks. When
        absent, metrics that require it are skipped for this case rather than failed.
    """

    case_id: str
    url: str
    question: str
    expected_output: str
    expected_retrieval_context: Optional[List[str]] = None


def load_golden_dataset(path: str) -> List[GoldenCase]:
    """Load golden eval cases from a YAML file.

    :param path: Path to the golden dataset YAML file.
    :returns: List of parsed golden cases.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [GoldenCase(**case) for case in raw["cases"]]
