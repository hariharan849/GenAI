from unittest.mock import patch

import pytest

from api.services.guardrails.presidio import PresidioRedactor


def test_presidio_engine_system_exit_becomes_runtime_error():
    redactor = PresidioRedactor()

    with patch("presidio_analyzer.AnalyzerEngine", side_effect=SystemExit(1)):
        with pytest.raises(RuntimeError, match="Presidio engine initialization failed"):
            redactor.redact_text("What does the Blur node do?")


def test_presidio_engine_load_failure_is_cached():
    redactor = PresidioRedactor()

    with patch("presidio_analyzer.AnalyzerEngine", side_effect=SystemExit(1)) as analyzer_cls:
        with pytest.raises(RuntimeError, match="Presidio engine initialization failed"):
            redactor.redact_text("What does the Blur node do?")
        with pytest.raises(RuntimeError, match="previously failed"):
            redactor.redact_text("What does the Merge node do?")

    analyzer_cls.assert_called_once()
