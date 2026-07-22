"""Tạo fixed-size chunks cho baseline Standard RAG."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


LOGGER = logging.getLogger(__name__)

WORD_PATTERN = re.compile(r"\S+", re.UNICODE)


def configure_console_encoding() -> None:
    """Cấu hình console UTF-8 để argparse/help in tiếng Việt ổn định trên Windows."""

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class ChunkingConfig:
    """Cấu hình chia chunk theo số từ cho Standard RAG."""

    input_path: Path
    output_path: Path
    chunk_size_words: int = 350
    chunk_overlap_words: int = 40
    min_chunk_words: int = 60


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any] | None, str | None]]:
    """Đọc từng dòng JSONL và trả về lỗi parse nếu có."""

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                yield line_number, json.loads(line), None
            except json.JSONDecodeError as exc:
                yield line_number, None, str(exc)


def split_words(text: str) -> list[str]:
    """Tách văn bản thành danh sách token dạng từ/ký hiệu theo whitespace."""

    return WORD_PATTERN.findall(text)


def join_words(words: list[str]) -> str:
    """Ghép danh sách từ thành text gọn để dùng trong chunk."""

    return " ".join(words).strip()


def build_retrieval_text(document: dict[str, Any], chunk_text: str) -> str:
    """Tạo text giàu ngữ cảnh tối thiểu để dùng cho embedding/retrieval."""

    return "\n".join(
        [
            f"Document: {document['clean_title']}",
            f"Source: {document['source_url']}",
            f"Language: {document['language']}",
            "",
            chunk_text,
        ]
    ).strip()


def create_chunk(
    document: dict[str, Any],
    chunk_index: int,
    chunk_text: str,
    start_word: int,
    end_word: int,
) -> dict[str, Any]:
    """Tạo một chunk Standard RAG với metadata tối thiểu."""

    document_id = document["document_id"]
    return {
        "chunk_id": f"{document_id}_chunk_{chunk_index:04d}",
        "document_id": document_id,
        "chunk_index": chunk_index,
        "source_url": document["source_url"],
        "source_domain": document["source_domain"],
        "document_title": document["clean_title"],
        "language": document["language"],
        "source_text": chunk_text,
        "retrieval_text": build_retrieval_text(document, chunk_text),
        "word_count": len(split_words(chunk_text)),
        "start_word": start_word,
        "end_word": end_word,
    }


def chunk_document(document: dict[str, Any], config: ChunkingConfig) -> list[dict[str, Any]]:
    """Chia một document thành các fixed-size chunks có overlap."""

    words = split_words(str(document.get("plain_text") or ""))
    if not words:
        return []

    if config.chunk_overlap_words >= config.chunk_size_words:
        raise ValueError("chunk_overlap_words phải nhỏ hơn chunk_size_words")

    chunks: list[dict[str, Any]] = []
    step = config.chunk_size_words - config.chunk_overlap_words
    start = 0

    while start < len(words):
        end = min(start + config.chunk_size_words, len(words))
        chunk_words = words[start:end]

        if len(chunk_words) < config.min_chunk_words and chunks:
            # Với phần đuôi quá ngắn, gộp vào chunk trước để tránh chunk ít giá trị retrieval.
            previous = chunks[-1]
            previous_words = split_words(previous["source_text"])
            merged_words = previous_words + words[start:end]
            merged_text = join_words(merged_words)
            previous["source_text"] = merged_text
            previous["retrieval_text"] = build_retrieval_text(document, merged_text)
            previous["word_count"] = len(merged_words)
            previous["end_word"] = end
            break

        chunk_text = join_words(chunk_words)
        chunks.append(create_chunk(document, len(chunks), chunk_text, start, end))

        if end >= len(words):
            break
        start += step

    return chunks


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Ghi dữ liệu ra file JSONL UTF-8 dạng compact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def create_standard_chunks(config: ChunkingConfig) -> dict[str, Any]:
    """Tạo fixed-size chunks cho toàn bộ document Standard RAG."""

    if not config.input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file đầu vào: {config.input_path}")
    if config.chunk_size_words <= 0:
        raise ValueError("chunk_size_words phải lớn hơn 0")
    if config.min_chunk_words <= 0:
        raise ValueError("min_chunk_words phải lớn hơn 0")

    all_chunks: list[dict[str, Any]] = []
    rejected_reasons: dict[str, int] = {}
    invalid_json_lines: list[dict[str, Any]] = []
    document_count = 0

    for line_number, document, parse_error in iter_jsonl(config.input_path):
        if parse_error:
            rejected_reasons["invalid_json"] = rejected_reasons.get("invalid_json", 0) + 1
            invalid_json_lines.append({"line": line_number, "error": parse_error})
            continue

        assert document is not None
        document_count += 1
        chunks = chunk_document(document, config)
        if not chunks:
            rejected_reasons["no_chunks"] = rejected_reasons.get("no_chunks", 0) + 1
            continue
        all_chunks.extend(chunks)

    written = write_jsonl(config.output_path, all_chunks)
    chunk_word_counts = [chunk["word_count"] for chunk in all_chunks]
    summary = {
        "input_path": str(config.input_path),
        "output_path": str(config.output_path),
        "chunk_size_words": config.chunk_size_words,
        "chunk_overlap_words": config.chunk_overlap_words,
        "min_chunk_words": config.min_chunk_words,
        "input_documents": document_count,
        "output_chunks": written,
        "rejected_documents": sum(rejected_reasons.values()),
        "rejected_reasons": rejected_reasons,
        "invalid_json_examples": invalid_json_lines[:5],
        "chunk_word_count": {
            "min": min(chunk_word_counts) if chunk_word_counts else 0,
            "max": max(chunk_word_counts) if chunk_word_counts else 0,
            "avg": round(sum(chunk_word_counts) / len(chunk_word_counts), 2) if chunk_word_counts else 0,
        },
    }
    LOGGER.info("Đã tạo %s chunks cho Standard RAG", written)
    return summary


def parse_args() -> argparse.Namespace:
    """Đọc tham số CLI."""

    parser = argparse.ArgumentParser(description="Tạo fixed-size chunks cho baseline Standard RAG.")
    parser.add_argument(
        "--input",
        default="data/processed/standard_rag_documents.jsonl",
        help="Đường dẫn file document Standard RAG đầu vào.",
    )
    parser.add_argument(
        "--output",
        default="data/chunks/chunks_standard_rag.jsonl",
        help="Đường dẫn file chunks Standard RAG đầu ra.",
    )
    parser.add_argument("--chunk-size-words", type=int, default=350, help="Số từ mục tiêu trong mỗi chunk.")
    parser.add_argument("--chunk-overlap-words", type=int, default=40, help="Số từ overlap giữa hai chunk.")
    parser.add_argument("--min-chunk-words", type=int, default=60, help="Số từ tối thiểu của một chunk.")
    parser.add_argument("--log-level", default="INFO", help="Mức logging của Python.")
    return parser.parse_args()


def main() -> int:
    """Điểm vào CLI."""

    configure_console_encoding()
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s:%(message)s")
    config = ChunkingConfig(
        input_path=Path(args.input),
        output_path=Path(args.output),
        chunk_size_words=args.chunk_size_words,
        chunk_overlap_words=args.chunk_overlap_words,
        min_chunk_words=args.min_chunk_words,
    )
    summary = create_standard_chunks(config)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
