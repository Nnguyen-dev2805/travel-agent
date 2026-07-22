"""Dense FAISS và BM25 + Dense retrievers cho baseline Standard RAG."""

from __future__ import annotations

import argparse
import collections
import json
import logging
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from backend.rag.embedding.embedding_model_registry import get_model_config, load_registry


LOGGER = logging.getLogger(__name__)
TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class RetrieverConfig:
    """Cấu hình chạy retriever baseline."""

    registry_path: Path = Path("configs/embedding_models.json")
    model_id: str = "paraphrase-multilingual-MiniLM-L12-v2"
    index_dir: Path = Path("data/indexes/paraphrase-multilingual-MiniLM-L12-v2_standard_rag")
    device: str | None = "cpu"


def configure_console_encoding() -> None:
    """Cấu hình console UTF-8 để in tiếng Việt ổn định trên Windows."""

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def tokenize(text: str) -> list[str]:
    """Token hóa đơn giản cho BM25."""

    return [token.casefold() for token in TOKEN_PATTERN.findall(text)]


def load_metadata(index_dir: Path) -> dict[str, Any]:
    """Đọc metadata sidecar cạnh FAISS index."""

    metadata_path = index_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Không tìm thấy metadata FAISS: {metadata_path}")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def format_result(rank: int, score: float, item: dict[str, Any], retriever: str) -> dict[str, Any]:
    """Chuẩn hóa output result cho các retriever."""

    return {
        "rank": rank,
        "score": round(float(score), 6),
        "retriever": retriever,
        "chunk_id": item.get("chunk_id"),
        "document_id": item.get("document_id"),
        "chunk_index": item.get("chunk_index"),
        "document_title": item.get("document_title"),
        "source_url": item.get("source_url"),
        "language": item.get("language"),
        "word_count": item.get("word_count"),
        "source_text": item.get("source_text"),
    }


