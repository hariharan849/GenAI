"""Register the nuke_docs_ingestion flow as a Prefect deployment.

Run directly (python deployments/nuke_ingestion_deployment.py) or via the
entrypoint.sh on worker startup. Idempotent — safe to run on every restart.
"""

from flows.nuke_docs_ingestion import nuke_docs_ingestion_flow

if __name__ == "__main__":
    nuke_docs_ingestion_flow.from_source(
        source="/app",
        entrypoint="flows/nuke_docs_ingestion.py:nuke_docs_ingestion_flow",
    ).deploy(
        name="nuke-docs-ingestion",
        work_pool_name="local-process-pool",
        # Manual trigger only — set to a cron string (e.g. "0 0 1 */3 *") once stable
        schedules=[],
    )
