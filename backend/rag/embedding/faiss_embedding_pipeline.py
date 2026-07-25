"""Tạo embeddings và lưu FAISS index cho baseline Standard RAG."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from backend.rag.embedding.embedding_model_registry import get_model_config, load_registry, validate_registry


LOGGER = logging.getLogger(__name__)


def configure_console_encoding() -> None:
    """Cấu hình console UTF-8 để argparse/help in tiếng Việt ổn định trên Windows."""

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class FaissEmbeddingConfig:
    """Cấu hình chạy embedding và build FAISS index."""

    registry_path: Path
    model_id: str
    chunks_path: Path | None = None
    embeddings_path: Path | None = None
    index_dir: Path | None = None
    batch_size: int = 16
    limit: int | None = None
    device: str | None = None
    error_report_path: Path = Path("report/task_04_embedding_faiss_errors.md")


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


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Ghi dữ liệu ra JSONL UTF-8 dạng compact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Ghi dữ liệu JSON UTF-8."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def model_output_name(model_id: str) -> str:
    """Chuyển model_id thành tên an toàn để dùng cho file/thư mục."""

    return model_id.replace("/", "__")


def resolve_paths(config: FaissEmbeddingConfig, registry: dict[str, Any]) -> tuple[Path, Path, Path]:
    """Xác định đường dẫn chunks, embeddings và index."""

    default_experiment = registry.get("default_experiment") or {}
    output_dir = Path(default_experiment.get("output_dir", "data/embeddings"))
    chunks_path = config.chunks_path or Path(default_experiment.get("dataset", "data/chunks/chunks_standard_rag.jsonl"))
    safe_model_name = model_output_name(config.model_id)
    embeddings_path = config.embeddings_path or output_dir / f"{safe_model_name}_standard_rag_embeddings.jsonl"
    index_dir = config.index_dir or Path("data/indexes") / f"{safe_model_name}_standard_rag"
    return chunks_path, embeddings_path, index_dir


def load_chunks(path: Path, limit: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Đọc chunks và trả về danh sách lỗi parse nếu có."""

    chunks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for line_number, row, parse_error in iter_jsonl(path):
        if parse_error:
            errors.append({"line": line_number, "error": parse_error})
            continue
        assert row is not None
        chunks.append(row)
        if limit is not None and len(chunks) >= limit:
            break
    return chunks, errors


def prepare_documents_for_embedding(chunks: list[dict[str, Any]], model_config: dict[str, Any]) -> list[str]:
    """Tạo danh sách text sẽ đưa vào embedding model."""

    document_prefix = str(model_config.get("document_prefix") or "")
    texts: list[str] = []
    for chunk in chunks:
        retrieval_text = str(chunk.get("retrieval_text") or "")
        texts.append(f"{document_prefix}{retrieval_text}")
    return texts


def encode_with_sentence_transformers(
    texts: list[str],
    model_config: dict[str, Any],
    batch_size: int,
    device: str | None,
) -> np.ndarray:
    """Sinh embeddings bằng sentence-transformers."""

    from sentence_transformers import SentenceTransformer

    model_name = str(model_config["model_name"])
    LOGGER.info("Đang tải embedding model: %s", model_name)
    model = SentenceTransformer(model_name, device=device) # lấy model embedding
    LOGGER.info("Đang embedding %s chunks với batch_size=%s", len(texts), batch_size)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return np.asarray(embeddings, dtype="float32")


