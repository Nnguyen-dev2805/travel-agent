"""Parent-Child Semantic Chunker module implementing Dual Text Fields (source_text vs retrieval_text)."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("parent_child_chunker")

WORD_RE = re.compile(r"\S+", re.UNICODE)
PARAGRAPH_RE = re.compile(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", re.DOTALL)
SENTENCE_RE = re.compile(r"[^.!?。！？]+(?:[.!?。！？]+|$)", re.UNICODE)
SITE_SUFFIX_RE = re.compile(r"\s*\|\s*Vietnam Tourism\s*$", re.I)

NOISE_PATTERNS = [
    r"click the image",
    r"360-degree",
    r"360 degree",
    r"photo by",
    r"photos? courtesy",
    r"all photos by",
    r"image courtesy",
    r"credit",
    r"read more",
    r"learn more",
    r"for more information",
    r"visit:",
    r"book now",
    r"share this",
    r"subscribe",
    r"follow us",
    r"copyright",
]
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.I)
SENTENCE_END_RE = re.compile(r"[.!?]")


@dataclass
class ParentChunk:
    """Represents a document-level Parent record with extractive lead summary."""

    parent_id: str
    document_id: str
    title: str
    clean_title: str
    context_summary: str
    content: str
    child_ids: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChildChunk:
    """Represents a section-level Child chunk with dual source and retrieval text."""

    child_id: str
    parent_id: str
    document_id: str
    heading: str
    heading_path: List[str]
    source_text: str
    retrieval_text: str
    word_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class ParentChildChunker:
    """Document-Parent Heading-Aware Paragraph/Sentence Semantic Chunker."""

    def __init__(
        self,
        summary_max_words: int = 120,
        target_child_words: int = 220,
        max_child_words: int = 360,
        min_child_words: int = 40,
    ) -> None:
        self.summary_max_words = summary_max_words
        self.target_child_words = target_child_words
        self.max_child_words = max_child_words
        self.min_child_words = min_child_words

    @staticmethod
    def normalize_space(value: Any) -> str:
        """Collapse repeated whitespace."""
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def clean_display_title(title: str) -> str:
        """Remove website suffix from display title."""
        return SITE_SUFFIX_RE.sub("", ParentChildChunker.normalize_space(title)).strip()

    @staticmethod
    def count_words(text: str) -> int:
        """Count whitespace-separated words."""
        return len(WORD_RE.findall(text or ""))

    @staticmethod
    def truncate_words(text: str, max_words: int) -> str:
        """Truncate text to max_words."""
        words = WORD_RE.findall(text or "")
        if len(words) <= max_words:
            return ParentChildChunker.normalize_space(text)
        return " ".join(words[:max_words]).strip()

    @staticmethod
    def is_noise_text(value: str) -> bool:
        """Check if text contains CTA or caption noise."""
        return bool(NOISE_RE.search(ParentChildChunker.normalize_space(value)))

    def clean_heading_path(self, heading_path: List[str]) -> Tuple[List[str], List[str]]:
        """Remove CTA noise nodes from heading path."""
        cleaned, removed = [], []
        for node in heading_path or []:
            text = self.normalize_space(node)
            if not text:
                continue
            if self.is_noise_text(text):
                removed.append(text)
                continue
            cleaned.append(node)
        return cleaned, removed

    def is_paragraph_like_heading(self, heading: str) -> bool:
        """Detect headings that look like prose paragraphs."""
        text = self.normalize_space(heading)
        words = self.count_words(text)
        sentence_marks = len(SENTENCE_END_RE.findall(text))
        return (
            words >= 18
            or len(text) >= 150
            or sentence_marks >= 2
            or (sentence_marks >= 1 and words >= 14)
        )

    def extract_sections_from_raw_text(self, document_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract structured sections from raw document text if not present."""
        if document_dict.get("sections"):
            return document_dict["sections"]

        text = document_dict.get("text") or ""
        doc_title = self.clean_display_title(document_dict.get("title") or "")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        if not paragraphs:
            return [{
                "section_index": 0,
                "heading": doc_title,
                "heading_path": [doc_title],
                "text": text,
            }]

        sections: List[Dict[str, Any]] = []
        current_heading = doc_title
        current_paras: List[str] = []
        section_idx = 0

        for para in paragraphs:
            lines = para.split("\n")
            first_line = lines[0].strip()
            # If line is short and looks like a heading
            if len(first_line) < 80 and not first_line.endswith((".", ":", "?", "!")) and len(lines) == 1:
                if current_paras:
                    sections.append({
                        "section_index": section_idx,
                        "heading": current_heading,
                        "heading_path": [doc_title, current_heading] if current_heading != doc_title else [doc_title],
                        "text": "\n\n".join(current_paras),
                    })
                    section_idx += 1
                    current_paras = []
                current_heading = first_line
            else:
                current_paras.append(para)

        if current_paras:
            sections.append({
                "section_index": section_idx,
                "heading": current_heading,
                "heading_path": [doc_title, current_heading] if current_heading != doc_title else [doc_title],
                "text": "\n\n".join(current_paras),
            })

        return sections

    def _split_into_units(self, text: str) -> List[str]:
        """Split text into paragraph and sentence units."""
        units: List[str] = []
        for match in PARAGRAPH_RE.finditer(text or ""):
            para = match.group(0).strip()
            if not para:
                continue
            if self.count_words(para) <= self.max_child_words:
                units.append(para)
            else:
                for s_match in SENTENCE_RE.finditer(para):
                    sentence = s_match.group(0).strip()
                    if sentence:
                        units.append(sentence)
        return units or [text.strip()]

    def pack_units(self, units: List[str]) -> List[str]:
        """Pack units into cohesive child chunks."""
        packed: List[str] = []
        current_units: List[str] = []
        current_words = 0

        for unit in units:
            unit_words = self.count_words(unit)
            if current_units and (current_words + unit_words > self.max_child_words or (current_words >= self.target_child_words and current_words + unit_words > self.target_child_words)):
                packed.append("\n\n".join(current_units))
                current_units = []
                current_words = 0
            current_units.append(unit)
            current_words += unit_words

        if current_units:
            if packed and current_words < self.min_child_words:
                packed[-1] += "\n\n" + "\n\n".join(current_units)
            else:
                packed.append("\n\n".join(current_units))

        return packed

    def build_retrieval_text(self, title: str, heading: str, heading_path: List[str], url: str, lang: str, source_text: str) -> str:
        """Build derived retrieval text augmented with title, section, and heading path."""
        lines = [
            f"Article: {title}",
            f"Section: {heading}",
        ]
        if heading_path:
            lines.append(f"Heading path: {' > '.join(heading_path)}")
        if url:
            lines.append(f"Source: {url}")
        if lang:
            lines.append(f"Language: {lang}")
        lines.extend(["", source_text])
        return "\n".join(lines).strip()

    def chunk_document(self, document_dict: Dict[str, Any]) -> Tuple[ParentChunk, List[ChildChunk]]:
        """Chunk a document into a Parent record and List of Child chunks."""
        doc_id = str(document_dict.get("document_id") or document_dict.get("id") or "doc_unknown")
        raw_title = document_dict.get("title") or ""
        clean_title = self.clean_display_title(raw_title)
        url = document_dict.get("url") or ""
        lang = document_dict.get("language") or "en"
        parent_id = f"{doc_id}:parent:document"

        sections = self.extract_sections_from_raw_text(document_dict)

        # Build Lead Summary for Parent
        first_text = ""
        for sec in sections:
            txt = sec.get("text", "").strip()
            if txt:
                first_text = txt
                break
        context_summary = self.truncate_words(first_text, self.summary_max_words)
        full_content = "\n\n".join([sec.get("text", "").strip() for sec in sections if sec.get("text", "").strip()])

        children: List[ChildChunk] = []
        child_ids: List[str] = []

        for sec_idx, section in enumerate(sections):
            heading = section.get("heading") or clean_title
            raw_path = section.get("heading_path") or [heading]
            if isinstance(raw_path, str):
                raw_path = [raw_path]
            clean_path, _ = self.clean_heading_path(raw_path)

            text = section.get("text", "").strip()
            if not text:
                continue

            units = self._split_into_units(text)
            packed_texts = self.pack_units(units)

            for chunk_idx, source_text in enumerate(packed_texts):
                if not source_text.strip():
                    continue
                child_id = f"{doc_id}:child:{sec_idx:04d}:{chunk_idx:02d}"
                retrieval_text = self.build_retrieval_text(clean_title, heading, clean_path, url, lang, source_text)
                
                child = ChildChunk(
                    child_id=child_id,
                    parent_id=parent_id,
                    document_id=doc_id,
                    heading=heading,
                    heading_path=clean_path,
                    source_text=source_text,
                    retrieval_text=retrieval_text,
                    word_count=self.count_words(source_text),
                    metadata={
                        "url": url,
                        "title": clean_title,
                        "language": lang,
                        "section_index": sec_idx,
                        "chunk_index": chunk_idx,
                    },
                )
                children.append(child)
                child_ids.append(child_id)

        parent = ParentChunk(
            parent_id=parent_id,
            document_id=doc_id,
            title=raw_title,
            clean_title=clean_title,
            context_summary=context_summary,
            content=full_content,
            child_ids=child_ids,
            metadata={
                "url": url,
                "language": lang,
                "total_children": len(children),
            },
        )

        return parent, children
