"""RAG Generation Service connecting Vector Retrieval to LLM Response Generation."""

import logging
import os
from typing import Any, Dict, List
# pyrefly: ignore [missing-import]
from openai import OpenAI
from backend.app.config import settings
from backend.rag.embedding import VectorEmbedder
from backend.rag.query_understanding import (
    ParsedQuery,
    QueryFilters,
    QwenQueryParser,
    apply_metadata_bonus,
    build_query_filters,
)
from backend.rag.reranking import TEICrossEncoderReranker
from backend.rag.retrieval import ChromaVectorStore, ElasticsearchBM25Store, HybridRetriever

logger = logging.getLogger("travel_agent_rag_service")


class RAGService:
    """Orchestrates retrieval of relevant travel knowledge and LLM answer generation."""

    def __init__(self, collection_name: str | None = None) -> None:
        self.embedder = VectorEmbedder()
        self.collection_name = collection_name or settings.RAG_COLLECTION_NAME
        self.retriever_mode = settings.RETRIEVER_MODE
        self.vector_store = ChromaVectorStore(collection_name=self.collection_name)
        self.hybrid_retriever = None
        self.reranker = None
        self.query_parser = None

        if self.retriever_mode == "hybrid":
            bm25_store = ElasticsearchBM25Store(
                url=settings.ELASTICSEARCH_URL,
                index_name=settings.ELASTICSEARCH_INDEX,
                username=settings.ELASTICSEARCH_USERNAME,
                password=settings.ELASTICSEARCH_PASSWORD,
                api_key=settings.ELASTICSEARCH_API_KEY,
                verify_certs=settings.ELASTICSEARCH_VERIFY_CERTS,
                request_timeout=settings.ELASTICSEARCH_REQUEST_TIMEOUT,
            )
            self.hybrid_retriever = HybridRetriever(
                vector_store=self.vector_store,
                bm25_store=bm25_store,
                candidate_k=settings.HYBRID_CANDIDATE_K,
                rrf_k=settings.HYBRID_RRF_K,
                dense_weight=settings.HYBRID_DENSE_WEIGHT,
                bm25_weight=settings.HYBRID_BM25_WEIGHT,
            )
        elif self.retriever_mode != "dense":
            raise ValueError("RETRIEVER_MODE must be either 'dense' or 'hybrid'.")

        if settings.RERANKER_ENABLED:
            if settings.RERANKER_PROVIDER != "tei":
                raise ValueError("RERANKER_PROVIDER must be 'tei'.")
            self.reranker = TEICrossEncoderReranker(
                rerank_url=settings.TEI_RERANK_URL,
                timeout_seconds=settings.RERANKER_TIMEOUT_SECONDS,
                max_text_chars=settings.RERANKER_MAX_TEXT_CHARS,
                batch_size=settings.RERANKER_BATCH_SIZE,
                raw_scores=settings.RERANKER_RAW_SCORES,
            )

        if settings.QUERY_PARSER_ENABLED:
            self.query_parser = QwenQueryParser(
                base_url=settings.QUERY_PARSER_BASE_URL,
                api_key=settings.QUERY_PARSER_API_KEY,
                model=settings.QUERY_PARSER_MODEL,
                timeout_seconds=settings.QUERY_PARSER_TIMEOUT_SECONDS,
            )

    def _count_chroma_candidates(self, query_filters: QueryFilters | None) -> int:
        if query_filters is None:
            return self.vector_store.count()
        chroma_where = query_filters.chroma_where()
        if not chroma_where:
            return self.vector_store.count()
        try:
            matches = self.vector_store.collection.get(where=chroma_where, include=[])
        except (TypeError, ValueError):
            matches = self.vector_store.collection.get(where=chroma_where, include=["metadatas"])
        return len(matches.get("ids") or [])

    def _resolve_metadata_prefilter(
        self,
        query_filters: QueryFilters | None,
        candidate_k: int,
    ) -> tuple[QueryFilters | None, int, str]:
        if query_filters is None:
            return None, self.vector_store.count(), ""

        chroma_where = query_filters.chroma_where()
        elasticsearch_filters = query_filters.elasticsearch_filters()
        candidate_count = self._count_chroma_candidates(query_filters)
        if not chroma_where and not elasticsearch_filters:
            return query_filters, candidate_count, ""

        minimum_candidates = max(1, candidate_k)
        if candidate_count < minimum_candidates:
            reason = f"candidate_count {candidate_count} < k_candidate {minimum_candidates}"
            logger.info("Metadata pre-filter fallback to full retrieval: %s", reason)
            return QueryFilters(), candidate_count, reason

        return query_filters, candidate_count, ""

    def _get_llm_client(self) -> OpenAI:
        """Get OpenAI client configured for GitHub Models API."""
        if not settings.GITHUB_TOKEN:
            logger.warning("GITHUB_TOKEN missing in environment settings.")
            raise ValueError("GITHUB_TOKEN is missing in server environment.")

        return OpenAI(
            base_url=settings.GITHUB_MODELS_URL,
            api_key=settings.GITHUB_TOKEN,
        )

    def generate_answer(self, user_message: str, top_k: int = 4) -> Dict[str, Any]:
        """Retrieve relevant context and generate source-cited response.

        Args:
            user_message: User query string.
            top_k: Number of relevant chunks to retrieve.

        Returns:
            Dictionary containing 'reply', 'model', and 'citations'.
        """
        user_text = user_message.strip()
        if not user_text:
            raise ValueError("User message content cannot be empty.")

        model_name = settings.LLM_MODEL
        logger.info(f"Processing RAG request for: '{user_text[:50]}...'")

        parsed_query = ParsedQuery(raw_query=user_text, language=settings.QUERY_PARSER_DEFAULT_LANGUAGE)
        query_filters = None
        if settings.METADATA_FILTERING_ENABLED and self.query_parser:
            try:
                parsed_query = self.query_parser.parse(user_text)
            except Exception as err:
                logger.warning("Query parser failed; continuing without parsed metadata: %s", err)
                parsed_query = ParsedQuery(raw_query=user_text, language=settings.QUERY_PARSER_DEFAULT_LANGUAGE)

        if settings.METADATA_FILTERING_ENABLED:
            query_filters = build_query_filters(
                parsed_query,
                default_language=settings.QUERY_PARSER_DEFAULT_LANGUAGE,
            )

        # 1. Retrieve candidate chunks
        query_vector = self.embedder.embed_query(user_text)
        retrieval_k = max(top_k, settings.RERANKER_CANDIDATE_K) if self.reranker else top_k
        if query_filters and query_filters.location_cities:
            retrieval_k = max(
                retrieval_k,
                top_k * max(1, settings.METADATA_FILTER_CANDIDATE_MULTIPLIER),
            )
        candidate_k = max(
            retrieval_k,
            settings.HYBRID_CANDIDATE_K if self.hybrid_retriever else retrieval_k,
        )
        raw_metadata_candidate_count = None
        metadata_fallback_reason = ""
        raw_query_filters = query_filters
        if settings.METADATA_FILTERING_ENABLED:
            query_filters, raw_metadata_candidate_count, metadata_fallback_reason = self._resolve_metadata_prefilter(
                query_filters,
                candidate_k=candidate_k,
            )

        if self.hybrid_retriever:
            retrieved_results = self.hybrid_retriever.search(
                user_text,
                query_vector,
                top_k=retrieval_k,
                filters=query_filters.elasticsearch_filters() if query_filters else None,
                chroma_where=query_filters.chroma_where() if query_filters else None,
            )
        else:
            retrieved_results = self.vector_store.search_similar(
                query_vector,
                top_k=retrieval_k,
                where=query_filters.chroma_where() if query_filters else None,
            )

        if self.reranker:
            rerank_k = max(top_k, len(retrieved_results)) if settings.METADATA_BONUS_ENABLED else top_k
            retrieved_results = self.reranker.rerank(user_text, retrieved_results, top_k=rerank_k)

        if settings.METADATA_BONUS_ENABLED:
            retrieved_results = apply_metadata_bonus(
                retrieved_results,
                parsed_query,
                cross_encoder_weight=settings.METADATA_BONUS_CROSS_ENCODER_WEIGHT,
                metadata_weight=settings.METADATA_BONUS_WEIGHT,
                top_k=top_k,
            )
        else:
            retrieved_results = retrieved_results[:top_k]

        # 2. Build context string and extract citations
        context_parts = []
        citations_map: Dict[str, str] = {}

        for idx, item in enumerate(retrieved_results, 1):
            text = item.get("text", "")
            meta = item.get("metadata", {})
            title = meta.get("title", "Vietnam Travel Guide")
            url = meta.get("url", "")

            context_parts.append(f"[Nguồn {idx}: {title}]\n{text}")

            if url and title:
                citations_map[title] = url

        context_str = "\n\n---\n\n".join(context_parts) if context_parts else "Không tìm thấy tài liệu liên quan."

        # 3. Construct System Prompt
        system_prompt = (
            "Bạn là Trợ lý AI Du lịch Việt Nam thông minh, thân thiện và am hiểu địa phương. "
            "Hãy sử dụng thông tin Cẩm nang Du lịch được cung cấp bên dưới để trả lời câu hỏi của người dùng bằng Tiếng Việt. "
            "Nếu thông tin được cung cấp có chứa câu trả lời, hãy trả lời chính xác, hữu ích và tự nhiên. "
            "Không tự bịa đặt thông tin không có trong cẩm nang.\n\n"
            f"=== CẨM NANG DU LỊCH THAM KHẢO ===\n{context_str}"
        )

        # 4. Call LLM API
        client = self._get_llm_client()
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=0.7,
            max_tokens=800,
        )

        reply_content = completion.choices[0].message.content

        # Format citations list
        citations_list = [
            {"title": title, "url": url}
            for title, url in citations_map.items()
        ]

        logger.info(f"Successfully generated RAG response with {len(citations_list)} citations.")

        return {
            "reply": reply_content,
            "model": model_name,
            "citations": citations_list,
            "parsed_query": parsed_query.to_dict(),
            "metadata_filter": {
                "raw_candidate_count": raw_metadata_candidate_count,
                "fallback_reason": metadata_fallback_reason,
                "raw_expanded_locations": raw_query_filters.location_cities if raw_query_filters else [],
                "expanded_locations": query_filters.location_cities if query_filters else [],
                "chroma_where": query_filters.chroma_where() if query_filters else None,
            },
        }