def save_embedding_cache(
    path: Path,
    chunks: list[dict[str, Any]],
    embeddings: np.ndarray,
    model_config: dict[str, Any],
) -> int:
    """Lưu embedding cache dạng JSONL để debug và rebuild index."""

    rows = []
    for chunk, vector in zip(chunks, embeddings):
        rows.append(
            {
                "chunk_id": chunk["chunk_id"],
                "document_id": chunk["document_id"],
                "model_id": model_config["model_id"],
                "model_name": model_config["model_name"],
                "dimension": int(vector.shape[0]),
                "embedding": vector.tolist(),
                "metadata": {
                    "chunk_index": chunk.get("chunk_index"),
                    "document_title": chunk.get("document_title"),
                    "source_url": chunk.get("source_url"),
                    "source_domain": chunk.get("source_domain"),
                    "language": chunk.get("language"),
                    "word_count": chunk.get("word_count"),
                },
            }
        )
    return write_jsonl(path, rows)


def build_faiss_index(index_dir: Path, chunks: list[dict[str, Any]], embeddings: np.ndarray, model_config: dict[str, Any]) -> None:
    """Tạo FAISS index và metadata sidecar."""

    import faiss

    index_dir.mkdir(parents=True, exist_ok=True)
    dimension = int(embeddings.shape[1])
    index = faiss.IndexIDMap(faiss.IndexFlatIP(dimension))
    numeric_ids = np.arange(len(chunks), dtype="int64")
    index.add_with_ids(embeddings, numeric_ids)
    faiss.write_index(index, str(index_dir / "index.faiss"))

    metadata_rows = []
    for numeric_id, chunk in zip(numeric_ids.tolist(), chunks):
        metadata_rows.append(
            {
                "faiss_id": numeric_id,
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "chunk_index": chunk.get("chunk_index"),
                "document_title": chunk.get("document_title"),
                "source_url": chunk.get("source_url"),
                "source_domain": chunk.get("source_domain"),
                "language": chunk.get("language"),
                "word_count": chunk.get("word_count"),
                "source_text": chunk.get("source_text"),
                "retrieval_text": chunk.get("retrieval_text"),
            }
        )

    metadata_payload = {
        "index_type": "faiss.IndexIDMap(IndexFlatIP)",
        "similarity": "cosine_similarity_via_normalized_inner_product",
        "model_id": model_config["model_id"],
        "model_name": model_config["model_name"],
        "dimension": dimension,
        "chunk_count": len(chunks),
        "note": "FAISS chỉ lưu vector và numeric id. Metadata JSON được lưu cạnh index để lookup context/citation.",
        "items": metadata_rows,
    }
    write_json(index_dir / "metadata.json", metadata_payload)


