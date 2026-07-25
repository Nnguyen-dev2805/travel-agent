"""Clean document structure before semantic Parent-Child chunking.

This script focuses on two concrete issues found in T01:

1. Long/paragraph-like headings near the beginning of an article.
   These headings are often article summaries or lead paragraphs, not real
   semantic headings. The cleaner demotes them into section text and keeps the
   original value in provenance fields.

2. CTA/caption/noise nodes inside `heading_path`.
   These nodes, such as "Click the image below for a 360-degree tour", pollute
   the hierarchy. The cleaner removes them from `heading_path` while preserving
   a list of removed nodes for audit.

The output is a JSON array at `data/document_clean.json` by default.
"""

import argparse
import copy
import json
import re
from collections import Counter
from pathlib import Path


# Với các chú thích có heading, cần phần loại bỏ : như hình ảnh 360 , Click images 
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

SITE_SUFFIX_RE = re.compile(r"\s*\|\s*Vietnam Tourism\s*$", re.I)
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.I)
WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_END_RE = re.compile(r"[.!?]")


def normalize_space(value):
    """Collapse repeated whitespace and trim the final string."""
    return WHITESPACE_RE.sub(" ", str(value or "")).strip()


def normalize_title(value):
    """Normalize titles/headings for comparison without changing display text."""
    return SITE_SUFFIX_RE.sub("", normalize_space(value)).strip().lower()


def word_count(value):
    """Count simple whitespace-separated words for rule-based cleaning."""
    return len(normalize_space(value).split())


def is_noise_text(value):
    """Return True when a heading/path node is CTA, caption, credit, or UI text."""
    return bool(NOISE_RE.search(normalize_space(value)))


# giải quyết heading giống như 1 đoạn văn hơn là 1 tiêu đề, ví dụ ở các phần mở đầu giới thiệu 
# người ta thường highlight hoặc heading làm nổi bật lên đoạn văn đó
def is_paragraph_like_heading(heading):
    """Detect headings that look like prose instead of a compact section title.

    The rule is intentionally stricter than the T01 audit rule to avoid demoting
    valid travel headings such as "Best for river views: Sky 36, Da Nang".
    A heading is paragraph-like when it is long enough to behave like a lead
    sentence/paragraph, or when it has multiple sentence boundaries.
    """
    text = normalize_space(heading)
    words = word_count(text)
    sentence_marks = len(SENTENCE_END_RE.findall(text))
    return (
        words >= 18
        or len(text) >= 150
        or sentence_marks >= 2
        or (sentence_marks >= 1 and words >= 14)
    )


def should_demote_heading(section, document_title):
    """Decide whether a section heading should become lead/summary text.

    Only early non-document headings are demoted. Document titles can be long
    article titles, especially Vietnamese news titles, so they are preserved as
    headings. This keeps the first article title stable while moving accidental
    lead paragraphs out of hierarchy.
    """
    heading = section.get("heading") or ""
    section_index = section.get("section_index", 0)
    heading_source = (section.get("heading_source") or "").lower()

    if not heading or heading_source == "document":
        return False
    if section_index not in (0, 1):
        return False
    if normalize_title(heading) == normalize_title(document_title):
        return False
    return is_paragraph_like_heading(heading)


def clean_heading_path(heading_path):
    """Remove CTA/caption/noise nodes from a heading path.

    Returns a tuple `(cleaned_path, removed_nodes)`. Empty path items are also
    removed because they do not help hierarchy construction.
    """
    cleaned = []
    removed = []
    for node in heading_path or []:
        node_text = normalize_space(node)
        if not node_text:
            continue
        if is_noise_text(node_text):
            removed.append(node_text)
            continue
        cleaned.append(node)
    return cleaned, removed


# Hàm này dùng khi 1 heading bị demote xuốn sumary/text --> chọn  heading thay thế cho section đó
def choose_parent_heading(cleaned_path, document_title):
    """Choose the replacement heading after demoting a fake summary heading."""
    if cleaned_path:
        return cleaned_path[-1]
    return document_title

# đổi vai trò của heading thành text
def prepend_summary_to_text(summary, text):
    """Move a demoted heading into section text without duplicating content."""
    summary = normalize_space(summary)
    text = (text or "").strip()
    if not summary:
        return text
    if normalize_space(text).startswith(summary):
        return text
    if not text:
        return summary
    return f"{summary}\n\n{text}"

