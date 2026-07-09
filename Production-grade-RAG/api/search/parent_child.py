"""LangChain adapters for parent-child document retrieval."""

import asyncio
import hashlib
import threading
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Sequence

from langchain_classic.retrievers import ParentDocumentRetriever
from langchain_core.documents import Document
from langchain_core.stores import BaseStore
from langchain_core.vectorstores import VectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker

from api.config import Settings
from api.models.nuke_page import NukePage  # noqa: F401
from api.models.nuke_parent_document import NukeParentDocument, parse_optional_uuid
from api.search.protocol import SearchClient
from api.services.embeddings.jina_client import JinaEmbeddingsClient


def _word_count(text: str) -> int:
    return len(text.split())


def make_parent_doc_id(page_url: str, parent_index: int) -> str:
    return hashlib.sha256(f"{page_url}:parent:{parent_index}".encode()).hexdigest()


def make_child_chunk_id(parent_doc_id: str, child_index: int) -> str:
    return hashlib.sha256(f"{parent_doc_id}:child:{child_index}".encode()).hexdigest()


def make_recursive_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=_word_count,
        separators=["\n\n", "\n", ". ", " ", ""],
        keep_separator=False,
        add_start_index=True,
        strip_whitespace=True,
    )


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def _target() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(target=_target)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result["value"]


class PostgresParentDocumentStore(BaseStore[str, Document]):
    """Persistent LangChain docstore for parent Nuke documentation chunks."""

    def __init__(self, settings: Settings):
        self.engine = create_engine(
            settings.postgres_database_url,
            echo=settings.postgres_echo_sql,
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
            pool_pre_ping=True,
        )
        NukeParentDocument.__table__.create(bind=self.engine, checkfirst=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def mget(self, keys: Sequence[str]) -> list[Document | None]:
        if not keys:
            return []
        with self.session_factory() as session:
            rows = session.execute(
                select(NukeParentDocument).where(NukeParentDocument.parent_doc_id.in_(list(keys)))
            ).scalars()
            by_id = {
                row.parent_doc_id: Document(page_content=row.page_content, metadata=dict(row.doc_metadata or {}))
                for row in rows
            }
        return [by_id.get(key) for key in keys]

    def mset(self, key_value_pairs: Sequence[tuple[str, Document]]) -> None:
        if not key_value_pairs:
            return
        with self.session_factory() as session:
            for key, document in key_value_pairs:
                metadata = dict(document.metadata or {})
                metadata["parent_doc_id"] = key
                stmt = insert(NukeParentDocument).values(
                    parent_doc_id=key,
                    page_id=parse_optional_uuid(metadata.get("page_id")),
                    url=metadata.get("url", ""),
                    doc_metadata=metadata,
                    page_content=document.page_content,
                )
                session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["parent_doc_id"],
                        set_={
                            "page_id": stmt.excluded.page_id,
                            "url": stmt.excluded.url,
                            "doc_metadata": stmt.excluded.doc_metadata,
                            "page_content": stmt.excluded.page_content,
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )
                )
            session.commit()

    def mdelete(self, keys: Sequence[str]) -> None:
        if not keys:
            return
        with self.session_factory() as session:
            rows = session.execute(
                select(NukeParentDocument).where(NukeParentDocument.parent_doc_id.in_(list(keys)))
            ).scalars()
            for row in rows:
                session.delete(row)
            session.commit()

    def yield_keys(self, *, prefix: str | None = None) -> Iterator[str]:
        with self.session_factory() as session:
            query = select(NukeParentDocument.parent_doc_id).order_by(NukeParentDocument.parent_doc_id)
            if prefix:
                query = query.where(NukeParentDocument.parent_doc_id.like(f"{prefix}%"))
            for key in session.execute(query).scalars():
                yield key


