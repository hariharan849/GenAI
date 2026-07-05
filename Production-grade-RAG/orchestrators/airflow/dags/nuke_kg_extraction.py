from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

from api.db.factory import make_database
from api.repositories.nuke_page import NukePageRepository
from nuke_ingestion.graph import extract_all_pending_nuke_kg

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
    "nuke_kg_extraction",
    default_args=default_args,
    description=(
        "Extract Nuke knowledge graph triples from already-indexed Postgres pages; "
        "does not scrape or index docs."
    ),
    schedule=None,
    max_active_runs=1,
    catchup=False,
    tags=["nuke", "kg", "neo4j", "backfill"],
)


def setup_kg_backfill(**context):
    logger = __import__("logging").getLogger(__name__)
    logger.info("Starting Nuke KG-only extraction backfill")
    logger.info("Source: indexed Postgres pages where kg_extracted is false")
    db = make_database()
    try:
        dag_run = context.get("dag_run")
        conf = getattr(dag_run, "conf", None) or {}
        reset_kg_extracted = bool(conf.get("reset_kg_extracted", False))
        reset_count = 0

        if reset_kg_extracted:
            with db.get_session() as session:
                reset_count = NukePageRepository(session).reset_kg_extracted_for_indexed_pages()
            logger.info("Reset kg_extracted=false for %d indexed page(s)", reset_count)
        else:
            logger.info("Leaving existing kg_extracted state unchanged")

        return {
            "kg_columns_ready": True,
            "reset_kg_extracted": reset_kg_extracted,
            "kg_pages_reset": reset_count,
        }
    finally:
        db.teardown()


setup_task = PythonOperator(
    task_id="setup_kg_backfill",
    python_callable=setup_kg_backfill,
    dag=dag,
)

extract_task = PythonOperator(
    task_id="extract_all_pending_nuke_kg",
    python_callable=extract_all_pending_nuke_kg,
    execution_timeout=timedelta(minutes=20),
    dag=dag,
)

setup_task >> extract_task
