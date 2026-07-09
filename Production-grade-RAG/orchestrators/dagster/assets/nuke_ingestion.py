import json
import logging
import os
from datetime import datetime

from dagster import (
    AssetExecutionContext,
    DynamicOut,
    DynamicOutput,
    MetadataValue,
    OpExecutionContext,
    asset,
    job,
    op,
)

logger = logging.getLogger(__name__)

NUKE_VERSION = "17.0"


def _scrape_nuke_pages(log) -> list[dict]:
    from nuke_ingestion.scraping import scrape_nuke_reference_guide

    log.info(f"Starting Nuke {NUKE_VERSION} docs scrape")
    # scrape_nuke_reference_guide writes to a temp file and returns its path.
    # With no Airflow context (no ti), it skips XCom and just returns the result dict.
    result = scrape_nuke_reference_guide()
    file_path = result["file"]

    try:
        with open(file_path) as f:
            pages = json.load(f)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    log.info(f"Scraped {len(pages)} pages from Nuke {NUKE_VERSION} docs")
    return pages


def _save_nuke_pages(log, pages: list[dict]) -> dict:
    from api.db.factory import make_database
    from api.repositories.nuke_page import NukePageRepository

    if not pages:
        log.info("No pages to save")
        return {"pages_scraped": 0, "pages_saved": 0, "dupes_skipped": 0}

    db = make_database()
    with db.get_session() as session:
        repo = NukePageRepository(session)
        count, skipped_dupes = repo.upsert_pages(pages, nuke_version=NUKE_VERSION)

    log.info(
        f"Upserted {count} pages (version {NUKE_VERSION}); "
        f"skipped {len(skipped_dupes)} near-duplicates"
    )
    for new_url, canon_url in skipped_dupes:
        log.info(f"  DEDUP: {new_url} skipped (similar to {canon_url})")

    return {
        "pages_scraped": len(pages),
        "pages_saved": count,
        "dupes_skipped": len(skipped_dupes),
    }


def _prepare_index_batches(log) -> dict:
    from nuke_ingestion.indexing import index_nuke_docs_dynamic

    log.info("Preparing dynamic indexing batches for unindexed Nuke pages")
    batch_metadata = index_nuke_docs_dynamic()
    log.info(
        f"Prepared {batch_metadata.get('num_batches', 0)} indexing batches "
        f"for {batch_metadata.get('num_pages', 0)} pages"
    )
    return batch_metadata


def _index_nuke_batch(log, batch: dict) -> dict:
    from nuke_ingestion.indexing import index_nuke_docs_batch

    batch_id = batch["batch_id"]
    page_ids = batch.get("page_ids", [])
    log.info(f"Indexing batch {batch_id} with {len(page_ids)} pages")
    stats = index_nuke_docs_batch(page_ids, batch_id)
    log.info(
        f"Batch {batch_id} indexed {stats.get('pages_indexed', 0)} pages, "
        f"{stats.get('chunks_indexed', 0)} chunks"
    )
    return stats


def _finalize_index_batches(log, batch_results: list[dict]) -> dict:
    if not batch_results:
        log.info("No indexing batches to finalize")
        return {
            "pages_indexed": 0,
            "chunks_indexed": 0,
            "error_page_ids": [],
            "indexed_page_ids": [],
        }

    total_pages_indexed = 0
    total_chunks_indexed = 0
    error_page_ids: set[str] = set()
    indexed_page_ids: list[str] = []

    for result in batch_results:
        total_pages_indexed += result.get("pages_indexed", 0)
        total_chunks_indexed += result.get("chunks_indexed", 0)
        error_page_ids.update(result.get("error_page_ids", []))
        indexed_page_ids.extend(result.get("indexed_page_ids", []))

    stats = {
        "pages_indexed": total_pages_indexed,
        "chunks_indexed": total_chunks_indexed,
        "error_page_ids": sorted(error_page_ids),
        "indexed_page_ids": indexed_page_ids,
    }
    log.info(f"Index finalization stats: {stats}")
    return stats


def _extract_nuke_kg(log, index_stats: dict) -> dict:
    from api.services.graph.ingestion import extract_kg_for_indexed_pages

    stats = extract_kg_for_indexed_pages(index_stats.get("indexed_page_ids", []))
    log.info(f"KG extraction stats: {stats}")
    return stats


def _generate_nuke_report(log, save_stats: dict, index_stats: dict, kg_stats: dict) -> dict:
    report = {
        "pages_scraped": save_stats.get("pages_scraped", 0),
        "pages_saved": save_stats.get("pages_saved", 0),
        "dupes_skipped": save_stats.get("dupes_skipped", 0),
        "pages_indexed": index_stats.get("pages_indexed", 0),
        "chunks_indexed": index_stats.get("chunks_indexed", 0),
        "kg_pages_extracted": kg_stats.get("kg_pages_extracted", 0),
        "kg_pages_failed": kg_stats.get("kg_pages_failed", 0),
        "kg_triples_written": kg_stats.get("kg_triples_written", 0),
        "kg_skipped": kg_stats.get("kg_skipped", False),
        "completed_at": datetime.now().isoformat(),
    }
    log.info(f"Nuke ingestion report: {report}")
    return report


