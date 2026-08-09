"""RAG Generation Service connecting Vector Retrieval to LLM Response Generation."""

import logging
import os
from typing import Any, Dict, List
# pyrefly: ignore [missing-import]
from openai import OpenAI
from backend.app.config import settings
from backend.rag.embedding import VectorEmbedder
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

        # 1. Retrieve candidate chunks
        query_vector = self.embedder.embed_query(user_text)
        retrieval_k = max(top_k, settings.RERANKER_CANDIDATE_K) if self.reranker else top_k
        if self.hybrid_retriever:
            retrieved_results = self.hybrid_retriever.search(user_text, query_vector, top_k=retrieval_k)
        else:
            retrieved_results = self.vector_store.search_similar(query_vector, top_k=retrieval_k)

        if self.reranker:
            retrieved_results = self.reranker.rerank(user_text, retrieved_results, top_k=top_k)

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
        }
