"""Export Parent-Child chunking output to JSON for manual inspection."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.rag.chunking.loader import load_jsonl_dataset
from backend.rag.chunking.parent_child_chunker import ParentChildChunker


DEFAULT_INPUT = ROOT_DIR / "data" / "processed" / "vietnam_travel_cleaned.json"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "processed" / "parent_child_chunks_preview.json"
DEFAULT_PARENTS_OUTPUT = ROOT_DIR / "data" / "processed" / "parent_chunks_preview.json"
DEFAULT_CHILDREN_OUTPUT = ROOT_DIR / "data" / "processed" / "children_chunks_preview.json"


def export_parent_child_chunks(
    input_path: Path,
    output_path: Path,
    parents_output_path: Path | None = None,
    children_output_path: Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Chunk cleaned documents and write parent/child records to JSON."""
    documents = load_jsonl_dataset(input_path)
    if limit is not None:
        documents = documents[:limit]

    chunker = ParentChildChunker()
    parents = []
    children = []

    for document in documents:
        parent, child_chunks = chunker.chunk_document(document)
        parents.append(asdict(parent))
        children.extend(asdict(child) for child in child_chunks)

    payload = {
        "input_path": str(input_path),
        "document_count": len(documents),
        "parent_count": len(parents),
        "child_count": len(children),
        "parents": parents,
        "children": children,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if parents_output_path:
        parents_output_path.parent.mkdir(parents=True, exist_ok=True)
        parents_output_path.write_text(
            json.dumps(parents, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if children_output_path:
        children_output_path.parent.mkdir(parents=True, exist_ok=True)
        children_output_path.write_text(
            json.dumps(children, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return payload


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Export ParentChunk and ChildChunk JSON from cleaned travel data."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="Input cleaned JSON/JSONL file.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output JSON file for inspection.",
    )
    parser.add_argument(
        "--parents-output",
        default=str(DEFAULT_PARENTS_OUTPUT),
        help="Output JSON file containing only parent chunks.",
    )
    parser.add_argument(
        "--children-output",
        default=str(DEFAULT_CHILDREN_OUTPUT),
        help="Output JSON file containing only child chunks.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of documents to export. Use 0 to export all documents.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the export script."""
    args = parse_args()
    limit = None if args.limit == 0 else args.limit
    payload = export_parent_child_chunks(
        input_path=Path(args.input),
        output_path=Path(args.output),
        parents_output_path=Path(args.parents_output),
        children_output_path=Path(args.children_output),
        limit=limit,
    )
    print(
        json.dumps(
            {
                "output_path": str(Path(args.output)),
                "parents_output": str(Path(args.parents_output)),
                "children_output": str(Path(args.children_output)),
                "document_count": payload["document_count"],
                "parent_count": payload["parent_count"],
                "child_count": payload["child_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