class DenseFaissRetriever:
    """Retriever dense vector dùng FAISS."""

    def __init__(self, config: RetrieverConfig) -> None:
        self.config = config
        self.index = faiss.read_index(str(config.index_dir / "index.faiss"))
        self.metadata = load_metadata(config.index_dir)
        self.items_by_faiss_id = {int(item["faiss_id"]): item for item in self.metadata["items"]}
        registry = load_registry(config.registry_path)
        self.model_config = get_model_config(registry, config.model_id)
        self.model = None

    def _load_model(self) -> Any:
        """Lazy-load sentence-transformers model."""

        if self.model is None:
            # Dự án chỉ dùng PyTorch cho sentence-transformers.
            # Tắt TensorFlow để tránh lỗi Keras 3 trong môi trường có tensorflow/keras mới.
            os.environ["TRANSFORMERS_NO_TF"] = "1"
            os.environ["USE_TF"] = "0"
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(str(self.model_config["model_name"]), device=self.config.device)
        return self.model

    def embed_query(self, query: str) -> np.ndarray:
        """Tạo query embedding cùng model với index."""

        query_prefix = str(self.model_config.get("query_prefix") or "")
        query_text = f"{query_prefix}{query}"
        embedding = self._load_model().encode(
            [query_text],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(embedding, dtype="float32")

    def search(self, query: str, top_k: int = 5, search_k: int | None = None) -> list[dict[str, Any]]:
        """Search FAISS và trả về top-k chunks."""

        limit = search_k or top_k
        scores, ids = self.index.search(self.embed_query(query), limit)
        results: list[dict[str, Any]] = []
        for score, faiss_id in zip(scores[0].tolist(), ids[0].tolist()):
            if faiss_id == -1:
                continue
            item = self.items_by_faiss_id.get(int(faiss_id))
            if not item:
                continue
            results.append(format_result(len(results) + 1, score, item, "dense_faiss"))
            if len(results) >= top_k:
                break
        return results


class BM25Retriever:
    """BM25 retriever thuần Python cho corpus nhỏ."""

    def __init__(self, items: list[dict[str, Any]], k1: float = 1.5, b: float = 0.75) -> None:
        self.items = items
        self.k1 = k1
        self.b = b
        self.doc_tokens = [tokenize(str(item.get("source_text") or "")) for item in items]
        self.doc_lengths = [len(tokens) for tokens in self.doc_tokens]
        self.avg_doc_length = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0
        self.term_frequencies = [collections.Counter(tokens) for tokens in self.doc_tokens]
        self.document_frequencies: collections.Counter[str] = collections.Counter()
        for tokens in self.doc_tokens:
            self.document_frequencies.update(set(tokens))
        self.doc_count = len(items)

    def idf(self, term: str) -> float:
        """Tính IDF theo BM25 Okapi."""

        df = self.document_frequencies.get(term, 0)
        return math.log(1 + (self.doc_count - df + 0.5) / (df + 0.5))

    def score_document(self, query_terms: list[str], index: int) -> float:
        """Tính BM25 score cho một document/chunk."""

        score = 0.0
        frequencies = self.term_frequencies[index]
        doc_length = self.doc_lengths[index]
        for term in query_terms:
            tf = frequencies.get(term, 0)
            if tf == 0:
                continue
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_length / self.avg_doc_length)
            score += self.idf(term) * numerator / denominator
        return score

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search BM25 và trả về top-k chunks."""

        query_terms = tokenize(query)
        scored = [
            (index, self.score_document(query_terms, index))
            for index in range(len(self.items))
        ]
        scored = [(index, score) for index, score in scored if score > 0]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        results = []
        for rank, (index, score) in enumerate(scored[:top_k], 1):
            results.append(format_result(rank, score, self.items[index], "bm25"))
        return results


class HybridBM25DenseRetriever:
    """Hybrid retriever dùng BM25 + Dense FAISS với Reciprocal Rank Fusion."""

    def __init__(self, dense_retriever: DenseFaissRetriever, bm25_retriever: BM25Retriever, rrf_k: int = 60) -> None:
        self.dense_retriever = dense_retriever
        self.bm25_retriever = bm25_retriever
        self.rrf_k = rrf_k

    def search(self, query: str, top_k: int = 5, candidate_k: int = 20) -> list[dict[str, Any]]:
        """Search hybrid và fuse bằng RRF."""

        dense_results = self.dense_retriever.search(query, top_k=candidate_k)
        bm25_results = self.bm25_retriever.search(query, top_k=candidate_k)
        by_chunk: dict[str, dict[str, Any]] = {}
        scores: collections.Counter[str] = collections.Counter()
        sources: dict[str, list[str]] = collections.defaultdict(list)

        for result_set_name, result_set in [("dense", dense_results), ("bm25", bm25_results)]:
            for result in result_set:
                chunk_id = str(result["chunk_id"])
                by_chunk.setdefault(chunk_id, result)
                sources[chunk_id].append(result_set_name)
                scores[chunk_id] += 1.0 / (self.rrf_k + int(result["rank"]))

        ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
        final_results = []
        for rank, (chunk_id, score) in enumerate(ranked[:top_k], 1):
            item = dict(by_chunk[chunk_id])
            item["rank"] = rank
            item["score"] = round(float(score), 6)
            item["retriever"] = "hybrid_bm25_dense_rrf"
            item["matched_sources"] = sources[chunk_id]
            final_results.append(item)
        return final_results


def build_retrievers(config: RetrieverConfig) -> tuple[DenseFaissRetriever, BM25Retriever, HybridBM25DenseRetriever]:
    """Khởi tạo dense, BM25 và hybrid retrievers."""

    dense = DenseFaissRetriever(config)
    items = dense.metadata["items"]
    bm25 = BM25Retriever(items)
    hybrid = HybridBM25DenseRetriever(dense, bm25)
    return dense, bm25, hybrid


def parse_args() -> argparse.Namespace:
    """Đọc tham số CLI."""

    parser = argparse.ArgumentParser(description="Chạy thử Dense FAISS và BM25 + Dense retrievers.")
    parser.add_argument("--query", required=True, help="Câu hỏi truy vấn.")
    parser.add_argument("--top-k", type=int, default=5, help="Số kết quả cuối cùng.")
    parser.add_argument("--candidate-k", type=int, default=20, help="Số candidate cho hybrid retrieval.")
    parser.add_argument("--model-id", default="paraphrase-multilingual-MiniLM-L12-v2", help="Model id trong registry.")
    parser.add_argument(
        "--index-dir",
        default="data/indexes/paraphrase-multilingual-MiniLM-L12-v2_standard_rag",
        help="Thư mục FAISS index.",
    )
    parser.add_argument("--registry", default="configs/embedding_models.json", help="Registry embedding models.")
    parser.add_argument("--device", default="cpu", help="Thiết bị chạy embedding query.")
    parser.add_argument("--log-level", default="INFO", help="Mức logging.")
    return parser.parse_args()


def main() -> int:
    """Điểm vào CLI."""

    configure_console_encoding()
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s:%(message)s")
    dense, bm25, hybrid = build_retrievers(
        RetrieverConfig(
            registry_path=Path(args.registry),
            model_id=args.model_id,
            index_dir=Path(args.index_dir),
            device=args.device,
        )
    )
    payload = {
        "query": args.query,
        "dense": dense.search(args.query, top_k=args.top_k),
        "bm25": bm25.search(args.query, top_k=args.top_k),
        "hybrid_bm25_dense": hybrid.search(args.query, top_k=args.top_k, candidate_k=args.candidate_k),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
