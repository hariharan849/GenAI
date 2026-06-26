import json
import logging

from src.db.factory import make_database
from src.repositories.nuke_page import NukePageRepository

logger = logging.getLogger(__name__)


def save_nuke_pages(**context) -> dict:
    from nuke_docs_ingestion import NUKE_VERSION

    ti = context.get("ti")
    scraped_file = ti.xcom_pull(task_ids="scrape_nuke_docs", key="scraped_file") if ti else None
    if not scraped_file:
        raise ValueError("No scraped_file in XCom — upstream scrape task may have failed")

    with open(scraped_file) as f:
        pages = json.load(f)

    if not pages:
        logger.info("No pages to save")
        if ti:
            ti.xcom_push(key="pages_saved", value=0)
            ti.xcom_push(key="dupes_skipped", value=0)
        return {"pages_saved": 0, "dupes_skipped": 0}

    db = make_database()
    with db.get_session() as session:
        repo = NukePageRepository(session)
        count, skipped_dupes = repo.upsert_pages(pages, nuke_version=NUKE_VERSION)

    logger.info(
        f"Upserted {count} nuke pages to DB (version {NUKE_VERSION}); "
        f"skipped {len(skipped_dupes)} near-duplicates"
    )
    if skipped_dupes:
        for new_url, canon_url in skipped_dupes:
            logger.info(f"  DEDUP: {new_url} skipped (similar to {canon_url})")

    if ti:
        ti.xcom_push(key="pages_saved", value=count)
        ti.xcom_push(key="dupes_skipped", value=len(skipped_dupes))
    return {"pages_saved": count, "dupes_skipped": len(skipped_dupes)}
