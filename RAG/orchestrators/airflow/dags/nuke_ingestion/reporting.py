import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def generate_nuke_report(**context) -> dict:
    """Log a summary of the Nuke docs ingestion run."""
    ti = context.get("ti")
    scrape_stats = ti.xcom_pull(task_ids="scrape_nuke_docs", key="return_value") if ti else {}
    save_stats = ti.xcom_pull(task_ids="save_nuke_pages_to_db", key="return_value") if ti else {}
    index_stats = ti.xcom_pull(task_ids="index_nuke_docs", key="index_stats") if ti else {}

    scrape_stats = scrape_stats or {}
    save_stats = save_stats or {}
    index_stats = index_stats or {}

    report = {
        "pages_scraped": scrape_stats.get("pages_scraped", 0),
        "pages_saved": save_stats.get("pages_saved", 0),
        "dupes_skipped": save_stats.get("dupes_skipped", 0),
        "pages_indexed": index_stats.get("pages_indexed", 0),
        "chunks_created": index_stats.get("chunks_created", 0),
        "bulk_errors": index_stats.get("bulk_errors", 0),
        "completed_at": datetime.now().isoformat(),
    }

    logger.info(f"Nuke ingestion report: {report}")
    return report
