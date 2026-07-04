import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from deepeval.metrics import AnswerRelevancyMetric, ContextualRelevancyMetric, FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from api.evaluation.dataset import GoldenCase, load_golden_dataset
from api.services.agents.agentic_rag import AgenticRAGService

logger = logging.getLogger(__name__)


@dataclass
class CaseResult:
    """Outcome of scoring a single golden case.

    :cvar status: "scored" on success, "errored" if the case raised — an
        errored case is excluded from aggregates but never aborts the run.
    """

    case_id: str
    question: str
    status: str
    expected_output: str
    expected_retrieval_context: Optional[List[str]] = None
    actual_output: Optional[str] = None
    retrieval_context: List[str] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None


def _build_metrics(judge_model: str) -> List:
    """RAG triad: faithfulness + answer relevancy for the generator, contextual
    relevancy for the retriever. Judge model is a cloud LLM, never the
    production Ollama model — see EvalSettings docstring for why.
    """
    return [
        FaithfulnessMetric(model=judge_model),
        AnswerRelevancyMetric(model=judge_model),
        ContextualRelevancyMetric(model=judge_model),
    ]


def _score_case_sync(test_case: LLMTestCase, metrics: list) -> Dict[str, float]:
    """Run DeepEval metrics synchronously — called via run_in_executor to avoid blocking the event loop."""
    scores: Dict[str, float] = {}
    for metric in metrics:
        metric.measure(test_case)
        scores[metric.__class__.__name__] = metric.score
    return scores


async def run_case(service: AgenticRAGService, case: GoldenCase, judge_model: str) -> CaseResult:
    """Run one golden case through the agentic RAG pipeline and score it.

    Failures (Ollama timeout, judge API error, etc.) are caught here so one
    bad case never aborts the run — it's recorded as "errored" and excluded
    from aggregate scores.
    """
    try:
        result = await service.ask(query=case.question, user_id="eval_harness")
        actual_output = result["answer"]
        retrieval_context = result.get("retrieval_context") or []

        if not retrieval_context:
            logger.warning(f"[{case.case_id}] no retrieval context returned — contextual metrics score against empty context")

        test_case = LLMTestCase(
            input=case.question,
            actual_output=actual_output,
            expected_output=case.expected_output,
            retrieval_context=retrieval_context,
        )

        loop = asyncio.get_running_loop()
        scores = await loop.run_in_executor(None, _score_case_sync, test_case, _build_metrics(judge_model))

        return CaseResult(
            case_id=case.case_id,
            question=case.question,
            expected_output=case.expected_output,
            expected_retrieval_context=case.expected_retrieval_context,
            actual_output=actual_output,
            retrieval_context=retrieval_context,
            status="scored",
            scores=scores,
        )
    except Exception as e:
        logger.warning(f"[{case.case_id}] eval case failed, recording as errored: {e}")
        return CaseResult(
            case_id=case.case_id,
            question=case.question,
            expected_output=case.expected_output,
            expected_retrieval_context=case.expected_retrieval_context,
            status="errored",
            error=str(e),
        )


async def run_harness_from_cases(
    service: AgenticRAGService,
    cases: List[GoldenCase],
    judge_model: str,
    progress_cb: Optional[Callable[[], None]] = None,
) -> List[CaseResult]:
    """Run harness from pre-loaded cases. Called by the eval router (cases already parsed from upload).

    progress_cb is called after each case — used to increment the in-memory completed counter.
    """
    results = []
    for case in cases:
        results.append(await run_case(service, case, judge_model))
        if progress_cb:
            progress_cb()
    return results


async def run_harness(service: AgenticRAGService, dataset_path: str, judge_model: str) -> List[CaseResult]:
    """Run every golden case in the dataset through the pipeline and score it.

    :param service: A constructed AgenticRAGService (the /ask-agentic pipeline).
    :param dataset_path: Path to the golden dataset YAML.
    :param judge_model: DeepEval judge model name (e.g. "gpt-4o-mini").
    :returns: One CaseResult per golden case, in dataset order.
    """
    cases = load_golden_dataset(dataset_path)
    results = []
    for case in cases:
        results.append(await run_case(service, case, judge_model))
    return results
