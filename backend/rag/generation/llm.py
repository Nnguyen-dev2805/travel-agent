"""LLM answer generation over assembled context with a versioned prompt template."""

from __future__ import annotations

import logging
from typing import Optional

# pyrefly: ignore [missing-import]
from openai import OpenAI

from backend.app.config import settings
from backend.rag.contracts import ContextBundle, GeneratedAnswer

logger = logging.getLogger("travel_agent_llm_generator")

PROMPT_ID = "rag-structured-prompt-v1"

GENERATION_TEMPERATURE = 0.7
GENERATION_MAX_TOKENS = 800

INSUFFICIENT_EVIDENCE_REPLY = (
    "Tôi chưa có đủ thông tin trong cẩm nang để trả lời câu hỏi này một cách đáng tin cậy."
)

# Versioned prompt template. The wording is the characterized legacy
# RAGService system prompt moved verbatim (context header uses U+1EA8).
PROMPT_TEMPLATE = (
    "Bạn là Trợ lý AI Du lịch Việt Nam thông minh, thân thiện và am hiểu địa phương. "
    "Hãy sử dụng thông tin Cẩm nang Du lịch được cung cấp bên dưới để trả lời câu hỏi của người dùng bằng Tiếng Việt. "
    "Nếu thông tin được cung cấp có chứa câu trả lời, hãy trả lời chính xác, hữu ích và tự nhiên. "
    "Không tự bịa đặt thông tin không có trong cẩm nang.\n\n"
    "=== CẨM NANG DU LỊCH THAM KHẢO ===\n"
    "{context}"
)


class LLMGenerator:
    """Generates the final answer from a ContextBundle via the configured provider."""

    def __init__(self, client: Optional[OpenAI] = None) -> None:
        self._client = client

    def _get_llm_client(self) -> OpenAI:
        """Get OpenAI client configured for GitHub Models API (legacy behavior)."""
        if not settings.GITHUB_TOKEN:
            logger.warning("GITHUB_TOKEN missing in environment settings.")
            raise ValueError("GITHUB_TOKEN is missing in server environment.")

        return OpenAI(
            base_url=settings.GITHUB_MODELS_URL,
            api_key=settings.GITHUB_TOKEN,
        )

    def generate(self, user_message: str, context: ContextBundle) -> GeneratedAnswer:
        """Generate an answer for the user message using the assembled context.

        Args:
            user_message: Raw user query string sent to the provider.
            context: Assembled ContextBundle from the ContextAssembler.

        Returns:
            GeneratedAnswer with the reply, the configured model identity, and
            the citations carried through from the context bundle.
        """
        if context.insufficient_evidence:
            return GeneratedAnswer(
                reply=INSUFFICIENT_EVIDENCE_REPLY,
                model=settings.LLM_MODEL,
                citations=(),
            )

        system_prompt = PROMPT_TEMPLATE.format(context=context.prompt_context)

        client = self._client or self._get_llm_client()
        completion = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=GENERATION_TEMPERATURE,
            max_tokens=GENERATION_MAX_TOKENS,
        )

        reply_content = completion.choices[0].message.content

        return GeneratedAnswer(
            reply=reply_content,
            model=settings.LLM_MODEL,
            citations=context.citations,
        )
