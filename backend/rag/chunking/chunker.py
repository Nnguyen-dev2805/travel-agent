"""Text Chunker module implementing Recursive Character Splitting with Metadata Preservation."""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List

logger = logging.getLogger("travel_agent_chunker")


@dataclass
class TextChunk:
    """Represents a text chunk extracted from a document."""

    chunk_id: str
    document_id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class DocumentChunker:
    """Recursive Character Text Splitter preserving sentence boundaries and metadata."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
        separators: List[str] = None,
    ) -> None:
        """Initialize chunker with size and overlap bounds.

        Args:
            chunk_size: Maximum character length per chunk.
            chunk_overlap: Number of overlapping characters between consecutive chunks.
            separators: Priority list of separators for splitting.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " "]

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        """Recursively split text using separators."""
        final_chunks: List[str] = []
        separator = separators[-1]
        new_separators = []

        for i, s in enumerate(separators):
            if s == "":
                separator = ""
                break
            if s in text:
                separator = s
                new_separators = separators[i + 1 :]
                break

        splits = text.split(separator) if separator else list(text)

        good_splits: List[str] = []
        for s in splits:
            if len(s) < self.chunk_size:
                good_splits.append(s)
            else:
                if good_splits:
                    merged = self._merge_splits(good_splits, separator)
                    final_chunks.extend(merged)
                    good_splits = []
                if new_separators:
                    other_chunks = self._split_text(s, new_separators)
                    final_chunks.extend(other_chunks)
                else:
                    final_chunks.append(s)

        if good_splits:
            merged = self._merge_splits(good_splits, separator)
            final_chunks.extend(merged)

        return final_chunks

    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        """Combine smaller text splits into chunks up to chunk_size with overlap."""
        docs: List[str] = []
        current_doc: List[str] = []
        total = 0

        for d in splits:
            len_d = len(d)
            sep_len = len(separator) if current_doc else 0
            if total + len_d + sep_len > self.chunk_size:
                if total > 0:
                    doc = separator.join(current_doc).strip()
                    if doc:
                        docs.append(doc)

                    # Build overlap from trailing splits
                    while total > self.chunk_overlap or (
                        total + len_d + sep_len > self.chunk_size and total > 0
                    ):
                        removed = current_doc.pop(0)
                        total -= len(removed) + (len(separator) if current_doc else 0)

            current_doc.append(d)
            total += len_d + (len(separator) if len(current_doc) > 1 else 0)

        if current_doc:
            doc = separator.join(current_doc).strip()
            if doc:
                docs.append(doc)

        return docs

    def chunk_document(self, document: Dict[str, Any]) -> List[TextChunk]:
        """Split a single document into TextChunk objects.

        Args:
            document: Dictionary containing document_id, text, title, url, etc.

        Returns:
            List of TextChunk instances.
        """
        doc_id = str(document.get("document_id", "unknown"))
        text = document.get("text", "").strip()

        if not text:
            return []

        raw_chunks = self._split_text(text, self.separators)
        chunks: List[TextChunk] = []

        for idx, chunk_text in enumerate(raw_chunks):
            cleaned_text = chunk_text.strip()
            if not cleaned_text:
                continue

            chunk_id = f"{doc_id}_chunk_{idx}"
            metadata = {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "chunk_index": idx,
                "title": document.get("title", ""),
                "url": document.get("url", ""),
                "language": document.get("language", "en"),
                "source_domain": document.get("source_domain", "vietnam.travel"),
                "char_length": len(cleaned_text),
            }

            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    text=cleaned_text,
                    metadata=metadata,
                )
            )

        return chunks

    def chunk_documents(self, documents: List[Dict[str, Any]]) -> List[TextChunk]:
        """Process a list of documents into TextChunks."""
        all_chunks: List[TextChunk] = []
        for doc in documents:
            doc_chunks = self.chunk_document(doc)
            all_chunks.extend(doc_chunks)

        logger.info(
            f"Chunked {len(documents)} documents into {len(all_chunks)} total text chunks."
        )
        return all_chunks
