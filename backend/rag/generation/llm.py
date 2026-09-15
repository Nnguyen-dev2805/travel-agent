"""LLM answer generation over assembled context with a versioned prompt template."""

from __future__ import annotations

import logging
from typing import Optional, Union

# pyrefly: ignore [missing-import]
from openai import OpenAI

from backend.app.config import settings
from backend.generation.contracts import (
    ContextSufficiency,
    GenerationCitation,
    GenerationContext,
    GenerationResult,
)
from backend.rag.contracts import ContextBundle

logger = logging.getLogger("travel_agent_llm_generator")

PROMPT_ID = "rag-structured-prompt-v1"

GENERATION_TEMPERATURE = 0.7
GENERATION_MAX_TOKENS = 800


class GenerationError(RuntimeError):
    """The provider returned no usable content. Carries no provider output."""


INSUFFICIENT_EVIDENCE_REPLY = (
    "Tôi chưa có đủ thông tin trong cẩm nang để trả lời câu hỏi này một cách đáng tin cậy."
)

PROMPT_TEMPLATE = (
    "Bạn là Trợ lý AI Du lịch Việt Nam thông minh, thân thiện và am hiểu địa phương. "
    "Hãy sử dụng thông tin được cung cấp bên dưới để trả lời câu hỏi của người dùng bằng Tiếng Việt. "
    "Nếu có thông tin Cẩm nang Du lịch, hãy trả lời chính xác, hữu ích và tự nhiên; không tự bịa đặt thông tin không có trong cẩm nang. "
    "Nếu có thông tin Sở thích Người dùng, hãy xem đó là ngữ cảnh sở thích mềm (soft preferences) để cá nhân hóa câu trả lời; "
    "yêu cầu cụ thể của người dùng ở lượt hiện tại luôn có mức ưu tiên cao hơn và có thể ghi đè sở thích đã nhớ.\n\n"
    "{context}"
)


class LLMGenerator:
    """Generates the final answer from a GenerationContext via the configured provider."""

    def __init__(self, client: Optional[OpenAI] = None) -> None:
        self._client = client
        self._owned_client: Optional[OpenAI] = None

    def _get_llm_client(self) -> OpenAI:
        """Return the shared provider client, constructing it at most once.

        An injected client belongs to the caller and is never closed here.
        """
        if self._client is not None:
            return self._client
        if self._owned_client is None:
            if not settings.GITHUB_TOKEN:
                logger.warning("GITHUB_TOKEN missing in environment settings.")
                raise ValueError("GITHUB_TOKEN is missing in server environment.")
            self._owned_client = OpenAI(
                base_url=settings.GITHUB_MODELS_URL,
                api_key=settings.GITHUB_TOKEN,
                timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS,
                max_retries=settings.LLM_MAX_RETRIES,
            )
        return self._owned_client

    def close(self) -> None:
        """Release the owned client. Injected clients are the caller's."""
        if self._owned_client is not None:
            self._owned_client.close()
            self._owned_client = None

    def generate(
        self, user_message: str, context: Union[GenerationContext, ContextBundle]
    ) -> GenerationResult:
        """Generate an answer for the user message using the assembled context.

        Args:
            user_message: Raw user query string sent to the provider.
            context: GenerationContext (or legacy ContextBundle for backward compatibility).

        Returns:
            GenerationResult with the reply, the configured model identity, and
            the citations carried through from the context.
        """
        if isinstance(context, ContextBundle):
            if context.insufficient_evidence:
                return GenerationResult(
                    reply=INSUFFICIENT_EVIDENCE_REPLY,
                    model=settings.LLM_MODEL,
                    citations=(),
                )
            gen_context = GenerationContext(
                prompt_context=f"=== CẨM NANG DU LỊCH THAM KHẢO ===\n{context.prompt_context}",
                citations=tuple(
                    GenerationCitation(title=c.title, url=c.url) for c in context.citations
                ),
                sufficiency=ContextSufficiency.SUFFICIENT,
            )
        else:
            gen_context = context

        if gen_context.sufficiency is ContextSufficiency.INSUFFICIENT:
            return GenerationResult(
                reply=INSUFFICIENT_EVIDENCE_REPLY,
                model=settings.LLM_MODEL,
                citations=(),
            )

        if gen_context.prompt_context.strip():
            system_prompt = PROMPT_TEMPLATE.format(context=gen_context.prompt_context.strip())
        else:
            system_prompt = (
                "Bạn là Trợ lý AI Du lịch Việt Nam thông minh, thân thiện và am hiểu địa phương. "
                "Hãy trả lời câu hỏi của người dùng bằng Tiếng Việt một cách chính xác, hữu ích và tự nhiên."
            )

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
        if not isinstance(reply_content, str) or not reply_content.strip():
            raise GenerationError("The provider returned no usable content.")

        return GenerationResult(
            reply=reply_content,
            model=settings.LLM_MODEL,
            citations=gen_context.citations,
        )
