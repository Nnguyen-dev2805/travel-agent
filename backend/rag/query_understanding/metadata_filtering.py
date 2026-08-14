"""Tạo metadata pre-filter và cộng điểm metadata sau rerank cho RAG retrieval."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.rag.query_understanding.query_parser import ParsedQuery

MAX_LOCATION_FILTER_FIELDS = 8


@dataclass
class QueryFilters:
    """Chứa các filter metadata sẽ được truyền xuống Chroma hoặc Elasticsearch."""

    exact_filters: Dict[str, Any] = field(default_factory=dict)
    location_cities: List[str] = field(default_factory=list)
    regions: List[str] = field(default_factory=list)
    original_location_cities: List[str] = field(default_factory=list)

    def chroma_where(self) -> Optional[Dict[str, Any]]:
        """Tạo điều kiện `where` cho Chroma bằng exact match trên metadata.

        Location được so với `primary_location` và các field scalar `location_1`
        đến `location_8`, vì Chroma filter không xử lý list metadata trực tiếp tốt.
        """
        clauses = [{key: value} for key, value in self.exact_filters.items() if value not in (None, "")]
        location_clauses = []
        for city in self.location_cities:
            location_clauses.append({"primary_location": city})
            for index in range(1, MAX_LOCATION_FILTER_FIELDS + 1):
                location_clauses.append({f"location_{index}": city})
        if location_clauses:
            clauses.append(location_clauses[0] if len(location_clauses) == 1 else {"$or": location_clauses})
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def elasticsearch_filters(self) -> Dict[str, Any]:
        """Tạo dict filter cho Elasticsearch/BM25.

        `__locations_any` là key nội bộ để Elasticsearch search trên nhiều field
        location như `locations` và `primary_location`.
        """
        filters = dict(self.exact_filters)
        if self.location_cities:
            filters["__locations_any"] = self.location_cities
        return filters


def _strip_accents(value: str) -> str:
    """Bỏ dấu tiếng Việt và vá một số ký tự bị lỗi mã hóa phổ biến."""
    value = value.replace("Đ", "D").replace("đ", "d")
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _norm(value: Any) -> str:
    """Chuẩn hóa value để so khớp metadata: lowercase, bỏ dấu, bỏ ký tự đặc biệt."""
    text = str(value or "").lower().strip()
    text = _strip_accents(text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _metadata_values(metadata: Dict[str, Any], key: str) -> List[str]:
    """Lấy một field metadata về dạng list string sạch.

    Metadata có thể được lưu dưới dạng string phân tách bằng dấu phẩy, list,
    tuple/set hoặc scalar nên cần gom về cùng format trước khi tính điểm.
    """
    value = metadata.get(key)
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _unique(values: List[str]) -> List[str]:
    """Loại trùng theo khóa normalize nhưng giữ nguyên thứ tự và text gốc."""
    seen = set()
    unique_values = []
    for value in values:
        key = _norm(value)
        if key and key not in seen:
            seen.add(key)
            unique_values.append(value)
    return unique_values


def expand_location_filters(locations: List[str]) -> List[str]:
    """Chỉ giữ các location được xác nhận từ query để dùng làm exact filter.

    Không tự mở rộng sang địa điểm gần đó, tỉnh/thành cha hoặc hub du lịch.
    Nếu expansion được dùng làm hard filter thì cần catalog có kiểm chứng từ corpus,
    nếu không retrieval có thể loại nhầm tài liệu đúng hoặc kéo vào scope không liên quan.
    """
    return _unique(locations)


def build_query_filters(
    parsed_query: ParsedQuery,
    default_language: str = "en",
) -> QueryFilters:
    """Tạo pre-filter trước retrieval từ ParsedQuery.

    Hàm này chỉ tạo location/region filter khi query parser đã xác nhận có
    địa điểm hoặc vùng rõ ràng. Nếu không có geo scope, trả filter rỗng để
    retrieval chạy rộng theo semantic/BM25.
    """
    exact_filters: Dict[str, Any] = {}
    if not parsed_query.locations and not parsed_query.regions:
        return QueryFilters()

    if parsed_query.regions and not parsed_query.locations:
        exact_filters["region"] = parsed_query.regions[0]

    return QueryFilters(
        exact_filters=exact_filters,
        location_cities=expand_location_filters(parsed_query.locations),
        regions=parsed_query.regions,
        original_location_cities=parsed_query.locations,
    )


def _field_match_score(metadata: Dict[str, Any], key: str, query_values: List[str]) -> Optional[float]:
    """Tính điểm match giữa query values và một field metadata.

    Trả `None` khi query không có signal cho field đó, `1.0` khi match exact,
    `0.75` khi match một phần, và `0.0` khi query có signal nhưng metadata không khớp.
    """
    if not query_values:
        return None
    metadata_values = [_norm(item) for item in _metadata_values(metadata, key)]
    if not metadata_values:
        return 0.0

    best = 0.0
    for query_value in query_values:
        query_key = _norm(query_value)
        if not query_key:
            continue
        if query_key in metadata_values:
            best = max(best, 1.0)
        elif any(query_key in value or value in query_key for value in metadata_values):
            best = max(best, 0.75)
    return best


def _topic_score(metadata: Dict[str, Any], topic: Optional[str]) -> Optional[float]:
    """Tính điểm liên quan giữa topic query và topic trong metadata.

    Ưu tiên exact match, sau đó partial substring, cuối cùng dùng token overlap
    để cho điểm mềm khi topic gần nhau nhưng không trùng hoàn toàn.
    """
    if not topic:
        return None
    metadata_topic = _norm(metadata.get("topic"))
    query_topic = _norm(topic)
    if not metadata_topic:
        return 0.0
    if query_topic == metadata_topic:
        return 1.0
    if query_topic in metadata_topic or metadata_topic in query_topic:
        return 0.85

    query_tokens = set(query_topic.split())
    metadata_tokens = set(metadata_topic.split())
    if not query_tokens or not metadata_tokens:
        return 0.0
    overlap = len(query_tokens & metadata_tokens) / len(query_tokens | metadata_tokens)
    return min(0.7, overlap)


def metadata_score(metadata: Dict[str, Any], parsed_query: ParsedQuery) -> float:
    """Tính điểm metadata relevance để cộng sau rerank.

    Điểm này chỉ dùng các soft metadata signal: `topic`, `entity_type`,
    và `content_type`. Location không được tính ở đây vì location đã được xử lý
    ở bước pre-filter khi đủ chắc chắn.
    """
    weighted_scores = []
    for weight, score in (
        (0.40, _topic_score(metadata, parsed_query.topic)),
        (0.35, _field_match_score(metadata, "entity_type", parsed_query.entity_type)),
        (0.25, _field_match_score(metadata, "content_type", [parsed_query.content_type] if parsed_query.content_type else [])),
    ):
        if score is not None:
            weighted_scores.append((weight, max(0.0, min(1.0, score))))

    total_weight = sum(weight for weight, _ in weighted_scores)
    if total_weight <= 0:
        return 0.0
    return round(sum(weight * score for weight, score in weighted_scores) / total_weight, 6)


def _normalize_cross_scores(results: List[Dict[str, Any]]) -> List[float]:
    """Chuẩn hóa score của cross-encoder/retriever về khoảng 0..1.

    Nếu score đã nằm trong 0..1 thì clamp trực tiếp. Nếu score nằm ngoài khoảng,
    dùng min-max normalization. Khi mọi score bằng nhau, dùng sigmoid để tránh
    chia cho 0.
    """
    scores = [float(item.get("rerank_score", item.get("score", 0.0)) or 0.0) for item in results]
    if not scores:
        return []
    if all(0.0 <= score <= 1.0 for score in scores):
        return [max(0.0, min(1.0, score)) for score in scores]

    min_score = min(scores)
    max_score = max(scores)
    if not math.isclose(min_score, max_score):
        span = max_score - min_score
        return [(score - min_score) / span for score in scores]

    return [1.0 / (1.0 + math.exp(-scores[0])) for _ in scores]


def apply_metadata_bonus(
    results: List[Dict[str, Any]],
    parsed_query: ParsedQuery,
    cross_encoder_weight: float = 0.8,
    metadata_weight: float = 0.2,
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Cộng metadata bonus vào kết quả sau rerank và sắp xếp lại.

    Mặc định:
    `final_score = 0.8 * cross_encoder_score + 0.2 * metadata_score`.
    Hàm trả về danh sách đã được gắn thêm `metadata_score`, `final_score`
    và cắt theo `top_k` nếu có.
    """
    if not results:
        return []

    total = cross_encoder_weight + metadata_weight
    if total <= 0:
        cross_encoder_weight = 0.8
        metadata_weight = 0.2
        total = 1.0
    cross_weight = cross_encoder_weight / total
    meta_weight = metadata_weight / total
    normalized_cross_scores = _normalize_cross_scores(results)

    rescored = []
    for result, cross_score in zip(results, normalized_cross_scores):
        metadata_relevance = metadata_score(result.get("metadata") or {}, parsed_query)
        item = dict(result)
        item["cross_encoder_score_normalized"] = round(cross_score, 6)
        item["metadata_score"] = metadata_relevance
        item["final_score"] = round(cross_weight * cross_score + meta_weight * metadata_relevance, 6)
        item["score"] = item["final_score"]
        rescored.append(item)

    ranked = sorted(rescored, key=lambda item: float(item.get("final_score") or 0.0), reverse=True)
    return ranked[:top_k] if top_k else ranked
