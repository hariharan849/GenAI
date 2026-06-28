from dagster import AssetSelection, Definitions, define_asset_job

from assets.nuke_ingestion import (
    indexed_nuke_docs,
    nuke_ingestion_report,
    saved_nuke_pages,
    scraped_nuke_pages,
)

nuke_docs_ingestion_job = define_asset_job(
    name="nuke_docs_ingestion",
    selection=AssetSelection.groups("nuke_ingestion"),
    description="Scrape Foundry Nuke 17.0 reference guide and index into OpenSearch for RAG",
)

defs = Definitions(
    assets=[scraped_nuke_pages, saved_nuke_pages, indexed_nuke_docs, nuke_ingestion_report],
    jobs=[nuke_docs_ingestion_job],
    schedules=[],
)
