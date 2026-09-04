"""Unit tests for LLMGenerator prompt template, provider call, and fallback contract."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

# pyrefly: ignore [missing-import]
import pytest

from backend.app.config import settings
from backend.rag.contracts import CitationEvidence, ContextBundle, RetrievalResult
from backend.rag.generation import llm as llm_module
from backend.rag.generation.llm import LLMGenerator

FAKE_REPLY = "Câu trả lời giả lập từ mô hình."

INSUFFICIENT_REPLY = (
    "Tôi chưa có đủ thông tin trong cẩm nang để trả lời câu hỏi này một cách đáng tin cậy."
)

# Exact legacy system-prompt wording, byte-verified against legacy
# rag_service.py during characterization (context header uses U+1EA8).
LEGACY_PROMPT_PREFIX = (
    "Bạn là Trợ lý AI Du lịch Việt Nam thông minh, thân thiện và am hiểu địa phương. "
    "Hãy sử dụng thông tin Cẩm nang Du lịch được cung cấp bên dưới để trả lời câu hỏi của người dùng bằng Tiếng Việt. "
    "Nếu thông tin được cung cấp có chứa câu trả lời, hãy trả lời chính xác, hữu ích và tự nhiên. "
    "Không tự bịa đặt thông tin không có trong cẩm nang.\n\n"
)

LEGACY_CONTEXT_HEADER = "=== CẨM NANG DU LỊCH THAM KHẢO ===\n"


class FakeChatCompletions:
    """Captures chat.completions.create kwargs and returns a fixed completion."""

    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.create_calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=FAKE_REPLY))]
        )


class FakeChat:
    def __init__(self) -> None:
        self.completions = FakeChatCompletions()


class FakeLLMClient:
    """Fake OpenAI-compatible client exposing client.chat.completions.create."""

    def __init__(self) -> None:
        self.chat = FakeChat()


def _evidence(chunk_id: str, title: str, url: str, text: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        title=title,
        url=url,
        score=0.9,
        text=text,
    )


def _insufficient_bundle() -> ContextBundle:
    return ContextBundle(
        prompt_context="Không tìm thấy tài liệu liên quan.",
        evidence=(),
        citations=(),
        insufficient_evidence=True,
    )


def _non_empty_bundle() -> ContextBundle:
    evidence = (
        _evidence("c1", "T1", "https://u1", "text1"),
        _evidence("c2", "T2", "https://u2", "text2"),
    )
    return ContextBundle(
        prompt_context="[Nguồn 1: T1]\ntext1\n\n---\n\n[Nguồn 2: T2]\ntext2",
        evidence=evidence,
        citations=(
            CitationEvidence(
                title="T1", url="https://u1", evidence_ids=("c1",)
            ),
            CitationEvidence(
                title="T2", url="https://u2", evidence_ids=("c2",)
            ),
        ),
        insufficient_evidence=False,
    )


def test_insufficient_evidence_returns_fixed_answer_without_provider_call():
    """The zero-evidence path never touches the provider and returns the fixed reply."""
    generator = LLMGenerator(client=FakeLLMClient())

    answer = generator.generate("câu hỏi", _insufficient_bundle())

    assert answer.reply == INSUFFICIENT_REPLY
    assert answer.model == settings.LLM_MODEL
    assert answer.citations == ()


def test_non_empty_bundle_sends_exact_legacy_prompt_and_provider_kwargs():
    """System message is the legacy prompt verbatim plus the bundle context."""
    client = FakeLLMClient()
    generator = LLMGenerator(client=client)

    expected_system = (
        LEGACY_PROMPT_PREFIX
        + LEGACY_CONTEXT_HEADER
        + "[Nguồn 1: T1]\ntext1\n\n---\n\n[Nguồn 2: T2]\ntext2"
    )

    generator.generate("Hà Nội có gì đẹp?", _non_empty_bundle())

    create_kwargs = client.chat.completions.create_calls[0]
    assert create_kwargs["messages"] == [
        {"role": "system", "content": expected_system},
        {"role": "user", "content": "Hà Nội có gì đẹp?"},
    ]
    assert create_kwargs["temperature"] == 0.7
    assert create_kwargs["max_tokens"] == 800
    assert create_kwargs["model"] == settings.LLM_MODEL


def test_reply_from_provider_and_citations_carried_through():
    """Reply is the provider content; citations are the bundle citations unchanged."""
    client = FakeLLMClient()
    generator = LLMGenerator(client=client)
    bundle = _non_empty_bundle()

    answer = generator.generate("câu hỏi", bundle)

    assert answer.reply == FAKE_REPLY
    assert answer.model == settings.LLM_MODEL
    assert answer.citations == bundle.citations
    assert answer.citations == (
        CitationEvidence(title="T1", url="https://u1", evidence_ids=("c1",)),
        CitationEvidence(title="T2", url="https://u2", evidence_ids=("c2",)),
    )


def test_injected_client_used_and_no_real_client_constructed(monkeypatch):
    """The injected client is used on both paths and OpenAI is never constructed."""

    def fail_openai(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("OpenAI client must not be constructed in tests.")

    monkeypatch.setattr(llm_module, "OpenAI", fail_openai)

    client = FakeLLMClient()
    generator = LLMGenerator(client=client)

    generator.generate("câu hỏi", _non_empty_bundle())
    assert len(client.chat.completions.create_calls) == 1

    generator.generate("câu hỏi", _insufficient_bundle())
    assert len(client.chat.completions.create_calls) == 1
