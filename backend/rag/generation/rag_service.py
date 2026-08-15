"""RAG Generation Service connecting Vector Retrieval to LLM Response Generation with Memory integration."""

import logging
import os
import json
from typing import Any, Dict, List, Optional
# pyrefly: ignore [missing-import]
from openai import OpenAI
from backend.app.config import settings
from backend.rag.embedding import VectorEmbedder
from backend.rag.retrieval import ChromaVectorStore

logger = logging.getLogger("travel_agent_rag_service")


class RAGService:
    """Orchestrates retrieval of relevant travel knowledge and LLM answer generation."""

    def __init__(
        self,
        llm_client: OpenAI,
        embedder: VectorEmbedder,
        vector_store: ChromaVectorStore,
    ) -> None:
        self._client = llm_client
        self.embedder = embedder
        self.vector_store = vector_store


    def generate_answer(
        self,
        user_message: str,
        top_k: int = 4,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        user_facts: Optional[str] = None,
        skip_rag_search: bool = False,
    ) -> Dict[str, Any]:
        """Retrieve relevant context and generate source-cited response with memory context.

        Args:
            user_message: User query string.
            top_k: Number of relevant chunks to retrieve.
            conversation_history: Sliding window short-term message history.
            user_facts: Formatted long-term user preferences and facts.
            skip_rag_search: If True, skips querying ChromaDB.

        Returns:
            Dictionary containing 'reply', 'model', and 'citations'.
        """
        user_text = user_message.strip()
        if not user_text:
            raise ValueError("User message content cannot be empty.")

        model_name = settings.MAIN_LLM_MODEL
        logger.info(f"Processing RAG request for: '{user_text[:50]}...'")

        context_parts = []
        citations_map: Dict[str, str] = {}

        if not skip_rag_search:
            # 1. Retrieve top-k similar chunks
            query_vector = self.embedder.embed_query(user_text)
            retrieved_results = self.vector_store.search_similar(query_vector, top_k=top_k)

            # 2. Build context string and extract citations
            for idx, item in enumerate(retrieved_results, 1):
                text = item.get("text", "")
                meta = item.get("metadata", {})
                title = meta.get("title", "Vietnam Travel Guide")
                url = meta.get("url", "")

                context_parts.append(f"[Nguồn {idx}: {title}]\n{text}")

                if url and title:
                    citations_map[title] = url

        context_str = "\n\n---\n\n".join(context_parts) if context_parts else "Không tìm thấy tài liệu liên quan hoặc không cần tra cứu."

        # 3. Construct System Prompt (Injecting Long-term User Facts if available)
        facts_section = f"\n\n=== THÔNG TIN CÁ NHÂN ĐÃ BIẾT VỀ NGUỜI DÙNG ===\n{user_facts}" if user_facts else ""
        
        if not skip_rag_search:
            system_prompt = (
                "Bạn là Trợ lý AI Du lịch Việt Nam thông minh, thân thiện và am hiểu địa phương. "
                "Hãy sử dụng thông tin Cẩm nang Du lịch và thông tin cá nhân người dùng bên dưới để trả lời câu hỏi bằng Tiếng Việt. "
                "Nếu thông tin được cung cấp có chứa câu trả lời, hãy trả lời chính xác, hữu ích và tự nhiên. "
                "Không tự bịa đặt thông tin không có trong cẩm nang.\n\n"
                f"=== CẨM NANG DU LỊCH THAM KHẢO ===\n{context_str}"
                f"{facts_section}"
            )
        else:
            system_prompt = (
                "Bạn là Trợ lý AI Du lịch Việt Nam thông minh, thân thiện và am hiểu địa phương. "
                "Hãy trả lời người dùng một cách ngắn gọn, thân thiện và tự nhiên bằng Tiếng Việt.\n\n"
                f"{facts_section}"
            )

        # 4. Construct Full Messages Stream (Injecting Short-term Conversation History)
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_text})
        
        logger.info(f"\n{'='*20} RAG GENERATION PROMPT {'='*20}\n{json.dumps(messages, ensure_ascii=False, indent=2)}\n{'='*63}")

        # 5. Call LLM API
        client = self._client
        completion = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.7,
            max_tokens=800,
        )

        reply_content = completion.choices[0].message.content
        logger.info(f"\n{'='*20} RAG GENERATION OUTPUT {'='*20}\n{reply_content}\n{'='*63}")
        
        if not reply_content or not reply_content.strip():
            logger.warning(f"LLM returned empty content. Raw response: {completion.model_dump()}")
            reply_content = "Xin lỗi, hệ thống AI (Google Gemini) không trả về kết quả (phản hồi trống). Vui lòng kiểm tra lại API Key, Tên Model hoặc thử lại sau!"


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
