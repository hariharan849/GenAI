import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.models import Variable

# For true Kubernetes deployment, uncomment and update _create_batch_pod_tasks() to use KubernetesPodOperator:
# from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator

from nuke_ingestion.graph import extract_nuke_kg
from nuke_ingestion.indexing import (
    index_nuke_docs_ray,
    index_nuke_docs_dynamic,
    index_nuke_docs_batch,
    DEFAULT_NUM_PODS,
)
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


def index_finalize(**context) -> dict:
    """Aggregate batch results from all parallel K8s indexing pods and finalize.

    Pulls results from all batch tasks, aggregates statistics, and returns
    summary statistics.
    """
    import logging
    logger = logging.getLogger(__name__)

    ti = context.get("ti")
    if not ti:
        logger.warning("No task instance available; cannot finalize batch results")
        return {"total_pages_indexed": 0, "total_chunks_indexed": 0, "total_errors": 0}

    # Pull batch metadata to know how many batch tasks to expect
    batch_metadata = ti.xcom_pull(task_ids="index_prepare_batches", key="batch_metadata")
    if not batch_metadata or batch_metadata.get("num_batches", 0) == 0:
        logger.info("No batches to finalize")
        return {"total_pages_indexed": 0, "total_chunks_indexed": 0, "total_errors": 0}

    num_batches = batch_metadata["num_batches"]
    total_pages_indexed = 0
    total_chunks_indexed = 0
    total_error_count = 0

    # Aggregate results from all batch tasks
    for batch_id in range(num_batches):
        task_id = f"index_batch_{batch_id}"
        try:
            batch_result = ti.xcom_pull(task_ids=task_id, key="return_value")
            if batch_result:
                total_pages_indexed += batch_result.get("pages_indexed", 0)
                total_chunks_indexed += batch_result.get("chunks_indexed", 0)
                error_count = len(batch_result.get("error_page_ids", []))
                total_error_count += error_count
                logger.info(
                    f"Batch {batch_id}: {batch_result.get('pages_indexed', 0)} pages, "
                    f"{batch_result.get('chunks_indexed', 0)} chunks, {error_count} errors"
                )
        except Exception as e:
            logger.warning(f"Could not pull results from batch {batch_id}: {e}")

    logger.info(
        f"Index finalization complete: {total_pages_indexed} pages indexed, "
        f"{total_chunks_indexed} chunks indexed, {total_error_count} errors"
    )

    return {
        "total_pages_indexed": total_pages_indexed,
        "total_chunks_indexed": total_chunks_indexed,
        "total_errors": total_error_count,
    }


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

# ============================================================================
# Parallel indexing workflow with dynamic batching and K8s pods
# ============================================================================

index_prepare_batches = PythonOperator(
    task_id="index_prepare_batches",
    python_callable=index_nuke_docs_dynamic,
    execution_timeout=timedelta(minutes=5),
    dag=dag,
)


def _create_batch_pod_tasks(parent_dag, prepare_task_id: str = "index_prepare_batches"):
    """Dynamically create K8s pod operators for each batch.

    This creates DEFAULT_NUM_PODS number of KubernetesPodOperator tasks,
    each processing one batch of pages in parallel.

    Args:
        parent_dag: The parent DAG to attach tasks to
        prepare_task_id: Task ID of the prepare task that provides batch metadata
    """
    batch_tasks = []

    # Helper Python function to generate batch indices and pass to KubernetesPodOperator
    def _create_batch_pod(batch_id: int) -> str:
        """Create a single K8s pod task for a batch.

        The pod will run index_nuke_docs_batch() with the batch's page IDs.
        """
        task_id = f"index_batch_{batch_id}"

        # Use a Python callable to retrieve batch page IDs from XCom and pass to K8s pod
        def _get_batch_page_ids(**context):
            ti = context["ti"]
            batch_metadata = ti.xcom_pull(
                task_ids=prepare_task_id, key="batch_metadata"
            )
            if not batch_metadata:
                raise ValueError(
                    "No batch metadata found. index_prepare_batches may have failed."
                )

            batches = batch_metadata.get("batches", [])
            if batch_id >= len(batches):
                raise ValueError(
                    f"Batch ID {batch_id} out of range ({len(batches)} batches)"
                )

            batch_page_ids = batches[batch_id].get("page_ids", [])
            return json.dumps(batch_page_ids)

        # Retrieve batch page IDs and create K8s pod task
        return _get_batch_page_ids

    # Create K8s pod operator for each batch
    for batch_id in range(DEFAULT_NUM_PODS):
        task_id = f"index_batch_{batch_id}"

        # We'll create a wrapper Python task that calls index_nuke_docs_batch()
        # In a production setup, this would be containerized in a K8s pod;
        # for now, we simulate it with a PythonOperator
        # (KubernetesPodOperator requires more cluster setup)

        def _batch_indexer(batch_id_val=batch_id, **context):
            """Wrapper to call index_nuke_docs_batch() with batch metadata from XCom."""
            ti = context["ti"]
            batch_metadata = ti.xcom_pull(
                task_ids=prepare_task_id, key="batch_metadata"
            )

            if not batch_metadata:
                logger = __import__("logging").getLogger(__name__)
                logger.warning(f"Batch {batch_id_val}: No batch metadata available")
                return {
                    "batch_id": batch_id_val,
                    "pages_indexed": 0,
                    "chunks_indexed": 0,
                    "error_page_ids": [],
                    "indexed_page_ids": [],
                }

            batches = batch_metadata.get("batches", [])
            if batch_id_val >= len(batches):
                logger = __import__("logging").getLogger(__name__)
                logger.warning(f"Batch {batch_id_val}: Out of range (only {len(batches)} batches)")
                return {
                    "batch_id": batch_id_val,
                    "pages_indexed": 0,
                    "chunks_indexed": 0,
                    "error_page_ids": [],
                    "indexed_page_ids": [],
                }

            batch_page_ids = batches[batch_id_val].get("page_ids", [])
            return index_nuke_docs_batch(batch_page_ids, batch_id_val, **context)

        batch_task = PythonOperator(
            task_id=task_id,
            python_callable=_batch_indexer,
            execution_timeout=timedelta(minutes=25),  # A bit longer than single batch estimate
            dag=parent_dag,
        )
        batch_tasks.append(batch_task)

    return batch_tasks


# Create the batch indexing tasks
batch_tasks = _create_batch_pod_tasks(parent_dag=dag)

index_finalize_task = PythonOperator(
    task_id="index_finalize",
    python_callable=index_finalize,
    execution_timeout=timedelta(minutes=5),
    dag=dag,
)

# ============================================================================
# Rest of the pipeline
# ============================================================================

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

# ============================================================================
# DAG dependencies: parallel indexing and KG extraction
# ============================================================================
# After saving pages to DB, both indexing and KG extraction can proceed in parallel

setup_task >> scrape_task >> save_task >> [index_prepare_batches, kg_task]
index_prepare_batches >> batch_tasks >> index_finalize_task
[index_finalize_task, kg_task] >> report_task >> cleanup_task
