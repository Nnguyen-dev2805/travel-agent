"""Unit tests for the RAGService facade orchestrating retrieval, context, and generation."""

from __future__ import annotations

from typing import Any

# pyrefly: ignore [missing-import]
import pytest

from backend.generation.contracts import (
    ContextSufficiency,
    GenerationCitation,
    GenerationResult,
)
from backend.rag.contracts import RetrievalResult
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
        self.answers: list[GenerationResult] = []

    def generate(self, user_message: str, context: Any) -> GenerationResult:
        self.calls.append((user_message, context))
        citations = tuple(
            GenerationCitation(title=c.title, url=c.url)
            for c in getattr(context, "citations", ())
        )
        answer = GenerationResult(
            reply=FAKE_REPLY,
            model="fake-model",
            citations=citations,
        )
        self.answers.append(answer)
        return answer


def _make_service(
    results: list[RetrievalResult] | None = None,
) -> tuple[RAGService, FakeRetriever, ContextAssembler, FakeGenerator]:
    retriever = FakeRetriever(results=results)
    assembler = ContextAssembler()
    generator = FakeGenerator()
    service = RAGService(
        retriever=retriever,
        context_assembler=assembler,
        generator=generator,
    )
    return service, retriever, assembler, generator


def test_empty_user_message_raises_value_error():
    service, _, _, _ = _make_service()
    with pytest.raises(ValueError, match="User message content cannot be empty"):
        service.generate_answer("")
    with pytest.raises(ValueError, match="User message content cannot be empty"):
        service.generate_answer("   \n\t  ")


def test_custom_top_k_overrides_constructor_default():
    service, retriever, _, _ = _make_service(results=[])
    service.generate_answer("Đà Nẵng", top_k=7)
    assert retriever.calls == [("Đà Nẵng", 7)]


def test_constructor_top_k_used_when_call_site_omits_it():
    retriever = FakeRetriever(results=[])
    service = RAGService(retriever=retriever, top_k=5)
    service.generate_answer("Huế")
    assert retriever.calls == [("Huế", 5)]


def test_build_travel_context_exposes_r6_orchestration_seam():
    results = [_result("c1", "T1", "https://u1", "text1")]
    service, retriever, assembler, _ = _make_service(results=results)

    bundle = service.build_travel_context("Hà Nội", top_k=3)

    assert retriever.calls == [("Hà Nội", 3)]
    assert bundle == assembler.assemble(results)
    assert bundle.insufficient_evidence is False


def test_generate_from_context_returns_generation_result():
    results = [_result("c1", "T1", "https://u1", "text1")]
    service, _, _, generator = _make_service(results=results)
    bundle = service.build_travel_context("Hà Nội")

    result = service.generate_from_context("Hà Nội", bundle)

    assert isinstance(result, GenerationResult)
    assert result.reply == FAKE_REPLY
    assert result.model == "fake-model"
    assert len(result.citations) == 1
    assert result.citations[0].title == "T1"


def test_generator_receives_real_assembler_bundle():
    """The generator gets the neutral GenerationContext projected from ContextAssembler."""
    results = [
        _result("c1", "T1", "https://u1", "text1"),
        _result("c2", "T2", "https://u2", "text2"),
    ]
    service, retriever, _, generator = _make_service(results=results)

    bundle = service.build_travel_context("Hà Nội?")
    assert bundle.insufficient_evidence is False
    assert bundle.evidence == tuple(results)
    assert bundle.prompt_context == "[Nguồn 1: T1]\ntext1\n\n---\n\n[Nguồn 2: T2]\ntext2"
    assert bundle == ContextAssembler().assemble(results)

    service.generate_answer("Hà Nội?")
    user_message, gen_context = generator.calls[0]
    assert user_message == "Hà Nội?"
    assert gen_context.sufficiency is ContextSufficiency.SUFFICIENT
    assert "[Nguồn 1: T1]\ntext1" in gen_context.prompt_context


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
