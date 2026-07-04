"""PostgreSQL pg_embedding-backed search client."""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker

from api.config import Settings
from api.models.nuke_doc_chunk import NukeDocChunk
from api.models.nuke_page import NukePage  # noqa: F401

logger = logging.getLogger(__name__)


def deterministic_chunk_id(url: str, chunk_index: int) -> str:
    return hashlib.sha256(f"{url}:{chunk_index}".encode()).hexdigest()


class PostgresEmbeddingSearchClient:
    """Search client using PostgreSQL full-text search and pg_embedding HNSW."""

    backend_name = "postgres_embedding"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.table_name = NukeDocChunk.__tablename__
        self.vector_dimension = settings.search.vector_dimension
        self.candidate_multiplier = settings.search.hybrid_candidate_multiplier
        self.rrf_constant = settings.search.rrf_constant
        self.engine = create_engine(
            settings.postgres_database_url,
            echo=settings.postgres_echo_sql,
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
            pool_pre_ping=True,
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def health_check(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error("Postgres search health check failed: %s", e)
            return False

    def get_index_stats(self) -> Dict[str, Any]:
        try:
            with self.engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT
                            to_regclass('public.nuke_doc_chunks') IS NOT NULL AS table_exists,
                            EXISTS (
                                SELECT 1 FROM pg_extension WHERE extname = 'embedding'
                            ) AS extension_ready,
                            0 AS document_count
                        """
                    )
                ).mappings().one()
                document_count = 0
                if row["table_exists"]:
                    document_count = int(conn.execute(text("SELECT count(*) FROM nuke_doc_chunks")).scalar_one())
            return {
                "index_name": self.table_name,
                "exists": bool(row["table_exists"]),
                "extension_ready": bool(row["extension_ready"]),
                "schema_ready": bool(row["table_exists"]),
                "document_count": document_count,
            }
        except Exception as e:
            logger.error("Error getting Postgres search stats: %s", e)
            return {
                "index_name": self.table_name,
                "exists": False,
                "extension_ready": False,
                "schema_ready": False,
                "document_count": 0,
                "error": str(e),
            }

    def setup_indices(self, force: bool = False) -> Dict[str, bool]:
        del force
        results = {"extension": False, "schema": False, "full_text_index": False, "hnsw_index": False}
        with self.engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS embedding"))
            results["extension"] = True

            NukeDocChunk.__table__.create(bind=conn, checkfirst=True)
            results["schema"] = True

            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_nuke_doc_chunks_fts
                    ON nuke_doc_chunks
                    USING GIN (to_tsvector('english', chunk_text))
                    """
                )
            )
            results["full_text_index"] = True

            conn.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS ix_nuke_doc_chunks_embedding_hnsw
                    ON nuke_doc_chunks
                    USING hnsw (embedding ann_cos_ops)
                    WITH (dims = {self.vector_dimension})
                    """
                )
            )
            results["hnsw_index"] = True
        return results

    def search_unified(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        size: int = 10,
        from_: int = 0,
        categories: Optional[List[str]] = None,
        latest: bool = False,
        use_hybrid: bool = True,
        min_score: float = 0.0,
        knowledge_source: str = "nuke",
    ) -> Dict[str, Any]:
        del latest, knowledge_source
        try:
            if query_embedding and use_hybrid:
                return self._search_hybrid(query, query_embedding, size, from_, categories, min_score)
            if query_embedding and not query.strip():
                return self._search_vector(query_embedding, size, from_, categories, min_score)
            return self._search_keyword(query, size, from_, categories, min_score)
        except Exception as e:
            logger.error("Postgres unified search error: %s", e)
            return {"total": 0, "hits": []}

    def _search_keyword(
        self, query: str, size: int, from_: int, categories: Optional[List[str]], min_score: float
    ) -> Dict[str, Any]:
        sql = """
            WITH q AS (SELECT websearch_to_tsquery('english', :query) AS tsq)
            SELECT chunk_id, page_id, url, nuke_node_name, section, section_name,
                   chunk_index, chunk_text,
                   ts_rank_cd(to_tsvector('english', chunk_text), q.tsq) AS score,
                   ts_headline('english', chunk_text, q.tsq, 'MaxFragments=2, MinWords=5, MaxWords=20') AS headline
            FROM nuke_doc_chunks, q
            WHERE q.tsq @@ to_tsvector('english', chunk_text)
              AND (:categories IS NULL OR section = ANY(:categories))
            ORDER BY score DESC
            LIMIT :limit OFFSET :offset
        """
        rows = self._fetch(sql, {"query": query, "categories": categories, "limit": size, "offset": from_})
        hits = [self._row_to_hit(row) for row in rows if float(row["score"] or 0.0) >= min_score]
        return {"total": len(hits), "hits": hits}

    def _search_vector(
        self,
        query_embedding: List[float],
        size: int,
        from_: int,
        categories: Optional[List[str]],
        min_score: float,
    ) -> Dict[str, Any]:
        sql = """
            SELECT chunk_id, page_id, url, nuke_node_name, section, section_name,
                   chunk_index, chunk_text,
                   1.0 / (1.0 + (embedding <=> CAST(:embedding AS real[]))) AS score,
                   NULL AS headline
            FROM nuke_doc_chunks
            WHERE (:categories IS NULL OR section = ANY(:categories))
            ORDER BY embedding <=> CAST(:embedding AS real[])
            LIMIT :limit OFFSET :offset
        """
        rows = self._fetch(
            sql,
            {"embedding": query_embedding, "categories": categories, "limit": size, "offset": from_},
        )
        hits = [self._row_to_hit(row) for row in rows if float(row["score"] or 0.0) >= min_score]
        return {"total": len(hits), "hits": hits}

    def _search_hybrid(
        self,
        query: str,
        query_embedding: List[float],
        size: int,
        from_: int,
        categories: Optional[List[str]],
        min_score: float,
    ) -> Dict[str, Any]:
        candidate_size = max(size * self.candidate_multiplier, size)
        sql = """
            WITH
            q AS (SELECT websearch_to_tsquery('english', :query) AS tsq),
            keyword AS (
                SELECT chunk_id, row_number() OVER (ORDER BY ts_rank_cd(to_tsvector('english', chunk_text), q.tsq) DESC) AS rank
                FROM nuke_doc_chunks, q
                WHERE q.tsq @@ to_tsvector('english', chunk_text)
                  AND (:categories IS NULL OR section = ANY(:categories))
                ORDER BY ts_rank_cd(to_tsvector('english', chunk_text), q.tsq) DESC
                LIMIT :candidate_size
            ),
            vector AS (
                SELECT chunk_id, row_number() OVER (ORDER BY embedding <=> CAST(:embedding AS real[])) AS rank
                FROM nuke_doc_chunks
                WHERE (:categories IS NULL OR section = ANY(:categories))
                ORDER BY embedding <=> CAST(:embedding AS real[])
                LIMIT :candidate_size
            ),
            fused AS (
                SELECT chunk_id, SUM(score) AS score
                FROM (
                    SELECT chunk_id, 1.0 / (:rrf_constant + rank) AS score FROM keyword
                    UNION ALL
                    SELECT chunk_id, 1.0 / (:rrf_constant + rank) AS score FROM vector
                ) ranked
                GROUP BY chunk_id
            )
            SELECT c.chunk_id, c.page_id, c.url, c.nuke_node_name, c.section, c.section_name,
                   c.chunk_index, c.chunk_text, f.score, NULL AS headline
            FROM fused f
            JOIN nuke_doc_chunks c ON c.chunk_id = f.chunk_id
            WHERE f.score >= :min_score
            ORDER BY f.score DESC
            LIMIT :limit OFFSET :offset
        """
        rows = self._fetch(
            sql,
            {
                "query": query,
                "embedding": query_embedding,
                "categories": categories,
                "candidate_size": candidate_size,
                "rrf_constant": self.rrf_constant,
                "min_score": min_score,
                "limit": size,
                "offset": from_,
            },
        )
        hits = [self._row_to_hit(row) for row in rows]
        return {"total": len(hits), "hits": hits}

    def bulk_index_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, int]:
        if not chunks:
            return {"success": 0, "failed": 0}

        success = 0
        failed = 0
        failed_page_ids: set[str] = set()
        with self.session_factory() as session:
            for chunk in chunks:
                try:
                    payload = self._normalize_chunk(chunk)
                    stmt = insert(NukeDocChunk).values(**payload)
                    update_values = {
                        "page_id": stmt.excluded.page_id,
                        "url": stmt.excluded.url,
                        "nuke_node_name": stmt.excluded.nuke_node_name,
                        "section": stmt.excluded.section,
                        "section_name": stmt.excluded.section_name,
                        "chunk_index": stmt.excluded.chunk_index,
                        "chunk_text": stmt.excluded.chunk_text,
                        "embedding": stmt.excluded.embedding,
                        "updated_at": datetime.now(timezone.utc),
                    }
                    session.execute(stmt.on_conflict_do_update(index_elements=["chunk_id"], set_=update_values))
                    session.commit()
                    success += 1
                except Exception as e:
                    session.rollback()
                    failed += 1
                    raw_page_id = chunk.get("page_id") or chunk.get("chunk_data", {}).get("page_id")
                    if raw_page_id:
                        failed_page_ids.add(str(raw_page_id))
                    logger.warning("Failed to upsert chunk into Postgres search table: %s", e)
        return {"success": success, "failed": failed, "failed_page_ids": sorted(failed_page_ids)}

    def _fetch(self, sql: str, params: Dict[str, Any]) -> list[dict]:
        with self.engine.connect() as conn:
            return list(conn.execute(text(sql), params).mappings())

    def _normalize_chunk(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        chunk_data = chunk.get("chunk_data", chunk).copy()
        embedding = chunk.get("embedding", chunk_data.pop("embedding", None))
        if embedding is None:
            raise ValueError("chunk embedding is required")

        url = chunk_data["url"]
        chunk_index = int(chunk_data["chunk_index"])
        page_id = chunk_data.get("page_id") or chunk_data.get("id")
        if page_id is None:
            raise ValueError("page_id is required")
        if not isinstance(page_id, uuid.UUID):
            page_id = uuid.UUID(str(page_id))

        return {
            "chunk_id": chunk_data.get("chunk_id") or chunk_data.get("_id") or deterministic_chunk_id(url, chunk_index),
            "page_id": page_id,
            "url": url,
            "nuke_node_name": chunk_data.get("nuke_node_name") or chunk_data.get("node_name") or "",
            "section": chunk_data.get("section") or "",
            "section_name": chunk_data.get("section_name") or chunk_data.get("section_title") or "",
            "chunk_index": chunk_index,
            "chunk_text": chunk_data["chunk_text"],
            "embedding": list(embedding),
        }

    def _row_to_hit(self, row: Dict[str, Any]) -> Dict[str, Any]:
        hit = {
            "score": float(row["score"] or 0.0),
            "chunk_id": row["chunk_id"],
            "page_id": str(row["page_id"]),
            "url": row["url"],
            "nuke_node_name": row["nuke_node_name"],
            "section": row["section"],
            "section_name": row["section_name"],
            "chunk_index": row["chunk_index"],
            "chunk_text": row["chunk_text"],
        }
        if row.get("headline"):
            hit["highlights"] = {"chunk_text": [row["headline"]]}
        return hit
