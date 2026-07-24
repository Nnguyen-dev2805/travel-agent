"""Build Document Parent + Child chunks from cleaned travel/news documents.

Design implemented here:

- Parent is always the article/document.
- Parent `context_summary` is taken from the first paragraph text before the
  next heading. In `document_clean.json`, that is normally `sections[0].text`.
- Children are the paragraphs that belong to the heading above them.
- If a section is too long, it is split into smaller chunks by paragraph first,
  then by sentence when a single paragraph is still too long.
- If a document is short or unstructured, Parent is still the article and
  children are semantic chunks from the available article text.

Outputs:

- `data/chunks/semantic_parents.jsonl`
- `data/chunks/semantic_children.jsonl`
- `hybrid_chunk_report/parent_child_chunk_report.md`
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WORD_RE = re.compile(r"\S+", re.UNICODE)
PARAGRAPH_RE = re.compile(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", re.DOTALL)
SENTENCE_RE = re.compile(r"[^.!?。！？]+(?:[.!?。！？]+|$)", re.UNICODE)
SITE_SUFFIX_RE = re.compile(r"\s*\|\s*Vietnam Tourism\s*$", re.I)


def configure_console_encoding() -> None:
    """Make CLI output readable on Windows terminals."""

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class ChunkConfig:
    """Runtime config for the document-parent semantic chunker."""

    input_path: Path
    parent_output_path: Path
    child_output_path: Path
    report_path: Path
    summary_max_words: int = 120 # parent summary
    target_child_words: int = 220 # 
    max_child_words: int = 360
    min_child_words: int = 40


def normalize_space(value: Any) -> str:
    """Collapse whitespace for comparisons and compact metadata text."""

    return re.sub(r"\s+", " ", str(value or "")).strip()

# bỏ đi suffix website
def clean_display_title(title: str) -> str:
    """Remove site suffix from a title while preserving the original elsewhere."""

    return SITE_SUFFIX_RE.sub("", normalize_space(title)).strip()


def count_words(text: str) -> int:
    """Count whitespace-separated words."""

    return len(WORD_RE.findall(text or ""))

# cắt số từ trong số từ tối đa
def truncate_words(text: str, max_words: int) -> str:
    """Return a word-limited text preview without inventing new content."""

    words = WORD_RE.findall(text or "")
    if len(words) <= max_words:
        return normalize_space(text)
    return " ".join(words[:max_words]).strip()


def load_clean_documents(path: Path) -> list[dict[str, Any]]:
    """Load `document_clean.json`, which is a UTF-8 JSON array."""

    return json.loads(path.read_text(encoding="utf-8-sig"))

# tách text thành paragraph đồng thời lưu lại vị trí gốc của từng paragrahp
def paragraph_spans(text: str) -> list[dict[str, Any]]:
    """Split text into paragraph spans with exact char offsets.

    Each returned item has `text`, `char_start`, and `char_end`. The span text
    is trimmed, and the offsets point to the trimmed paragraph inside the
    original section text.
    """

    spans: list[dict[str, Any]] = []
    for match in PARAGRAPH_RE.finditer(text or ""):
        raw = match.group(0)
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        paragraph = raw.strip()
        if not paragraph:
            continue
        spans.append(
            {
                "text": paragraph,
                "char_start": match.start() + leading,
                "char_end": match.start() + trailing,
            }
        )
    return spans


def sentence_spans(paragraph: dict[str, Any]) -> list[dict[str, Any]]:
    """Split one long paragraph span into sentence spans.

    Offsets remain relative to the original section text by adding the paragraph
    start offset to each sentence boundary.
    """

    spans: list[dict[str, Any]] = []
    text = paragraph["text"]
    base = paragraph["char_start"]
    for match in SENTENCE_RE.finditer(text):
        sentence = match.group(0).strip()
        if not sentence:
            continue
        leading = len(match.group(0)) - len(match.group(0).lstrip())
        trailing = len(match.group(0).rstrip())
        spans.append(
            {
                "text": sentence,
                "char_start": base + match.start() + leading,
                "char_end": base + match.start() + trailing,
            }
        )
    return spans or [paragraph]


def split_long_span(span: dict[str, Any], max_words: int) -> list[dict[str, Any]]:
    """Split a long paragraph by sentence, then by words if needed.

    Word-level fallback is only used when one sentence is still larger than the
    maximum child size. In that fallback, exact char offsets are not guaranteed,
    so the span is marked with `span_mode = "word_fallback"`.
    """

    if count_words(span["text"]) <= max_words:
        return [span]

    output: list[dict[str, Any]] = []
    for sentence in sentence_spans(span):
        if count_words(sentence["text"]) <= max_words:
            output.append(sentence)
            continue

        words = WORD_RE.findall(sentence["text"])
        for index in range(0, len(words), max_words):
            part_words = words[index : index + max_words]
            output.append(
                {
                    "text": " ".join(part_words),
                    "char_start": sentence["char_start"],
                    "char_end": sentence["char_end"],
                    "span_mode": "word_fallback",
                }
            )
    return output

# Taoj các đơn vi unit: Paragraph hoặc sentence
def section_units(section: dict[str, Any], max_words: int) -> list[dict[str, Any]]:
    """Create paragraph/sentence units from one section text."""

    units: list[dict[str, Any]] = []
    for paragraph in paragraph_spans(section.get("text") or ""):
        units.extend(split_long_span(paragraph, max_words=max_words))
    return units

# Gom các đơn vị nhỏ thành child chunk có kích thước hợp lý
def pack_units(
    units: list[dict[str, Any]],
    target_words: int,
    max_words: int,
    min_words: int,
) -> list[list[dict[str, Any]]]:
    """Pack paragraph/sentence units into child chunks.

    The packer preserves unit order. It starts a new chunk when adding the next
    unit would exceed `max_words` after the current chunk has reached the target
    size. A very short tail is merged into the previous chunk when possible.
    """

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_words = 0

    for unit in units:
        unit_words = count_words(unit["text"])
        would_exceed = current and current_words + unit_words > max_words
        reached_target = current_words >= target_words
        if would_exceed or (reached_target and current_words + unit_words > target_words):
            chunks.append(current)
            current = []
            current_words = 0
        current.append(unit)
        current_words += unit_words

    if current:
        if chunks and current_words < min_words:
            chunks[-1].extend(current)
        else:
            chunks.append(current)
    return chunks

# viết được chunk đượec tạo từ section nào, và paragrap nào trong section đó
def build_source_spans(section_index: int, units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert packed units to source span records."""

    spans = []
    for unit in units:
        span = {
            "section_index": section_index,
            "char_start": unit["char_start"],
            "char_end": unit["char_end"],
        }
        if unit.get("span_mode"):
            span["span_mode"] = unit["span_mode"]
        spans.append(span)
    return spans


