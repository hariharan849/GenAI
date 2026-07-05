import logging
import re
from typing import List

from api.schemas.indexing.models import ChunkMetadata, TextChunk

logger = logging.getLogger(__name__)


class TextChunker:
    """Service for chunking text into overlapping segments.

    Uses word-based chunking with configurable chunk size and overlap.
    Default: 600 words per chunk with 100 word overlap.
    """

    def __init__(self, chunk_size: int = 600, overlap_size: int = 100, min_chunk_size: int = 100):
        """Initialize text chunker.

        :param chunk_size: Target number of words per chunk
        :param overlap_size: Number of overlapping words between chunks
        :param min_chunk_size: Minimum words for a chunk to be valid
        """
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        self.min_chunk_size = min_chunk_size

        if overlap_size >= chunk_size:
            raise ValueError("Overlap size must be less than chunk size")

        logger.info(
            f"Text chunker initialized: chunk_size={chunk_size}, overlap_size={overlap_size}, min_chunk_size={min_chunk_size}"
        )

    def _split_into_words(self, text: str) -> List[str]:
        """Split text into words while preserving whitespace information."""
        return re.findall(r"\S+", text)

    def _reconstruct_text(self, words: List[str]) -> str:
        """Reconstruct text from words."""
        return " ".join(words)

    def chunk_text(self, text: str, doc_id: str, page_id: str) -> List[TextChunk]:
        """Chunk text into overlapping segments.

        :param text: Full text to chunk
        :param doc_id: Document identifier (e.g. URL)
        :param page_id: Page/database identifier
        :returns: List of text chunks with metadata
        """
        if not text or not text.strip():
            logger.warning(f"Empty text provided for doc {doc_id}")
            return []

        words = self._split_into_words(text)

        if len(words) < self.min_chunk_size:
            logger.warning(f"Text for doc {doc_id} has only {len(words)} words, less than minimum {self.min_chunk_size}")
            if words:
                return [
                    TextChunk(
                        text=self._reconstruct_text(words),
                        metadata=ChunkMetadata(
                            chunk_index=0,
                            start_char=0,
                            end_char=len(text),
                            word_count=len(words),
                            overlap_with_previous=0,
                            overlap_with_next=0,
                        ),
                        doc_id=doc_id,
                        page_id=page_id,
                    )
                ]
            return []

        chunks = []
        chunk_index = 0
        current_position = 0

        while current_position < len(words):
            chunk_start = current_position
            chunk_end = min(current_position + self.chunk_size, len(words))

            chunk_words = words[chunk_start:chunk_end]
            chunk_text = self._reconstruct_text(chunk_words)

            start_char = len(" ".join(words[:chunk_start])) if chunk_start > 0 else 0
            end_char = len(" ".join(words[:chunk_end]))

            overlap_with_previous = min(self.overlap_size, chunk_start) if chunk_start > 0 else 0
            overlap_with_next = self.overlap_size if chunk_end < len(words) else 0

            chunk = TextChunk(
                text=chunk_text,
                metadata=ChunkMetadata(
                    chunk_index=chunk_index,
                    start_char=start_char,
                    end_char=end_char,
                    word_count=len(chunk_words),
                    overlap_with_previous=overlap_with_previous,
                    overlap_with_next=overlap_with_next,
                    section_title=None,
                ),
                doc_id=doc_id,
                page_id=page_id,
            )
            chunks.append(chunk)

            current_position += self.chunk_size - self.overlap_size
            chunk_index += 1

            if chunk_end >= len(words):
                break

        logger.info(f"Chunked doc {doc_id}: {len(words)} words -> {len(chunks)} chunks")
        return chunks

    def chunk_sections(
        self,
        sections: list[dict],
        doc_id: str,
        page_id: str,
    ) -> list[TextChunk]:
        """Chunk a list of sections, preserving section boundaries.

        Each section is chunked independently; chunk_index is global across all
        sections so OpenSearch doc IDs remain unique within a page.
        section_title is populated on every returned chunk.

        :param sections: List of {"title": str, "text": str} dicts
        :param doc_id: Document identifier (e.g. URL)
        :param page_id: Page/database identifier
        :returns: List of TextChunks with section_title set
        """
        chunks: list[TextChunk] = []
        global_chunk_index = 0
        for section in sections:
            section_chunks = self.chunk_text(section["text"], doc_id=doc_id, page_id=page_id)
            for chunk in section_chunks:
                new_meta = ChunkMetadata(
                    chunk_index=global_chunk_index,
                    start_char=chunk.metadata.start_char,
                    end_char=chunk.metadata.end_char,
                    word_count=chunk.metadata.word_count,
                    overlap_with_previous=chunk.metadata.overlap_with_previous,
                    overlap_with_next=chunk.metadata.overlap_with_next,
                    section_title=section["title"],
                )
                chunks.append(TextChunk(
                    text=chunk.text,
                    metadata=new_meta,
                    doc_id=chunk.doc_id,
                    page_id=chunk.page_id,
                ))
                global_chunk_index += 1
        return chunks
