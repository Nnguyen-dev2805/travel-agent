"""Convert semantic Parent-Child children into the legacy FAISS chunk schema.

The existing FAISS embedding pipeline expects Standard RAG-like fields such as
`chunk_id`, `chunk_index`, `document_title`, and `source_url`. Semantic children
use `child_id` and richer Parent/Child metadata. This script creates a bridge
JSONL so the old embedding/index workflow can be reused without changing the
retriever code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


def configure_console_encoding() -> None:
    """Print Unicode reliably on Windows terminals."""

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    """Yield JSON objects from a UTF-8 JSONL file."""

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                yield json.loads(line)


def load_parents(path: Path) -> dict[str, dict[str, Any]]:
    """Load Parent records keyed by parent_id."""

    return {row["parent_id"]: row for row in iter_jsonl(path)}


def parent_title(parent: dict[str, Any] | None, child: dict[str, Any]) -> str:
    """Pick the best display title for a compatible chunk."""

    if parent:
        return str(parent.get("clean_title") or parent.get("title") or "")
    metadata = child.get("metadata") or {}
    return str(metadata.get("document_title") or child.get("heading") or "")


def convert_child(child: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
    """Convert one semantic Child into the legacy chunk schema."""

    metadata = child.get("metadata") or {}
    parent_metadata = (parent or {}).get("metadata") or {}
    source_url = metadata.get("source_url") or parent_metadata.get("source_url")
    source_domain = metadata.get("source_domain") or parent_metadata.get("source_domain")
    language = metadata.get("language") or parent_metadata.get("language") or "unknown"

    return {
        "chunk_id": child["child_id"],
        "document_id": child["document_id"],
        "chunk_index": child.get("child_index"),
        "source_url": source_url,
        "source_domain": source_domain,
        "document_title": parent_title(parent, child),
        "language": language,
        "source_text": child.get("source_text") or "",
        "retrieval_text": child.get("retrieval_text") or child.get("source_text") or "",
        "word_count": child.get("word_count"),
        "parent_id": child.get("parent_id"),
        "child_id": child.get("child_id"),
        "child_type": child.get("child_type"),
        "section_index": child.get("section_index"),
        "section_chunk_index": child.get("section_chunk_index"),
        "heading": child.get("heading"),
        "heading_path": child.get("heading_path") or [],
        "source_spans": child.get("source_spans") or [],
        "previous_child_id": child.get("previous_child_id"),
        "next_child_id": child.get("next_child_id"),
        "parent_context_summary": (parent or {}).get("context_summary"),
        "document_type": metadata.get("document_type") or parent_metadata.get("document_type"),
        "pipeline_version": "semantic-child-legacy-faiss-v1",
    }


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Write compact UTF-8 JSONL."""

    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def prepare_chunks(children_path: Path, parents_path: Path, output_path: Path) -> dict[str, Any]:
    """Create the compatible chunk JSONL and return a summary."""

    parents = load_parents(parents_path)
    converted: list[dict[str, Any]] = []
    missing_parent_count = 0

    for child in iter_jsonl(children_path):
        parent = parents.get(str(child.get("parent_id")))
        if parent is None:
            missing_parent_count += 1
        converted.append(convert_child(child, parent))

    written = write_jsonl(output_path, converted)
    return {
        "children_input": str(children_path),
        "parents_input": str(parents_path),
        "output": str(output_path),
        "chunks_written": written,
        "missing_parent_count": missing_parent_count,
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""

    parser = argparse.ArgumentParser(description="Prepare semantic children for legacy FAISS embedding.")
    parser.add_argument("--children", default="data/chunks/semantic_children.jsonl")
    parser.add_argument("--parents", default="data/chunks/semantic_parents.jsonl")
    parser.add_argument("--output", default="data/chunks/semantic_children_faiss_compatible.jsonl")
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""

    configure_console_encoding()
    args = parse_args()
    summary = prepare_chunks(Path(args.children), Path(args.parents), Path(args.output))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
