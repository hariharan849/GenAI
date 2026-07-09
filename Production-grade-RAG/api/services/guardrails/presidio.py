import logging
from typing import Iterable

from .models import PiiRedactionResult

logger = logging.getLogger(__name__)


DEFAULT_PRESIDIO_ENTITIES = [
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "CREDIT_CARD",
    "IP_ADDRESS",
    "PERSON",
    "LOCATION",
]


class PresidioRedactor:
    """Lazy Presidio wrapper for PII redaction."""

    def __init__(
        self,
        entities: Iterable[str] | None = None,
        score_threshold: float = 0.5,
        allowlist_terms: Iterable[str] | None = None,
    ):
        self.entities = list(entities or DEFAULT_PRESIDIO_ENTITIES)
        self.score_threshold = score_threshold
        self.allowlist_terms = {term.lower() for term in (allowlist_terms or [])}
        self._analyzer = None
        self._anonymizer = None
        self._load_error: Exception | None = None

    def _load_engines(self):
        if self._analyzer is not None and self._anonymizer is not None:
            return self._analyzer, self._anonymizer
        if self._load_error is not None:
            raise RuntimeError("Presidio engine initialization previously failed") from self._load_error

        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            from presidio_anonymizer.entities import OperatorConfig

            self._operator_config_cls = OperatorConfig
            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, GeneratorExit)):
                raise
            self._load_error = RuntimeError(f"Presidio engine initialization failed: {e}")
            logger.warning("%s", self._load_error)
            raise self._load_error from e
        return self._analyzer, self._anonymizer

    def redact_text(self, text: str) -> PiiRedactionResult:
        if not text:
            return PiiRedactionResult(original_text=text, redacted_text=text)

        analyzer, anonymizer = self._load_engines()
        analyzer_results = analyzer.analyze(
            text=text,
            language="en",
            entities=self.entities,
            score_threshold=self.score_threshold,
            allow_list=list(self.allowlist_terms),
        )
        analyzer_results = [
            result
            for result in analyzer_results
            if text[result.start : result.end].lower() not in self.allowlist_terms
        ]

        if not analyzer_results:
            return PiiRedactionResult(original_text=text, redacted_text=text)

        operators = {
            entity: self._operator_config_cls("replace", {"new_value": f"[{entity}]"})
            for entity in self.entities
        }
        anonymized = anonymizer.anonymize(
            text=text,
            analyzer_results=analyzer_results,
            operators=operators,
        )
        entities = sorted({result.entity_type for result in analyzer_results})
        return PiiRedactionResult(
            original_text=text,
            redacted_text=anonymized.text,
            pii_redacted=anonymized.text != text,
            entities=entities,
            analyzer_results=[
                {
                    "entity_type": result.entity_type,
                    "start": result.start,
                    "end": result.end,
                    "score": result.score,
                }
                for result in analyzer_results
            ],
        )
