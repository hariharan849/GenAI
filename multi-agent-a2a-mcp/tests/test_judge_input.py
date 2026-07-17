# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

JUDGE_DIR = Path(__file__).parents[1] / "agents" / "judge"
sys.path.insert(0, str(JUDGE_DIR))

from judge_service.input_parser import parse_judge_input


def test_parse_judge_input_prefers_structured_context() -> None:
    payload = '{"original_request":"Explain photosynthesis","research_findings":"Plants use light."}'

    judge_input = parse_judge_input(payload)

    assert judge_input.original_request == "Explain photosynthesis"
    assert judge_input.research_findings == "Plants use light."
