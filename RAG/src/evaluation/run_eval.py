import asyncio
import logging
import os
from typing import List

from src.config import get_settings
from src.evaluation.harness import CaseResult, run_harness
from src.evaluation.persistence import save_run
from src.services.agents.factory import make_agentic_rag_service
from src.services.embeddings.factory import make_embeddings_service
from src.services.langfuse.factory import make_langfuse_tracer
from src.services.ollama.factory import make_ollama_client
from src.services.opensearch.factory import make_opensearch_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _print_score_table(results: List[CaseResult]) -> None:
    metrics = sorted({metric for r in results for metric in r.scores})
    header = f"{'Case':<32}" + "".join(f"{m:<26}" for m in metrics) + "Status"
    print(header)
    print("-" * len(header))
    for r in results:
        row = f"{r.case_id:<32}"
        for m in metrics:
            score = r.scores.get(m)
            row += f"{score:<26.3f}" if score is not None else f"{'--':<26}"
        row += r.status
        print(row)


async def main() -> None:
    """Run the eval harness end to end against /ask-agentic and print + persist results.

    Run with: uv run python -m src.evaluation.run_eval
    """
    settings = get_settings()
    if settings.eval.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.eval.openai_api_key)

    opensearch_client = make_opensearch_client(settings)
    embeddings_client = make_embeddings_service(settings)
    ollama_client = make_ollama_client()
    langfuse_tracer = make_langfuse_tracer()

    service = make_agentic_rag_service(
        opensearch_client=opensearch_client,
        ollama_client=ollama_client,
        embeddings_client=embeddings_client,
        langfuse_tracer=langfuse_tracer,
    )

    logger.info(f"Running eval harness against /ask-agentic with judge model {settings.eval.judge_model}")
    results = await run_harness(service, settings.eval.golden_dataset_path, settings.eval.judge_model)

    _print_score_table(results)

    run_path = save_run(results, settings.eval.results_dir)
    logger.info(f"Run persisted to {run_path}")

    errored = [r for r in results if r.status == "errored"]
    if errored:
        logger.warning(f"{len(errored)}/{len(results)} cases errored — see Status column above")


if __name__ == "__main__":
    asyncio.run(main())