def make_source_text(units: list[dict[str, Any]], joiner: str = "\n\n") -> str:
    """Join unit texts into the source text stored on a Child."""

    return joiner.join(unit["text"] for unit in units).strip()

# dựa vào title đón type document ở mức đơn giản
def infer_document_type(document: dict[str, Any]) -> str:
    """Infer a coarse document type from URL and section count."""

    url = str(document.get("url") or "").lower()
    sections = document.get("sections") or []
    title = str(document.get("title") or "").lower()
    if "recommended-trip" in url or "itinerary" in url or "day " in title:
        return "itinerary"
    if "2025.vietnam.travel" in url:
        return "news_article"
    if len(sections) <= 1:
        return "unstructured_article"
    if re.search(r"\b\d+\b|\btop\b|\bbest\b|\bways\b|\bthings\b", title):
        return "listicle_or_guide"
    return "structured_article"

# lấy đoạn text đầu tiên
def first_section_text(document: dict[str, Any]) -> tuple[str, int | None]:
    """Return the first usable section text and its section index."""

    for section in document.get("sections") or []:
        if section.get("is_noise_section"):
            continue
        text = (section.get("text") or "").strip()
        if text:
            return text, section.get("section_index")
    return "", None

# taoj sumary cho Parent
def build_parent_summary(document: dict[str, Any], max_words: int) -> dict[str, Any]:
    """Build Parent summary from early paragraph text before the next heading.

    For structured pages, this uses `sections[0].text`, which represents the
    paragraphs under the document title before the first section heading. For
    short/unstructured articles, this is simply the first paragraph(s) of the
    article body.
    """

    text, section_index = first_section_text(document)
    if text:
        paragraphs = paragraph_spans(text)
        selected: list[dict[str, Any]] = []
        total = 0
        for paragraph in paragraphs:
            paragraph_words = count_words(paragraph["text"])
            if selected and total + paragraph_words > max_words:
                break
            selected.append(paragraph)
            total += paragraph_words
            if total >= max_words:
                break
        summary_text = truncate_words(make_source_text(selected), max_words)
        spans = (
            build_source_spans(section_index, selected)
            if section_index is not None and selected
            else []
        )
        return {
            "context_summary": summary_text,
            "summary_type": "extractive_lead",
            "summary_source_spans": spans,
            "summary_model": None,
        }

    meta_description = normalize_space(document.get("meta_description"))
    if meta_description:
        return {
            "context_summary": truncate_words(meta_description, max_words),
            "summary_type": "meta_description",
            "summary_source_spans": [],
            "summary_model": None,
        }

    return {
        "context_summary": "",
        "summary_type": "none",
        "summary_source_spans": [],
        "summary_model": None,
    }


