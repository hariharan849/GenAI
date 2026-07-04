"""Airflow compatibility wrapper for KG ingestion tasks."""

import logging

from api.knowledge_graph.ingestion import extract_kg_for_indexed_pages

logger = logging.getLogger(__name__)


def extract_nuke_kg(**context) -> dict:
    ti = context.get("ti")
    index_stats = ti.xcom_pull(task_ids="index_nuke_docs", key="index_stats") if ti else {}
    index_stats = index_stats or {}
    page_ids = index_stats.get("indexed_page_ids", [])

    stats = extract_kg_for_indexed_pages(page_ids)
    logger.info("Nuke KG extraction report: %s", stats)
    if ti:
        ti.xcom_push(key="kg_stats", value=stats)
    return stats


def extract_all_pending_nuke_kg(**context) -> dict:
    ti = context.get("ti")
    stats = extract_kg_for_indexed_pages()
    logger.info("All-pending Nuke KG extraction report: %s", stats)
    if ti:
        ti.xcom_push(key="kg_stats", value=stats)
    return stats


__all__ = ["extract_all_pending_nuke_kg", "extract_kg_for_indexed_pages", "extract_nuke_kg"]
