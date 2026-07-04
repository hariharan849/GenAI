import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

from nuke_ingestion.graph import extract_nuke_kg
from nuke_ingestion.indexing import index_nuke_docs_ray
from nuke_ingestion.reporting import generate_nuke_report
from nuke_ingestion.save import save_nuke_pages
from nuke_ingestion.scraping import scrape_nuke_reference_guide

# Hardcoded — do not expose as a DAG param; change here when upgrading Nuke versions
# to avoid multi-version index collision.
NUKE_VERSION = "17.0"

default_args = {
    "owner": "nuke-curator",
    "depends_on_past": False,
    "start_date": datetime(2026, 6, 14),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "catchup": False,
}

dag = DAG(
    "nuke_docs_ingestion",
    default_args=default_args,
    description="Scrape Foundry Nuke 17.0 reference guide and index into OpenSearch for RAG",
    schedule=None,  # Manual trigger only; consider "@quarterly" once stable
    max_active_runs=1,
    catchup=False,
    tags=["nuke", "docs", "ingestion", "hybrid-search"],
)


def setup_nuke_env(**context):
    logger = __import__("logging").getLogger(__name__)
    logger.info(f"Starting Nuke {NUKE_VERSION} docs ingestion")
    logger.info(f"Target index: nuke-docs-chunks")


def cleanup_nuke_temp(**context):
    """Delete the temp file written by scrape_nuke_docs, plus any orphaned files older than 7 days."""
    import logging
    logger = logging.getLogger(__name__)

    ti = context["ti"]
    scraped_file = ti.xcom_pull(task_ids="scrape_nuke_docs", key="scraped_file")
    if scraped_file and os.path.exists(scraped_file):
        os.remove(scraped_file)
        logger.info(f"Removed temp file: {scraped_file}")

    # Safety net: clean up orphaned files older than 7 days
    for f in Path("/tmp").glob("nuke_pages_*.json"):
        if (time.time() - f.stat().st_mtime) > 7 * 86400:
            f.unlink()
            logger.info(f"Removed orphaned temp file: {f}")


setup_task = PythonOperator(
    task_id="setup_environment",
    python_callable=setup_nuke_env,
    dag=dag,
)

scrape_task = PythonOperator(
    task_id="scrape_nuke_docs",
    python_callable=scrape_nuke_reference_guide,
    execution_timeout=timedelta(minutes=30),  # 500 pages × 1 req/sec ≈ 8 min; 30 min covers retries
    dag=dag,
)

save_task = PythonOperator(
    task_id="save_nuke_pages_to_db",
    python_callable=save_nuke_pages,
    execution_timeout=timedelta(minutes=5),
    dag=dag,
)

index_task = PythonOperator(
    task_id="index_nuke_docs",
    python_callable=index_nuke_docs_ray,
    execution_timeout=timedelta(minutes=20),
    dag=dag,
)

report_task = PythonOperator(
    task_id="generate_nuke_report",
    python_callable=generate_nuke_report,
    dag=dag,
)

kg_task = PythonOperator(
    task_id="extract_nuke_kg",
    python_callable=extract_nuke_kg,
    execution_timeout=timedelta(minutes=20),
    dag=dag,
)

cleanup_task = PythonOperator(
    task_id="cleanup_temp_files",
    python_callable=cleanup_nuke_temp,
    trigger_rule="all_done",  # Run cleanup even if upstream fails
    dag=dag,
)

setup_task >> scrape_task >> save_task >> index_task >> kg_task >> report_task >> cleanup_task