def build_retrieval_text(
    document: dict[str, Any],
    section: dict[str, Any],
    source_text: str,
) -> str:
    """Build derived text for BM25/vector retrieval."""

    title = clean_display_title(document.get("title") or "")
    heading = normalize_space(section.get("heading") or title)
    heading_path = " > ".join(normalize_space(item) for item in section.get("heading_path") or [])
    lines = [
        f"Article: {title}",
        f"Section: {heading}",
    ]
    if heading_path:
        lines.append(f"Heading path: {heading_path}")
    if document.get("url"):
        lines.append(f"Source: {document['url']}")
    if document.get("language"):
        lines.append(f"Language: {document['language']}")
    lines.extend(["", source_text])
    return "\n".join(lines).strip()


def build_parent(document: dict[str, Any], child_ids: list[str], config: ChunkConfig) -> dict[str, Any]:
    """Create one document-level Parent record."""

    document_id = document["document_id"]
    title = document.get("title") or ""
    summary = build_parent_summary(document, config.summary_max_words)
    sections = document.get("sections") or []
    return {
        "schema_version": "1.0",
        "parent_id": f"{document_id}:parent:document",
        "document_id": document_id,
        "parent_parent_id": None,
        "parent_granularity": "document",
        "node_type": "document",
        "title": title,
        "clean_title": clean_display_title(title),
        "heading": title,
        "heading_path": [title] if title else [],
        **summary,
        "source_section_indexes": [
            section.get("section_index") for section in sections if section.get("section_index") is not None
        ],
        "child_ids": child_ids,
        "metadata": {
            "document_type": infer_document_type(document),
            "language": document.get("language"),
            "source": document.get("source"),
            "source_domain": document.get("source_domain"),
            "source_url": document.get("url"),
            "raw_html_path": document.get("raw_html_path"),
        },
        "expandable": True,
        "pipeline_version": "document-parent-child-v1",
    }


def child_type_for_section(section: dict[str, Any], chunk_index_in_section: int) -> str:
    """Label child type from section position and split index."""

    if chunk_index_in_section > 0:
        return "split_part"
    if section.get("section_index") == 0:
        return "overview"
    return "section"