# tiến hành xử lý \
def clean_section(section, document_title):
    """Clean one section and return `(cleaned_section, stats)`.

    The function preserves provenance fields before mutating heading/path:

    - `original_heading`
    - `original_heading_path`
    - `demoted_summary_text`
    - `removed_heading_path_nodes`
    - `clean_actions`
    """
    cleaned = copy.deepcopy(section)
    stats = Counter()
    actions = []

    original_heading = cleaned.get("heading") or ""
    original_path = cleaned.get("heading_path") or []
    if isinstance(original_path, str):
        original_path = [original_path]

    cleaned_path, removed_nodes = clean_heading_path(original_path)
    if removed_nodes:
        cleaned["original_heading_path"] = original_path
        cleaned["removed_heading_path_nodes"] = removed_nodes
        cleaned["heading_path"] = cleaned_path
        actions.append("remove_noise_from_heading_path")
        stats["path_noise_removed"] += len(removed_nodes)
        stats["sections_with_path_noise"] += 1
    else:
        cleaned["heading_path"] = cleaned_path

    if should_demote_heading(cleaned, document_title):
        path_without_self = [
            node for node in cleaned_path if normalize_space(node) != normalize_space(original_heading)
        ]
        replacement_heading = choose_parent_heading(path_without_self, document_title)

        cleaned["original_heading"] = original_heading
        cleaned["demoted_summary_text"] = normalize_space(original_heading)
        cleaned["heading"] = replacement_heading
        cleaned["heading_path"] = path_without_self or [replacement_heading]
        cleaned["heading_source"] = "demoted_summary"
        cleaned["text"] = prepend_summary_to_text(original_heading, cleaned.get("text") or "")
        cleaned["word_count"] = word_count(cleaned.get("text") or "")
        actions.append("demote_paragraph_like_heading_to_summary_text")
        stats["demoted_paragraph_like_heading"] += 1

    if is_noise_text(cleaned.get("heading") or ""):
        cleaned["is_noise_section"] = True
        actions.append("mark_noise_heading")
        stats["noise_heading_marked"] += 1

    if actions:
        cleaned["clean_actions"] = actions
    return cleaned, stats


def rebuild_document_text(title, sections):
    """Rebuild a readable clean text field from cleaned headings and section text."""
    parts = [title]
    previous_heading = normalize_space(title)
    for section in sections:
        heading = normalize_space(section.get("heading") or "")
        text = (section.get("text") or "").strip()
        if heading and normalize_title(heading) != normalize_title(previous_heading):
            parts.append(heading)
            previous_heading = heading
        if text:
            parts.append(text)
    return "\n\n".join(part for part in parts if part)


def clean_document(document):
    """Clean all sections in one document and attach document-level metadata."""
    cleaned_doc = copy.deepcopy(document)
    title = cleaned_doc.get("title") or cleaned_doc.get("clean_title") or ""
    cleaned_sections = []
    stats = Counter()

    for section in cleaned_doc.get("sections") or []:
        cleaned_section, section_stats = clean_section(section, title)
        cleaned_sections.append(cleaned_section)
        stats.update(section_stats)

    cleaned_doc["sections"] = cleaned_sections
    cleaned_doc["clean_text"] = rebuild_document_text(title, cleaned_sections)
    cleaned_doc["cleaning_metadata"] = {
        "pipeline": "semantic_document_clean_v1",
        "handled_issues": [
            "paragraph_like_heading_at_article_start",
            "cta_caption_noise_in_heading_path",
        ],
        "stats": dict(stats),
    }
    return cleaned_doc, stats


def load_documents_jsonl(input_path):
    """Load input JSONL documents into memory."""
    documents = []
    with input_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                documents.append(json.loads(line))
    return documents


def write_clean_documents(documents, output_path):
    """Write cleaned documents as a UTF-8 JSON array with Vietnamese preserved."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(documents, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


def clean_file(input_path, output_path):
    """Run the full cleaning pipeline and return aggregate stats."""
    documents = load_documents_jsonl(input_path)
    cleaned_documents = []
    total_stats = Counter()

    for document in documents:
        cleaned_document, document_stats = clean_document(document)
        cleaned_documents.append(cleaned_document)
        total_stats.update(document_stats)

    write_clean_documents(cleaned_documents, output_path)
    return {
        "input": str(input_path),
        "output": str(output_path),
        "documents": len(cleaned_documents),
        "stats": dict(total_stats),
    }


def main():
    """Parse CLI arguments and run the cleaner."""
    parser = argparse.ArgumentParser(
        description="Clean documents.jsonl for semantic Parent-Child chunking."
    )
    parser.add_argument("--input", default="data/documents.jsonl", help="Input JSONL file.")
    parser.add_argument(
        "--output",
        default="data/document_clean.json",
        help="Output JSON file.",
    )
    args = parser.parse_args()

    result = clean_file(Path(args.input), Path(args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
