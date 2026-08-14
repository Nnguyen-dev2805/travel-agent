"""Rerank candidate chunks bằng cross-encoder được serve qua TEI /rerank endpoint."""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("travel_agent_reranker")


class RerankError(RuntimeError):
    """Lỗi được raise khi TEI reranker không chấm điểm được candidates."""


class TEICrossEncoderReranker:
    """Rerank các candidate đã retrieve bằng cross-encoder chạy trên TEI.

    TEI reranker nhận POST /rerank với payload dạng:
    {"query": "...", "texts": ["candidate 1", "candidate 2"], "raw_scores": false}
    """

    def __init__(
        self,
        rerank_url: str,
        timeout_seconds: float = 120,
        max_text_chars: int = 2000,
        batch_size: int = 8,
        raw_scores: bool = False,
        client: Optional[httpx.Client] = None,
    ) -> None:
        """Khởi tạo reranker client.

        `rerank_url` là endpoint TEI /rerank. `batch_size` giới hạn số candidate
        gửi trong một request, còn `max_text_chars` cắt bớt text quá dài để tránh
        payload lớn hoặc vượt giới hạn model.
        """
        if not rerank_url:
            raise ValueError("TEI_RERANK_URL is required when reranking is enabled.")

        self.rerank_url = rerank_url
        self.timeout_seconds = timeout_seconds
        self.max_text_chars = max_text_chars
        self.batch_size = max(1, batch_size)
        self.raw_scores = raw_scores
        self.client = client

    @staticmethod
    def sanitize_text(value: str) -> str:
        """Làm sạch text trước khi gửi sang TEI reranker.

        Hàm loại bỏ null/control characters và gộp whitespace để tránh lỗi ở một
        số backend reranker khi gặp ký tự không hợp lệ.
        """
        text = str(value or "").replace("\x00", " ")
        text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text or " "

    @staticmethod
    def _metadata_text(metadata: Dict[str, Any]) -> str:
        """Tạo phần prefix metadata ngắn để đưa thêm ngữ cảnh cho cross-encoder."""
        parts = []
        for label, key in (
            ("Title", "title"),
            ("Heading", "heading"),
            ("Path", "heading_path"),
            ("Location", "locations"),
            ("Category", "category"),
        ):
            value = metadata.get(key)
            if value:
                parts.append(f"{label}: {value}")
        return "\n".join(parts)

    def candidate_text(self, result: Dict[str, Any]) -> str:
        """Tạo text candidate gửi sang cross-encoder.

        Text gồm prefix metadata như title, heading, location, category cộng với
        body chunk. Kết quả được sanitize và cắt theo `max_text_chars`.
        """
        metadata = result.get("metadata") or {}
        body = str(result.get("text") or metadata.get("source_text") or "")
        prefix = self._metadata_text(metadata)
        text = f"{prefix}\n\n{body}".strip() if prefix else body.strip()
        return self.sanitize_text(text)[: self.max_text_chars]

    def _post_rerank(self, query: str, texts: List[str]) -> Any:
        """Gửi HTTP POST tới TEI /rerank và trả JSON response."""
        payload = {
            "query": query,
            "texts": texts,
            "raw_scores": self.raw_scores,
        }

        if self.client is not None:
            response = self.client.post(self.rerank_url, json=payload, timeout=self.timeout_seconds)
        else:
            response = httpx.post(self.rerank_url, json=payload, timeout=self.timeout_seconds)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = response.text[:2000]
            raise RerankError(
                f"TEI rerank request failed with HTTP {response.status_code}: {body}"
            ) from exc
        return response.json()

    @staticmethod
    def _rank_items(payload: Any) -> List[Dict[str, Any]]:
        """Chuẩn hóa các dạng response TEI rerank về list dict."""
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("results", "ranks", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise ValueError(f"Unexpected TEI rerank response shape: {type(payload).__name__}")

    @staticmethod
    def _rank_index(item: Dict[str, Any]) -> int:
        """Lấy index candidate từ một item response của TEI."""
        for key in ("index", "text_index", "document_index"):
            if key in item:
                return int(item[key])
        raise ValueError(f"TEI rerank item missing index: {item}")

    @staticmethod
    def _rank_score(item: Dict[str, Any]) -> float:
        """Lấy relevance score từ một item response của TEI."""
        for key in ("score", "relevance_score", "logit"):
            if key in item:
                score = float(item[key])
                if math.isnan(score):
                    raise ValueError(f"TEI rerank item returned NaN score: {item}")
                return score
        return 0.0

    def _score_batch(
        self,
        query: str,
        results: List[Dict[str, Any]],
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Chấm điểm một batch candidates bằng TEI reranker.

        Hàm gửi query + candidate texts sang TEI, đọc thứ hạng/score trả về,
        rồi gắn thêm các field `rerank_score`, `rerank_rank`, `pre_rerank_score`
        vào từng result.
        """
        texts = [self.candidate_text(result) for result in results]
        payload = self._post_rerank(query, texts)
        rank_items = self._rank_items(payload)

        reranked: List[Dict[str, Any]] = []
        for rank, item in enumerate(rank_items, start=1):
            index = self._rank_index(item)
            if index < 0 or index >= len(results):
                logger.warning("Ignoring out-of-range rerank index %s for %s candidates.", index, len(results))
                continue

            result = dict(results[index])
            result["rerank_score"] = self._rank_score(item)
            result["rerank_rank"] = offset + rank
            result["reranker"] = "tei_cross_encoder"
            result["pre_rerank_score"] = result.get("score")
            result["pre_rerank_retriever"] = result.get("retriever")
            result["score"] = result["rerank_score"]
            reranked.append(result)

        return reranked

    def _score_in_batches(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Chia candidates thành nhiều batch, rerank từng batch rồi sort lại theo score."""
        reranked: List[Dict[str, Any]] = []
        for start in range(0, len(results), self.batch_size):
            batch = results[start : start + self.batch_size]
            reranked.extend(self._score_batch(query, batch, offset=start))
        return sorted(reranked, key=lambda item: float(item.get("rerank_score") or 0.0), reverse=True)

    def score(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Trả toàn bộ candidates đã được sort theo cross-encoder score.

        Nếu batch rerank gặp lỗi NaN từ TEI, hàm retry từng candidate một để
        giữ được nhiều kết quả hợp lệ nhất có thể.
        """
        query_text = query.strip()
        if not query_text or not results:
            return results

        if len(results) > self.batch_size:
            try:
                return self._score_in_batches(query_text, results)
            except RerankError as err:
                if "nan" not in str(err).lower():
                    raise
                logger.warning("TEI rerank batched request produced NaN; retrying candidates one by one.")

        try:
            return self._score_batch(query_text, results)
        except RerankError as err:
            if "nan" not in str(err).lower():
                raise
            logger.warning("TEI rerank batch produced NaN; retrying candidates one by one.")

        reranked = []
        fallback_score = min((float(item.get("score") or 0.0) for item in results), default=0.0) - 1.0
        for index, result in enumerate(results):
            try:
                reranked.extend(self._score_batch(query_text, [result], offset=index))
            except Exception as err:
                logger.warning(
                    "Skipping failed rerank candidate index=%s chunk_id=%s: %s",
                    index,
                    result.get("chunk_id"),
                    err,
                )
                item = dict(result)
                item["reranker"] = "tei_cross_encoder"
                item["rerank_error"] = str(err)
                item["rerank_score"] = fallback_score
                item["rerank_rank"] = None
                item["pre_rerank_score"] = item.get("score")
                item["pre_rerank_retriever"] = item.get("retriever")
                item["score"] = fallback_score
                reranked.append(item)

        return sorted(reranked, key=lambda item: float(item.get("rerank_score") or 0.0), reverse=True)

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int,
        fail_open: bool = False,
    ) -> List[Dict[str, Any]]:
        """Rerank candidates và trả về top-k cuối cùng.

        Nếu `fail_open=True`, khi reranker lỗi hệ thống sẽ trả lại thứ tự retrieval
        ban đầu thay vì làm hỏng toàn bộ pipeline.
        """
        if top_k <= 0:
            return []
        try:
            return self.score(query, results)[:top_k]
        except Exception as err:
            if not fail_open:
                raise
            logger.warning("Reranking failed; returning original retrieval order: %s", err)
            fallback = []
            for rank, result in enumerate(results[:top_k], start=1):
                item = dict(result)
                item["reranker"] = "tei_cross_encoder"
                item["rerank_error"] = str(err)
                item["rerank_rank"] = None
                item["pre_rerank_rank"] = rank
                item["pre_rerank_score"] = item.get("score")
                item["pre_rerank_retriever"] = item.get("retriever")
                fallback.append(item)
            return fallback
