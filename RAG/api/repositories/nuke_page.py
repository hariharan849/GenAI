import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from datasketch import MinHash, MinHashLSH
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.models.nuke_page import NukePage

logger = logging.getLogger(__name__)


def _compute_minhash(text: str, num_perm: int = 128, shingle_size: int = 5) -> MinHash:
    mh = MinHash(num_perm=num_perm)
    normalized = " ".join(text.lower().split())
    for i in range(len(normalized) - shingle_size + 1):
        mh.update(normalized[i : i + shingle_size].encode("utf-8"))
    return mh


class NukePageRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_url(self, url: str) -> Optional[NukePage]:
        stmt = select(NukePage).where(NukePage.url == url)
        return self.session.scalar(stmt)

    def get_all_pages(self) -> list[NukePage]:
        stmt = select(NukePage)
        return list(self.session.scalars(stmt))

    def upsert_pages(
        self,
        pages: list[dict],
        nuke_version: str,
        similarity_threshold: float = 0.85,
    ) -> tuple[int, list[tuple[str, str]]]:
        num_perm = 128
        lsh = MinHashLSH(threshold=similarity_threshold, num_perm=num_perm)

        for ep in self.get_all_pages():
            if ep.raw_content:
                lsh.insert(ep.url, _compute_minhash(ep.raw_content, num_perm))

        count = 0
        skipped: list[tuple[str, str]] = []
        now = datetime.now(timezone.utc)

        for page in pages:
            if not page.get("content"):
                logger.warning(f"Skipping {page.get('url', '?')} — empty content")
                continue

            mh = _compute_minhash(page["content"], num_perm)
            existing = self.get_by_url(page["url"])

            if existing:
                try:
                    lsh.remove(existing.url)
                except KeyError:
                    pass
                lsh.insert(page["url"], mh)
                existing.raw_content = page["content"]
                existing.node_name = page["node_name"]
                existing.section = page["section"]
                existing.nuke_version = nuke_version
                existing.nuke_pages_indexed = False
                existing.scraped_at = now
                count += 1
            else:
                near_dupes = [r for r in lsh.query(mh) if r != page["url"]]
                if near_dupes:
                    logger.warning(
                        f"Skipping near-duplicate: {page['url']} ≈ {near_dupes[0]} "
                        f"(threshold={similarity_threshold})"
                    )
                    skipped.append((page["url"], near_dupes[0]))
                    continue
                lsh.insert(page["url"], mh)
                self.session.add(NukePage(
                    url=page["url"],
                    node_name=page["node_name"],
                    section=page["section"],
                    raw_content=page["content"],
                    nuke_version=nuke_version,
                    scraped_at=now,
                ))
                count += 1

        self.session.commit()
        return count, skipped

    def get_unindexed_pages(self) -> list[NukePage]:
        stmt = select(NukePage).where(NukePage.nuke_pages_indexed == False)
        return list(self.session.scalars(stmt))

    def mark_indexed(self, page_ids: list) -> None:
        # page_ids: list[UUID] — UUID objects, not strings
        now = datetime.now(timezone.utc)
        stmt = (
            update(NukePage)
            .where(NukePage.id.in_(page_ids))
            .values(nuke_pages_indexed=True, indexed_at=now)
        )
        self.session.execute(stmt)
        self.session.commit()