class SearchClientVectorStore(VectorStore):
    """Small LangChain VectorStore over this repo's search client protocol."""

    def __init__(self, search_client: SearchClient, embeddings_client: JinaEmbeddingsClient, use_hybrid: bool = True):
        self.search_client = search_client
        self.embeddings_client = embeddings_client
        self.use_hybrid = use_hybrid

    def add_documents(self, documents: list[Document], **kwargs: Any) -> list[str]:
        ids = kwargs.get("ids") or [doc.id for doc in documents]
        ids = [
            doc_id or make_child_chunk_id(str(doc.metadata.get("parent_doc_id", "")), i)
            for i, (doc_id, doc) in enumerate(zip(ids, documents, strict=False))
        ]
        embeddings = _run_async(self.embeddings_client.embed_passages([doc.page_content for doc in documents]))
        chunks = []
        for i, (doc, doc_id, embedding) in enumerate(zip(documents, ids, embeddings, strict=False)):
            metadata = dict(doc.metadata or {})
            parent_doc_id = metadata.get("parent_doc_id")
            chunk_index = int(metadata.get("chunk_index", i))
            chunk_data = {
                "chunk_id": doc_id,
                "page_id": metadata.get("page_id"),
                "parent_doc_id": parent_doc_id,
                "nuke_node_name": metadata.get("nuke_node_name", ""),
                "section": metadata.get("section", ""),
                "section_name": metadata.get("section_name") or metadata.get("section_title") or "",
                "url": metadata.get("url", ""),
                "chunk_text": doc.page_content,
                "chunk_index": chunk_index,
            }
            chunks.append({"chunk_data": chunk_data, "embedding": list(embedding)})
        self.search_client.bulk_index_chunks(chunks)
        return list(ids)

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]:
        embedding = _run_async(self.embeddings_client.embed_query(query))
        results = self.search_client.search_unified(
            query=query,
            query_embedding=embedding,
            size=k,
            use_hybrid=kwargs.get("use_hybrid", self.use_hybrid),
        )
        return [self._hit_to_document(hit) for hit in results.get("hits", [])]

    def similarity_search_with_score(self, query: str, k: int = 4, **kwargs: Any) -> list[tuple[Document, float]]:
        docs = self.similarity_search(query, k=k, **kwargs)
        return [(doc, float(doc.metadata.get("score", 0.0))) for doc in docs]

    def delete(self, ids: list[str] | None = None, **kwargs: Any) -> bool | None:
        return None

    @classmethod
    def from_texts(
        cls,
        texts: list[str],
        embedding: Any,
        metadatas: list[dict] | None = None,
        *,
        ids: list[str] | None = None,
        **kwargs: Any,
    ):
        vectorstore = cls(
            search_client=kwargs["search_client"],
            embeddings_client=kwargs["embeddings_client"],
            use_hybrid=kwargs.get("use_hybrid", True),
        )
        vectorstore.add_texts(texts, metadatas=metadatas, ids=ids)
        return vectorstore

    @staticmethod
    def _hit_to_document(hit: dict[str, Any]) -> Document:
        return Document(
            page_content=hit.get("chunk_text", ""),
            metadata={
                "url": hit.get("url", ""),
                "page_id": hit.get("page_id", ""),
                "parent_doc_id": hit.get("parent_doc_id"),
                "nuke_node_name": hit.get("nuke_node_name", ""),
                "section": hit.get("section", ""),
                "section_name": hit.get("section_name", ""),
                "chunk_index": hit.get("chunk_index"),
                "score": hit.get("score", 0.0),
                "source": "hybrid",
            },
        )


def create_parent_document_retriever(
    *,
    settings: Settings,
    search_client: SearchClient,
    embeddings_client: JinaEmbeddingsClient,
    top_k: int,
    use_hybrid: bool = True,
) -> ParentDocumentRetriever:
    vectorstore = SearchClientVectorStore(search_client, embeddings_client, use_hybrid=use_hybrid)
    docstore = PostgresParentDocumentStore(settings)
    return ParentDocumentRetriever(
        vectorstore=vectorstore,
        docstore=docstore,
        child_splitter=make_recursive_splitter(settings.chunking.chunk_size, settings.chunking.overlap_size),
        parent_splitter=None,
        id_key=settings.chunking.parent_doc_id_key,
        search_kwargs={"k": top_k, "use_hybrid": use_hybrid},
    )


def split_parent_documents(document: Document, settings: Settings) -> list[Document]:
    splitter = make_recursive_splitter(settings.chunking.parent_chunk_size, settings.chunking.parent_overlap_size)
    return splitter.split_documents([document])