@asset(group_name="nuke_ingestion", description="Scraped Nuke 17.0 reference guide pages")
def scraped_nuke_pages(context: AssetExecutionContext) -> list[dict]:
    pages = _scrape_nuke_pages(context.log)
    context.add_output_metadata({"pages_scraped": MetadataValue.int(len(pages))})
    return pages


@asset(group_name="nuke_ingestion", description="Nuke pages upserted to PostgreSQL")
def saved_nuke_pages(context: AssetExecutionContext, scraped_nuke_pages: list[dict]) -> dict:
    stats = _save_nuke_pages(context.log, scraped_nuke_pages)
    context.add_output_metadata({
        "pages_scraped": MetadataValue.int(stats["pages_scraped"]),
        "pages_saved": MetadataValue.int(stats["pages_saved"]),
        "dupes_skipped": MetadataValue.int(stats["dupes_skipped"]),
    })
    return stats


@asset(group_name="nuke_ingestion", description="Nuke docs chunked, embedded, and indexed into OpenSearch via Ray Data")
def indexed_nuke_docs(context: AssetExecutionContext, saved_nuke_pages: dict) -> dict:
    batch_metadata = _prepare_index_batches(context.log)
    batch_results = [
        _index_nuke_batch(context.log, batch)
        for batch in batch_metadata.get("batches", [])
    ]
    stats = _finalize_index_batches(context.log, batch_results)

    context.log.info(
        f"Indexed {stats.get('pages_indexed', 0)} pages, "
        f"{stats.get('chunks_indexed', 0)} chunks"
    )
    context.add_output_metadata({
        "pages_indexed": MetadataValue.int(stats.get("pages_indexed", 0)),
        "chunks_indexed": MetadataValue.int(stats.get("chunks_indexed", 0)),
    })
    return stats


@asset(group_name="nuke_ingestion", description="Nuke knowledge graph triples extracted into Neo4j")
def extracted_nuke_kg(context: AssetExecutionContext, indexed_nuke_docs: dict) -> dict:
    stats = _extract_nuke_kg(context.log, indexed_nuke_docs)
    context.add_output_metadata({k: MetadataValue.text(str(v)) for k, v in stats.items()})
    return stats


@asset(group_name="nuke_ingestion", description="Summary report of the Nuke ingestion run")
def nuke_ingestion_report(
    context: AssetExecutionContext,
    saved_nuke_pages: dict,
    indexed_nuke_docs: dict,
    extracted_nuke_kg: dict,
) -> dict:
    report = _generate_nuke_report(
        context.log,
        saved_nuke_pages,
        indexed_nuke_docs,
        extracted_nuke_kg,
    )
    context.add_output_metadata({k: MetadataValue.text(str(v)) for k, v in report.items()})
    return report


@op(name="scrape_nuke_docs")
def scrape_nuke_docs_op(context: OpExecutionContext) -> list[dict]:
    return _scrape_nuke_pages(context.log)


@op(name="save_nuke_pages_to_db")
def save_nuke_pages_to_db_op(context: OpExecutionContext, pages: list[dict]) -> dict:
    return _save_nuke_pages(context.log, pages)


@op(name="index_prepare_batches", out=DynamicOut(dict))
def index_prepare_batches_op(context: OpExecutionContext, save_stats: dict):
    batch_metadata = _prepare_index_batches(context.log)
    for batch in batch_metadata.get("batches", []):
        yield DynamicOutput(
            batch,
            mapping_key=f"batch_{batch['batch_id']}",
            metadata={"page_count": batch.get("page_count", 0)},
        )


@op(name="index_nuke_docs_batch")
def index_nuke_docs_batch_op(context: OpExecutionContext, batch: dict) -> dict:
    return _index_nuke_batch(context.log, batch)


@op(name="index_finalize")
def index_finalize_op(context: OpExecutionContext, batch_results: list[dict]) -> dict:
    return _finalize_index_batches(context.log, batch_results)


@op(name="extract_nuke_kg")
def extract_nuke_kg_op(context: OpExecutionContext, index_stats: dict) -> dict:
    return _extract_nuke_kg(context.log, index_stats)


@op(name="generate_nuke_report")
def generate_nuke_report_op(
    context: OpExecutionContext,
    save_stats: dict,
    index_stats: dict,
    kg_stats: dict,
) -> dict:
    return _generate_nuke_report(context.log, save_stats, index_stats, kg_stats)


@job(name="nuke_docs_ingestion")
def nuke_docs_ingestion_job():
    pages = scrape_nuke_docs_op()
    save_stats = save_nuke_pages_to_db_op(pages)
    batch_results = index_prepare_batches_op(save_stats).map(index_nuke_docs_batch_op)
    index_stats = index_finalize_op(batch_results.collect())
    kg_stats = extract_nuke_kg_op(index_stats)
    generate_nuke_report_op(save_stats, index_stats, kg_stats)