def build_children_for_document(
    document: dict[str, Any],
    config: ChunkConfig,
) -> list[dict[str, Any]]:
    """Create Child chunks for all non-noise sections in one document."""

    document_id = document["document_id"]
    parent_id = f"{document_id}:parent:document"
    children: list[dict[str, Any]] = []

    for section in document.get("sections") or []:
        if section.get("is_noise_section"):
            continue

        units = section_units(section, max_words=config.max_child_words)
        if not units:
            continue
        packed_chunks = pack_units(
            units,
            target_words=config.target_child_words,
            max_words=config.max_child_words,
            min_words=config.min_child_words,
        )

        for chunk_index_in_section, packed_units in enumerate(packed_chunks):
            source_text = make_source_text(packed_units)
            if not source_text:
                continue
            global_child_index = len(children)
            section_index = section.get("section_index", global_child_index)
            child_id = f"{document_id}:child:{section_index:04d}:{chunk_index_in_section:02d}"
            child = {
                "schema_version": "1.0",
                "child_id": child_id,
                "document_id": document_id,
                "parent_id": parent_id,
                "child_index": global_child_index,
                "section_index": section_index,
                "section_chunk_index": chunk_index_in_section,
                "child_type": child_type_for_section(section, chunk_index_in_section),
                "heading": section.get("heading"),
                "heading_path": section.get("heading_path") or [],
                "source_spans": build_source_spans(section_index, packed_units),
                "source_joiner": "\n\n",
                "source_text": source_text,
                "retrieval_text": build_retrieval_text(document, section, source_text),
                "metadata": {
                    "document_type": infer_document_type(document),
                    "language": document.get("language"),
                    "source_domain": document.get("source_domain"),
                    "source_url": document.get("url"),
                    "heading_source": section.get("heading_source"),
                    "heading_level": section.get("heading_level"),
                },
                "word_count": count_words(source_text),
                "previous_child_id": None,
                "next_child_id": None,
                "pipeline_version": "document-parent-child-v1",
            }
            children.append(child)

    for index, child in enumerate(children):
        if index > 0:
            child["previous_child_id"] = children[index - 1]["child_id"]
        if index + 1 < len(children):
            child["next_child_id"] = children[index + 1]["child_id"]
    return children


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write rows to compact UTF-8 JSONL."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_report(path: Path, summary: dict[str, Any]) -> None:
    """Write a short Markdown report for the chunk build."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Document Parent-Child Chunk Report",
        "",
        f"- Input: `{summary['input']}`",
        f"- Parent output: `{summary['parent_output']}`",
        f"- Child output: `{summary['child_output']}`",
        f"- Documents: {summary['documents']}",
        f"- Parents: {summary['parents']}",
        f"- Children: {summary['children']}",
        "",
        "## Child Type",
        "",
        "| Type | Count |",
        "|---|---:|",
    ]
    for key, value in summary["child_type_counts"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(
        [
            "",
            "## Word Count",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| min | {summary['child_word_count']['min']} |",
            f"| max | {summary['child_word_count']['max']} |",
            f"| avg | {summary['child_word_count']['avg']} |",
            "",
            "## Notes",
            "",
            "- Parent is the whole document/article.",
            "- Parent summary is extracted from the first available paragraphs before the next heading.",
            "- Children are paragraph/section chunks attached to the document Parent.",
            "- Long sections are split by paragraph and sentence before any word fallback.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def build_chunks(config: ChunkConfig) -> dict[str, Any]:
    """Run the full Parent/Child chunking pipeline."""

    documents = load_clean_documents(config.input_path)
    parents: list[dict[str, Any]] = []
    children: list[dict[str, Any]] = []

    for document in documents:
        document_children = build_children_for_document(document, config)
        child_ids = [child["child_id"] for child in document_children]
        parents.append(build_parent(document, child_ids, config))
        children.extend(document_children)

    write_jsonl(config.parent_output_path, parents)
    write_jsonl(config.child_output_path, children)

    child_word_counts = [child["word_count"] for child in children]
    summary = {
        "input": str(config.input_path),
        "parent_output": str(config.parent_output_path),
        "child_output": str(config.child_output_path),
        "report": str(config.report_path),
        "documents": len(documents),
        "parents": len(parents),
        "children": len(children),
        "child_type_counts": dict(Counter(child["child_type"] for child in children)),
        "child_word_count": {
            "min": min(child_word_counts) if child_word_counts else 0,
            "max": max(child_word_counts) if child_word_counts else 0,
            "avg": round(sum(child_word_counts) / len(child_word_counts), 2)
            if child_word_counts
            else 0,
        },
    }
    write_report(config.report_path, summary)
    return summary


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Build document-level Parent records and semantic Child chunks."
    )
    parser.add_argument("--input", default="data/document_clean.json", help="Clean JSON input.")
    parser.add_argument(
        "--parents-output",
        default="data/chunks/semantic_parents.jsonl",
        help="Parent JSONL output.",
    )
    parser.add_argument(
        "--children-output",
        default="data/chunks/semantic_children.jsonl",
        help="Child JSONL output.",
    )
    parser.add_argument(
        "--report",
        default="hybrid_chunk_report/parent_child_chunk_report.md",
        help="Markdown report output.",
    )
    parser.add_argument("--summary-max-words", type=int, default=120)
    parser.add_argument("--target-child-words", type=int, default=220)
    parser.add_argument("--max-child-words", type=int, default=360)
    parser.add_argument("--min-child-words", type=int, default=40)
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""

    configure_console_encoding()
    args = parse_args()
    config = ChunkConfig(
        input_path=Path(args.input),
        parent_output_path=Path(args.parents_output),
        child_output_path=Path(args.children_output),
        report_path=Path(args.report),
        summary_max_words=args.summary_max_words,
        target_child_words=args.target_child_words,
        max_child_words=args.max_child_words,
        min_child_words=args.min_child_words,
    )
    result = build_chunks(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
