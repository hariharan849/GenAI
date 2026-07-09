from dagster import Definitions

from assets.nuke_ingestion import (
    extracted_nuke_kg,
    indexed_nuke_docs,
    nuke_docs_ingestion_job,
    nuke_ingestion_report,
    saved_nuke_pages,
    scraped_nuke_pages,
)

defs = Definitions(
    assets=[scraped_nuke_pages, saved_nuke_pages, indexed_nuke_docs, extracted_nuke_kg, nuke_ingestion_report],
    jobs=[nuke_docs_ingestion_job],
    schedules=[],
)
