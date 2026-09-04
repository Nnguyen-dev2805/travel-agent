"""Unit tests for the RAGService facade orchestrating retrieval, context, and generation."""

from __future__ import annotations

from typing import Any

# pyrefly: ignore [missing-import]
import pytest

from backend.rag.contracts import GeneratedAnswer, RetrievalResult
from backend.rag.generation import rag_service as rag_service_module
from backend.rag.generation.context import ContextAssembler
from backend.rag.generation.rag_service import RAGService

FAKE_REPLY = "Câu trả lời giả lập từ generator."
DEFAULT_COLLECTION_NAME = "vietnam_travel_parent_child"


def _result(
    chunk_id: str, title: str, url: str, text: str, score: float | None = 0.9
) -> RetrievalResult:
    """Build one RetrievalResult fixture directly from the runtime contract."""
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        title=title,
        url=url,
        score=score,
        text=text,
    )


class FakeRetriever:
    """Records retrieve calls and returns canned structured results."""

    def __init__(self, results: list[RetrievalResult] | None = None) -> None:
        self.results = list(results) if results is not None else []
        self.calls: list[tuple[str, int | None]] = []

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        self.calls.append((query, top_k))
        return list(self.results)


class FakeGenerator:
    """Records generate calls and returns a canned answer carrying bundle citations."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.answers: list[GeneratedAnswer] = []

    def generate(self, user_message: str, context: Any) -> GeneratedAnswer:
        self.calls.append((user_message, context))
        answer = GeneratedAnswer(
            reply=FAKE_REPLY,
            model="fake-model",
            citations=context.citations,
        )
        self.answers.append(answer)
        return answer


def _make_service(
    results: list[RetrievalResult] | None = None,
) -> tuple[RAGService, FakeRetriever, ContextAssembler, FakeGenerator]:
    """Build the facade with injected fakes and the real context assembler."""
    retriever = FakeRetriever(results=results)
    assembler = ContextAssembler()
    generator = FakeGenerator()
    service = RAGService(
        retriever=retriever, context_assembler=assembler, generator=generator
    )
    return service, retriever, assembler, generator


def test_empty_message_raises_value_error_without_touching_dependencies():
    """Empty/whitespace input fails fast before retriever or generator use."""
    service, retriever, _, generator = _make_service(
        results=[_result("c1", "T1", "https://u1", "text1")]
    )

    for bad_message in ("", "   ", "\n\t  "):
        with pytest.raises(ValueError, match="cannot be empty") as excinfo:
            service.generate_answer(bad_message)
        assert str(excinfo.value) == "User message content cannot be empty."

    assert retriever.calls == []
    assert generator.calls == []


def test_query_stripped_and_default_top_k_passed_to_retriever():
    """The stripped query goes to the retriever with the default top_k of 4."""
    service, retriever, _, generator = _make_service(
        results=[_result("c1", "T1", "https://u1", "text1")]
    )

    service.generate_answer("  Hà Nội?  ")

    assert retriever.calls == [("Hà Nội?", 4)]
    assert generator.calls[0][0] == "Hà Nội?"


def test_explicit_top_k_overrides_default():
    """An explicit top_k argument is forwarded to the retriever unchanged."""
    service, retriever, _, _ = _make_service(results=[])

    service.generate_answer("Hà Nội?", top_k=7)

    assert retriever.calls == [("Hà Nội?", 7)]


def test_generator_receives_real_assembler_bundle():
    """The generator gets the real ContextAssembler output for the retriever results."""
    results = [
        _result("c1", "T1", "https://u1", "text1"),
        _result("c2", "T2", "https://u2", "text2"),
    ]
    service, retriever, _, generator = _make_service(results=results)

    service.generate_answer("Hà Nội?")

    user_message, bundle = generator.calls[0]
    assert user_message == "Hà Nội?"
    assert bundle.insufficient_evidence is False
    assert bundle.evidence == tuple(results)
    assert bundle.prompt_context == "[Nguồn 1: T1]\ntext1\n\n---\n\n[Nguồn 2: T2]\ntext2"
    assert bundle == ContextAssembler().assemble(results)


def test_public_result_shape_and_citation_projection():
    """Public dict projects only reply/model/citations with title+url pairs."""
    results = [
        _result("c1", "T1", "https://u1", "text1"),
        _result("c2", "T2", "https://u2", "text2"),
        _result("c3", "T1", "https://u1-later", "text3"),
        _result("c4", "T4", "", "text4"),
    ]
    service, retriever, _, generator = _make_service(results=results)

    result = service.generate_answer("Hà Nội?")

    generated = generator.answers[0]
    assert set(result.keys()) == {"reply", "model", "citations"}
    assert result == {
        "reply": generated.reply,
        "model": generated.model,
        "citations": [
            {"title": citation.title, "url": citation.url}
            for citation in generated.citations
        ],
    }
    assert result["citations"] == [
        {"title": "T1", "url": "https://u1-later"},
        {"title": "T2", "url": "https://u2"},
    ]
    # No evidence ids, chunk ids, or scores leak into the public dict.
    for citation in result["citations"]:
        assert set(citation.keys()) == {"title", "url"}
    assert result["model"] == "fake-model"
    assert result["reply"] == FAKE_REPLY


def test_default_construction_uses_module_level_defaults(monkeypatch):
    """RAGService() builds and wires the module-level defaults without real embedders."""
    sentinel_retriever = FakeRetriever(
        results=[_result("c1", "T1", "https://u1", "text1")]
    )
    sentinel_assembler = ContextAssembler()
    sentinel_generator = FakeGenerator()
    retriever_kwargs: list[dict] = []
    assembler_kwargs: list[dict] = []
    generator_kwargs: list[dict] = []

    def fake_retriever_factory(*args, **kwargs):
        retriever_kwargs.append(kwargs)
        return sentinel_retriever

    def fake_assembler_factory(*args, **kwargs):
        assembler_kwargs.append(kwargs)
        return sentinel_assembler

    def fake_generator_factory(*args, **kwargs):
        generator_kwargs.append(kwargs)
        return sentinel_generator

    monkeypatch.setattr(rag_service_module, "KnowledgeRetriever", fake_retriever_factory)
    monkeypatch.setattr(rag_service_module, "ContextAssembler", fake_assembler_factory)
    monkeypatch.setattr(rag_service_module, "LLMGenerator", fake_generator_factory)

    service = RAGService()

    assert service.retriever is sentinel_retriever
    assert service.context_assembler is sentinel_assembler
    assert service.generator is sentinel_generator
    assert retriever_kwargs == [
        {"top_k": 4, "collection_name": DEFAULT_COLLECTION_NAME}
    ]
    assert assembler_kwargs == [{}]
    assert generator_kwargs == [{}]

    service.generate_answer("Hà Nội?")
    assert sentinel_retriever.calls == [("Hà Nội?", 4)]
    assert len(sentinel_generator.calls) == 1