def write_error_report(path: Path, title: str, errors: list[dict[str, Any]], summary: dict[str, Any] | None = None) -> None:
    """Ghi toàn bộ lỗi ra Markdown để dễ theo dõi."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {title}",
        "",
        "## Tóm Tắt",
        "",
    ]
    if summary:
        for key, value in summary.items():
            lines.append(f"- `{key}`: `{value}`")
    if not errors:
        lines.extend(["", "Không ghi nhận lỗi trong lần chạy này."])
    else:
        lines.extend(["", "## Danh Sách Lỗi", ""])
        for index, error in enumerate(errors, 1):
            lines.append(f"### Lỗi {index}")
            lines.append("")
            for key, value in error.items():
                if key == "traceback":
                    lines.append("```text")
                    lines.append(str(value))
                    lines.append("```")
                else:
                    lines.append(f"- `{key}`: `{value}`")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_embedding_pipeline(config: FaissEmbeddingConfig) -> dict[str, Any]:
    """Chạy pipeline embedding và build FAISS index."""

    errors: list[dict[str, Any]] = []
    started_at = time.time()
    registry = load_registry(config.registry_path)
    registry_errors = validate_registry(registry)
    if registry_errors:
        raise ValueError("Registry embedding model không hợp lệ:\n" + "\n".join(registry_errors))

    model_config = get_model_config(registry, config.model_id)
    if model_config.get("provider") != "local_sentence_transformers":
        raise NotImplementedError(
            "Pipeline hiện tại mới hỗ trợ provider local_sentence_transformers. "
            f"Provider nhận được: {model_config.get('provider')}"
        )

    chunks_path, embeddings_path, index_dir = resolve_paths(config, registry)
    chunks, parse_errors = load_chunks(chunks_path, config.limit)
    errors.extend({"type": "json_parse_error", **error} for error in parse_errors)
    if not chunks:
        raise ValueError(f"Không có chunk hợp lệ để embedding từ file: {chunks_path}")

    texts = prepare_documents_for_embedding(chunks, model_config)
    try:
        embeddings = encode_with_sentence_transformers(texts, model_config, config.batch_size, config.device)
        written_embeddings = save_embedding_cache(embeddings_path, chunks, embeddings, model_config)
        build_faiss_index(index_dir, chunks, embeddings, model_config)
    except Exception as exc:
        errors.append(
            {
                "type": "embedding_or_faiss_error",
                "error": repr(exc),
                "traceback": traceback.format_exc(),
            }
        )
        summary = {
            "model_id": config.model_id,
            "chunks_path": str(chunks_path),
            "embeddings_path": str(embeddings_path),
            "index_dir": str(index_dir),
            "status": "failed",
        }
        write_error_report(config.error_report_path, "Báo Cáo Lỗi Embedding Và FAISS", errors, summary)
        raise

    elapsed_seconds = round(time.time() - started_at, 2)
    summary = {
        "status": "success",
        "model_id": config.model_id,
        "model_name": model_config["model_name"],
        "chunks_path": str(chunks_path),
        "chunk_count": len(chunks),
        "embedding_dimension": int(embeddings.shape[1]),
        "embeddings_path": str(embeddings_path),
        "embeddings_written": written_embeddings,
        "index_dir": str(index_dir),
        "faiss_index_path": str(index_dir / "index.faiss"),
        "metadata_path": str(index_dir / "metadata.json"),
        "elapsed_seconds": elapsed_seconds,
        "errors_count": len(errors),
    }
    write_error_report(config.error_report_path, "Báo Cáo Lỗi Embedding Và FAISS", errors, summary)
    LOGGER.info("Hoàn tất embedding và FAISS index trong %s giây", elapsed_seconds)
    return summary


def parse_args() -> argparse.Namespace:
    """Đọc tham số CLI."""

    parser = argparse.ArgumentParser(description="Tạo embeddings và FAISS index cho Standard RAG.")
    parser.add_argument("--registry", default="configs/embedding_models.json", help="Đường dẫn registry embedding models.")
    parser.add_argument("--model-id", default="multilingual-e5-large", help="Model id trong registry.")
    parser.add_argument("--chunks", default=None, help="Đường dẫn chunks JSONL. Mặc định lấy từ registry.")
    parser.add_argument("--embeddings-output", default=None, help="Đường dẫn embedding cache JSONL.")
    parser.add_argument("--index-dir", default=None, help="Thư mục lưu FAISS index và metadata.")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size khi encode embeddings.")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số chunk để chạy thử.")
    parser.add_argument("--device", default=None, help="Thiết bị cho sentence-transformers, ví dụ cpu hoặc cuda.")
    parser.add_argument(
        "--error-report",
        default="report/task_04_embedding_faiss_errors.md",
        help="File Markdown ghi lỗi nếu có.",
    )
    parser.add_argument("--log-level", default="INFO", help="Mức logging của Python.")
    return parser.parse_args()


def main() -> int:
    """Điểm vào CLI."""

    configure_console_encoding()
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s:%(message)s")
    summary = run_embedding_pipeline(
        FaissEmbeddingConfig(
            registry_path=Path(args.registry),
            model_id=args.model_id,
            chunks_path=Path(args.chunks) if args.chunks else None,
            embeddings_path=Path(args.embeddings_output) if args.embeddings_output else None,
            index_dir=Path(args.index_dir) if args.index_dir else None,
            batch_size=args.batch_size,
            limit=args.limit,
            device=args.device,
            error_report_path=Path(args.error_report),
        )
    )
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
