"""Đánh index và truy xuất BM25 bằng Elasticsearch cho các child chunk lấy từ Chroma."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

try:
    from elasticsearch import Elasticsearch, helpers
except ImportError:  # pragma: no cover - exercised in environments without ES client
    Elasticsearch = None  # type: ignore[assignment]
    helpers = None  # type: ignore[assignment]

from backend.rag.retrieval.vector_store import ChromaVectorStore

logger = logging.getLogger("travel_agent_elasticsearch_bm25")


class ElasticsearchBM25Store:
    """Quản lý Elasticsearch index và search child chunk bằng BM25."""

    def __init__(
        self,
        url: str = "http://localhost:9200",
        index_name: str = "travel_child_chunks_v1",
        username: str = "",
        password: str = "",
        api_key: str = "",
        verify_certs: bool = False,
        request_timeout: int = 30,
        client: Any = None,
    ) -> None:
        """Khởi tạo Elasticsearch client và lưu thông tin index.

        Có thể truyền `client` giả trong unit test. Nếu không truyền, class sẽ
        tự tạo Elasticsearch client từ URL, credential và timeout trong config.
        """
        self.url = url
        self.index_name = index_name
        self.request_timeout = request_timeout

        if client is not None:
            self.client = client
            return

        if Elasticsearch is None:
            raise RuntimeError(
                "The 'elasticsearch' package is not installed. "
                "Install dependencies from requirements.txt before using BM25 Elasticsearch retrieval."
            )

        kwargs: Dict[str, Any] = {
            "request_timeout": request_timeout,
            "verify_certs": verify_certs,
        }
        if api_key:
            kwargs["api_key"] = api_key
        elif username or password:
            kwargs["basic_auth"] = (username, password)

        self.client = Elasticsearch(url, **kwargs)

    @staticmethod
    def index_settings() -> Dict[str, Any]:
        """Tạo settings/mapping cho index child chunks.

        Mapping định nghĩa analyzer `travel_text` với lowercase + asciifolding
        để search không phân biệt hoa/thường và dấu. Các field text chính dùng
        similarity BM25 tùy chỉnh `travel_bm25`.
        """
        text_field = {
            "type": "text", # phục vụ text search
            "analyzer": "travel_text",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
        }
        keyword_with_text = {
            "type": "keyword",
            "fields": {"text": {"type": "text", "analyzer": "travel_text"}},
        }
        return {
            "settings": {
                "analysis": {
                    "analyzer": {
                        "travel_text": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "asciifolding"],
                        }
                    }
                },
                "similarity": {
                    "travel_bm25": {
                        "type": "BM25",
                        "k1": 1.2,
                        "b": 0.75,
                    }
                },
            },
            "mappings": {
                "dynamic": True,
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "child_id": {"type": "keyword"},
                    "parent_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "record_type": {"type": "keyword"},
                    "title": {**text_field, "similarity": "travel_bm25"},
                    "heading": {**text_field, "similarity": "travel_bm25"},
                    "heading_path": {**text_field, "similarity": "travel_bm25"},
                    "retrieval_text": {
                        "type": "text",
                        "analyzer": "travel_text",
                        "similarity": "travel_bm25",
                    },
                    "source_text": {"type": "text", "index": False},
                    "locations": {**text_field, "similarity": "travel_bm25"},
                    "primary_location": keyword_with_text,
                    "region": keyword_with_text,
                    "category": keyword_with_text,
                    "topic": {**text_field, "similarity": "travel_bm25"},
                    "entity_type": keyword_with_text,
                    "content_type": {"type": "keyword"},
                    "language": {"type": "keyword"},
                    "source_domain": {"type": "keyword"},
                    "url": {"type": "keyword"},
                    "section_index": {"type": "integer"},
                    "chunk_index": {"type": "integer"},
                    "word_count": {"type": "integer"},
                    "char_length": {"type": "integer"},
                    "metadata": {"type": "object", "enabled": True},
                }
            },
        }

    def create_index(self, recreate: bool = False) -> None:
        """Tạo Elasticsearch index nếu chưa tồn tại.

        Nếu `recreate=True`, index cũ sẽ bị xóa rồi tạo lại từ đầu. Dùng khi
        muốn rebuild toàn bộ dữ liệu BM25 từ Chroma.
        """
        exists = self.client.indices.exists(index=self.index_name)
        if exists and recreate:
            logger.info("Deleting existing Elasticsearch index '%s'.", self.index_name)
            self.client.indices.delete(index=self.index_name)
            exists = False

        if not exists:
            logger.info("Creating Elasticsearch index '%s'.", self.index_name)
            self.client.indices.create(index=self.index_name, **self.index_settings())

    @staticmethod
    def _metadata_value(metadata: Dict[str, Any], key: str, default: Any = "") -> Any:
        """Lấy giá trị metadata theo key, trả default nếu value là None."""
        value = metadata.get(key)
        return default if value is None else value

    @classmethod
    def build_document(
        cls,
        chunk_id: str,
        retrieval_text: str,
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Chuyển một Chroma chunk thành document để index vào Elasticsearch.

        Hàm gom `retrieval_text`, `source_text` và các metadata quan trọng
        như location, topic, entity_type, content_type vào cùng một document
        Elasticsearch để phục vụ BM25 search và metadata filtering.
        """
        meta = metadata or {}
        child_id = str(cls._metadata_value(meta, "child_id", chunk_id) or chunk_id)
        source_text = str(cls._metadata_value(meta, "source_text", "") or "")
        return {
            "chunk_id": chunk_id,
            "child_id": child_id,
            "parent_id": str(cls._metadata_value(meta, "parent_id", "")),
            "document_id": str(cls._metadata_value(meta, "document_id", cls._metadata_value(meta, "doc_id", ""))),
            "record_type": str(cls._metadata_value(meta, "record_type", "child")),
            "title": str(cls._metadata_value(meta, "title", "")),
            "heading": str(cls._metadata_value(meta, "heading", "")),
            "heading_path": str(cls._metadata_value(meta, "heading_path", "")),
            "retrieval_text": retrieval_text or source_text,
            "source_text": source_text,
            "locations": str(cls._metadata_value(meta, "locations", "")),
            "primary_location": str(cls._metadata_value(meta, "primary_location", "")),
            "region": str(cls._metadata_value(meta, "region", "")),
            "category": str(cls._metadata_value(meta, "category", "")),
            "topic": str(cls._metadata_value(meta, "topic", "")),
            "entity_type": str(cls._metadata_value(meta, "entity_type", "")),
            "content_type": str(cls._metadata_value(meta, "content_type", "")),
            "language": str(cls._metadata_value(meta, "language", "en")),
            "source_domain": str(cls._metadata_value(meta, "source_domain", "")),
            "url": str(cls._metadata_value(meta, "url", "")),
            "section_index": int(cls._metadata_value(meta, "section_index", 0) or 0),
            "chunk_index": int(cls._metadata_value(meta, "chunk_index", 0) or 0),
            "word_count": int(cls._metadata_value(meta, "word_count", 0) or 0),
            "char_length": int(cls._metadata_value(meta, "char_length", 0) or 0),
            "metadata": meta,
        }

    def _bulk_actions(
        self,
        vector_store: ChromaVectorStore,
        batch_size: int,
    ) -> Iterable[Dict[str, Any]]:
        """Sinh các bulk action để copy dữ liệu từ Chroma sang Elasticsearch.

        Dữ liệu được đọc theo batch từ Chroma collection, sau đó mỗi chunk được
        chuyển thành action `_op_type=index` cho Elasticsearch helpers.bulk().
        """
        total = vector_store.count()
        for offset in range(0, total, batch_size):
            batch = vector_store.collection.get(
                limit=batch_size,
                offset=offset,
                include=["documents", "metadatas"],
            )
            ids = batch.get("ids") or []
            documents = batch.get("documents") or []
            metadatas = batch.get("metadatas") or []

            for chunk_id, document, metadata in zip(ids, documents, metadatas):
                yield {
                    "_op_type": "index",
                    "_index": self.index_name,
                    "_id": chunk_id,
                    "_source": self.build_document(chunk_id, document or "", metadata),
                }

    def index_from_chroma(
        self,
        vector_store: ChromaVectorStore,
        batch_size: int = 500,
        recreate: bool = False,
        refresh: bool = True,
    ) -> int:
        """Đồng bộ toàn bộ chunks từ Chroma collection sang Elasticsearch.

        Đây là hàm chính cho bước offline indexing BM25. Nó đảm bảo index tồn tại,
        đọc documents/metadatas từ Chroma, bulk index vào Elasticsearch và refresh
        index để dữ liệu có thể search ngay sau khi sync.
        """
        if helpers is None:
            raise RuntimeError("The 'elasticsearch' helpers module is unavailable.")

        self.create_index(recreate=recreate)
        total = vector_store.count()
        if total == 0:
            return 0

        success, _ = helpers.bulk(
            self.client,
            self._bulk_actions(vector_store, batch_size),
            stats_only=True,
            request_timeout=self.request_timeout,
        )
        if refresh:
            self.client.indices.refresh(index=self.index_name)
        logger.info("Indexed %s Chroma chunks into Elasticsearch '%s'.", success, self.index_name)
        return int(success)

    def search(
        self,
        query_text: str,
        top_k: int = 30,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search Elasticsearch bằng BM25 và trả kết quả theo format giống Chroma.

        Query chính dùng `multi_match` trên `retrieval_text`, `heading`, `title`
        và `locations`. Nếu có metadata filters, hàm thêm filter clause, gồm
        key nội bộ `__locations_any` để match trên nhiều field location.
        """
        query = query_text.strip()
        if not query:
            return []

        must: List[Dict[str, Any]] = [
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "retrieval_text^4",
                        "heading^1.5",
                        "title^1",
                        "locations^1",
                    ],
                    "type": "best_fields",
                    "operator": "or",
                }
            }
        ]
        filter_clauses = []
        for key, value in (filters or {}).items():
            if value in (None, ""):
                continue
            if key == "__locations_any":
                location_should = []
                for location in value:
                    location_should.extend(
                        [
                            {"match_phrase": {"locations": location}},
                            {"match_phrase": {"primary_location.text": location}},
                        ]
                    )
                if location_should:
                    filter_clauses.append(
                        {"bool": {"should": location_should, "minimum_should_match": 1}}
                    )
            else:
                filter_clauses.append({"term": {key: value}})

        body = {
            "query": {"bool": {"must": must, "filter": filter_clauses}},
            "size": top_k,
        }
        response = self.client.search(index=self.index_name, **body)

        results: List[Dict[str, Any]] = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            metadata = dict(source.get("metadata") or {})
            for key in (
                "title",
                "url",
                "source_domain",
                "source_text",
                "parent_id",
                "child_id",
                "document_id",
                "heading",
                "heading_level",
                "heading_path",
                "language",
                "locations",
                "primary_location",
                "region",
                "category",
                "topic",
                "entity_type",
                "content_type",
                "section_index",
                "chunk_index",
                "word_count",
                "char_length",
            ):
                if key in source and key not in metadata:
                    metadata[key] = source[key]

            results.append(
                {
                    "chunk_id": source.get("chunk_id") or hit.get("_id"),
                    "text": source.get("source_text") or source.get("retrieval_text", ""),
                    "metadata": metadata,
                    "score": float(hit.get("_score") or 0.0),
                    "retriever": "bm25_elasticsearch",
                }
            )

        return results
