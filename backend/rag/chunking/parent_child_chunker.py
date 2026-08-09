"""Parent-Child Semantic Chunker module implementing Dual Text Fields (source_text vs retrieval_text)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    from tools.enrich_chunk_metadata import enrich_child, enrich_parent
    HAS_METADATA_ENRICHER = True
except ImportError:
    HAS_METADATA_ENRICHER = False

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
    record_type: str
    title: str
    clean_title: str
    url: str
    language: str
    source_domain: str
    context_summary: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    child_ids: List[str] = field(default_factory=list)


@dataclass
class ChildChunk:
    """Represents a section-level Child chunk with dual source and retrieval text."""

    child_id: str
    parent_id: str
    document_id: str
    record_type: str
    heading: str
    heading_level: int
    heading_path: List[str]
    source_text: str
    retrieval_text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        """Backward-compatible access to metadata word count."""
        return int(self.metadata.get("word_count") or 0)

    @property
    def char_length(self) -> int:
        """Backward-compatible access to metadata character length."""
        return int(self.metadata.get("char_length") or 0)


class ParentChildChunker:
    """Document-Parent Heading-Aware Paragraph/Sentence Semantic Chunker."""

    def __init__(
        self,
        summary_max_words: int = 120,
        target_child_words: int = 220,
        max_child_words: int = 360,
        min_child_words: int = 40,
        enrich_metadata: bool = True,
    ) -> None:
        self.summary_max_words = summary_max_words
        self.target_child_words = target_child_words
        self.max_child_words = max_child_words
        self.min_child_words = min_child_words
        self.enrich_metadata = enrich_metadata

    @staticmethod
    def normalize_space(value: Any) -> str:
        """Collapse repeated whitespace."""
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def clean_display_title(title: str) -> str:
        """Remove website suffix from display title."""
        return SITE_SUFFIX_RE.sub("", ParentChildChunker.normalize_space(title)).strip()

    @staticmethod
    def infer_source_domain(url: str, fallback: str = "vietnam.travel") -> str:
        """Infer source domain from URL when not provided by preprocessing."""
        parsed = urlparse(str(url or ""))
        return parsed.netloc or fallback

    @staticmethod
    def ensure_list(value: Any) -> List[Any]:
        """Coerce scalar metadata values into a list."""
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return [value]

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
        """Remove CTA noise and paragraph-like nodes from heading path."""
        cleaned, removed = [], []
        for node in heading_path or []:
            text = self.normalize_space(node)
            if not text:
                continue
            if self.is_noise_text(text) or self.is_paragraph_like_heading(text):
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
        doc_title = self.clean_display_title(
            document_dict.get("clean_title")
            or document_dict.get("title")
            or document_dict.get("raw_title")
            or ""
        )
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        if not paragraphs:
            return [{
                "section_index": 0,
                "heading": doc_title,
                "heading_level": 1,
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
                        "heading_level": 2 if current_heading != doc_title else 1,
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
                "heading_level": 2 if current_heading != doc_title else 1,
                "heading_path": [doc_title, current_heading] if current_heading != doc_title else [doc_title],
                "text": "\n\n".join(current_paras),
            })

        return sections

    def extract_section_text(self, section: Dict[str, Any]) -> str:
        """Read section text from semantic cleaner `text` or html cleaner `blocks`."""
        parts: List[str] = []
        text = self.normalize_space(section.get("text") or "")
        if text and not self.is_noise_text(text):
            parts.append(text)

        blocks = section.get("blocks") or []
        if isinstance(blocks, list):
            ordered_blocks = sorted(
                [block for block in blocks if isinstance(block, dict)],
                key=lambda block: int(block.get("order") or 0),
            )
            for block in ordered_blocks:
                block_text = self.normalize_space(block.get("text") or "")
                if not block_text:
                    continue
                if self.is_noise_text(block_text) and self.count_words(block_text) <= 12:
                    continue
                if block_text not in parts:
                    parts.append(block_text)

        return "\n\n".join(parts).strip()

    def infer_categories(self, document_dict: Dict[str, Any]) -> List[str]:
        """Infer broad content categories from document metadata and URL."""
        explicit = (
            document_dict.get("categories")
            or document_dict.get("category")
            or document_dict.get("metadata", {}).get("categories")
            or document_dict.get("metadata", {}).get("category")
        )
        categories = [str(item) for item in self.ensure_list(explicit) if str(item).strip()]
        if categories:
            return categories

        url = str(document_dict.get("url") or "").lower()
        if "things-to-do" in url:
            return ["experience"]
        if "places-to-go" in url:
            return ["destination"]
        if "plan-your-trip" in url:
            return ["itinerary"]
        if "2025.vietnam.travel" in url:
            return ["news"]
        return []

    def build_document_metadata(
        self,
        document_dict: Dict[str, Any],
        source_domain: str,
    ) -> Dict[str, Any]:
        """Build normalized document metadata shared by parent and child chunks."""
        metadata = document_dict.get("metadata") or {}
        locations = self.ensure_list(document_dict.get("locations") or metadata.get("locations"))
        primary_location = (
            document_dict.get("primary_location")
            or metadata.get("primary_location")
            or (locations[0] if locations else "")
        )
        return {
            "primary_location": str(primary_location or ""),
            "locations": [str(item) for item in locations if str(item).strip()],
            "region": str(document_dict.get("region") or metadata.get("region") or ""),
            "categories": self.infer_categories(document_dict),
            "entity_type": [
                str(item)
                for item in self.ensure_list(document_dict.get("entity_type") or metadata.get("entity_type"))
                if str(item).strip()
            ],
            "article_type": str(document_dict.get("article_type") or metadata.get("article_type") or "travel_guide"),
            "source_domain": source_domain,
        }

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

    def build_retrieval_text(
        self,
        title: str,
        heading: str,
        heading_path: List[str],
        lang: str,
        source_text: str,
        primary_location: str = "",
        categories: Optional[List[str]] = None,
    ) -> str:
        """Build derived retrieval text augmented with title, section, and heading path."""
        lines = [
            f"Article: {title}",
            f"Section: {heading}",
        ]
        if heading_path:
            lines.append(f"Heading path: {' > '.join(heading_path)}")
        if primary_location:
            lines.append(f"Location: {primary_location}")
        if categories:
            lines.append(f"Category: {', '.join(categories)}")
        if lang:
            lines.append(f"Language: {lang}")
        lines.extend(["", source_text])
        return "\n".join(lines).strip()

    def enrich_parent_child_chunks(
        self,
        parent: ParentChunk,
        children: List[ChildChunk],
    ) -> Tuple[ParentChunk, List[ChildChunk]]:
        """Enrich parent/child metadata using gazetteer and taxonomy rules."""
        if not self.enrich_metadata or not HAS_METADATA_ENRICHER:
            if self.enrich_metadata and not HAS_METADATA_ENRICHER:
                logger.warning("Metadata enricher is unavailable; returning base chunk metadata.")
            return parent, children

        parent_dict = asdict(parent)
        child_dicts = [asdict(child) for child in children]
        enriched_children_dicts = [enrich_child(child, parent_dict) for child in child_dicts]
        enriched_parent_dict = enrich_parent(parent_dict, enriched_children_dicts)

        enriched_parent = ParentChunk(**enriched_parent_dict)
        enriched_children = [ChildChunk(**child) for child in enriched_children_dicts]
        return enriched_parent, enriched_children

    def chunk_document(self, document_dict: Dict[str, Any]) -> Tuple[ParentChunk, List[ChildChunk]]:
        """Chunk a document into a Parent record and List of Child chunks."""
        doc_id = str(document_dict.get("document_id") or document_dict.get("id") or "doc_unknown")
        raw_title = document_dict.get("raw_title") or document_dict.get("title") or document_dict.get("clean_title") or ""
        clean_title = document_dict.get("clean_title") or self.clean_display_title(raw_title)
        url = document_dict.get("url") or ""
        lang = document_dict.get("language") or "en"
        source_domain = document_dict.get("source_domain") or self.infer_source_domain(url)
        parent_id = f"{doc_id}:parent:document"
        shared_metadata = self.build_document_metadata(document_dict, source_domain)

        sections = self.extract_sections_from_raw_text(document_dict)

        # Build Lead Summary for Parent
        first_text = self.normalize_space(document_dict.get("meta_description") or "")
        for sec in sections:
            if first_text:
                break
            txt = self.normalize_space(sec.get("demoted_summary_text") or "")
            if not txt:
                txt = self.extract_section_text(sec)
            if txt:
                first_text = txt
                break
        if not first_text:
            first_text = document_dict.get("clean_text") or document_dict.get("plain_text") or document_dict.get("text") or ""
        context_summary = self.truncate_words(first_text, self.summary_max_words)

        children: List[ChildChunk] = []
        child_ids: List[str] = []

        for sec_idx, section in enumerate(sections):
            heading = section.get("heading") or clean_title
            heading = self.normalize_space(heading)
            heading_level = int(section.get("heading_level") or 1)
            raw_path = section.get("heading_path") or [heading]
            if isinstance(raw_path, str):
                raw_path = [raw_path]
            clean_path, _ = self.clean_heading_path(raw_path)
            if heading and heading not in clean_path and not self.is_paragraph_like_heading(heading):
                clean_path.append(heading)

            text = self.extract_section_text(section)
            if not text:
                continue

            units = self._split_into_units(text)
            packed_texts = self.pack_units(units)

            for chunk_idx, source_text in enumerate(packed_texts):
                if not source_text.strip():
                    continue
                child_id = f"{doc_id}:child:{sec_idx:04d}:{chunk_idx:02d}"
                categories = shared_metadata["categories"]
                retrieval_text = self.build_retrieval_text(
                    clean_title,
                    heading,
                    clean_path,
                    lang,
                    source_text,
                    primary_location=shared_metadata["primary_location"],
                    categories=categories,
                )
                
                child = ChildChunk(
                    child_id=child_id,
                    parent_id=parent_id,
                    document_id=doc_id,
                    record_type="child",
                    heading=heading,
                    heading_level=heading_level,
                    heading_path=clean_path,
                    source_text=source_text,
                    retrieval_text=retrieval_text,
                    metadata={
                        "title": clean_title,
                        "url": url,
                        "language": lang,
                        "source_domain": source_domain,
                        "primary_location": shared_metadata["primary_location"],
                        "region": shared_metadata["region"],
                        "category": categories,
                        "topic": self.normalize_space(heading).lower(),
                        "entity_type": shared_metadata["entity_type"],
                        "content_type": shared_metadata["article_type"],
                        "section_index": sec_idx,
                        "chunk_index": chunk_idx,
                        "word_count": self.count_words(source_text),
                        "char_length": len(source_text),
                        "chunker_version": "parent_child_v1",
                    },
                )
                children.append(child)
                child_ids.append(child_id)

        parent = ParentChunk(
            parent_id=parent_id,
            document_id=doc_id,
            record_type="parent",
            title=raw_title,
            clean_title=clean_title,
            url=url,
            language=lang,
            source_domain=source_domain,
            context_summary=context_summary,
            metadata={
                "primary_location": shared_metadata["primary_location"],
                "locations": shared_metadata["locations"],
                "region": shared_metadata["region"],
                "categories": shared_metadata["categories"],
                "article_type": shared_metadata["article_type"],
                "total_children": len(children),
                "chunker_version": "parent_child_v1",
            },
            child_ids=child_ids,
        )

        return self.enrich_parent_child_chunks(parent, children)
