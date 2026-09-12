"""The application's startup path: what it warms, and what it is allowed to log.

Two defects lived here, and they are different in kind.

**The pre-warm did not warm.** `container.rag_service()` constructs the object
graph, and `VectorEmbedder.model` is a lazy property — so the embedding weights were
never loaded, the "successfully pre-warmed" line was untrue, and the first real user
query paid for a multi-gigabyte checkpoint.

**The failure log carried raw exception text.** It was the one startup log in the
repository that did, while everything else reports a `failure_class`. An exception
raised by an SDK or a provider can hold an endpoint, a path or a response body, and
this one is emitted at the moment credentials are most likely to be in play.

Both are asserted against the real lifespan, with the container replaced: the
startup path is what is under test, not the database behind it.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from backend.app import main


class _StubService:
    def __init__(self, container: "_StubContainer") -> None:
        self._container = container

    def warm(self) -> None:
        self._container.warm_calls += 1
        if self._container.warm_error is not None:
            raise self._container.warm_error


class _StubContainer:
    """A composed container whose RAG service is observable and can fail."""

    def __init__(self, warm_error: BaseException | None = None) -> None:
        self.warm_error = warm_error
        self.warm_calls = 0

    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    def rag_service(self) -> _StubService:
        return _StubService(self)


def _run_lifespan() -> None:
    async def _run() -> None:
        async with main.lifespan(main.app):
            pass

    asyncio.run(_run())


def _install(monkeypatch, container: _StubContainer) -> _StubContainer:
    monkeypatch.setattr(main, "RuntimeContainer", lambda *_a, **_k: container)
    return container


SENTINEL = "https://internal.example.test/v1?api_key=SECRET-SENTINEL"


def test_the_lifespan_actually_warms_the_embedding_model(monkeypatch):
    """Constructing the object graph is not warming it.

    `VectorEmbedder.model` loads on first access, so `rag_service()` alone left the
    weights unloaded. Without this call the startup line claims something that is
    not true, and the cost moves to the first user query.
    """
    container = _install(monkeypatch, _StubContainer())

    _run_lifespan()

    assert container.warm_calls == 1, "the lifespan must load the model, not just build it"


def test_a_prewarm_failure_logs_a_class_and_never_the_message(monkeypatch, caplog):
    """A pre-warm failure must not print what the exception said.

    The exception comes from a model SDK or a provider client, and its message can
    carry an endpoint, a path, or a response body. Every other startup and request
    log in this repository reports `failure_class`; this one did not.
    """
    container = _install(monkeypatch, _StubContainer(warm_error=RuntimeError(SENTINEL)))

    with caplog.at_level(logging.WARNING, logger="travel_agent_main"):
        _run_lifespan()

    assert "failure_class=RuntimeError" in caplog.text, (
        "the class is what an operator needs, and it is content-free"
    )
    assert SENTINEL not in caplog.text, (
        "a provider exception can carry an endpoint or a response body"
    )
    assert container.warm_calls == 1, "the failure came from the warm call itself"


def test_a_prewarm_failure_does_not_stop_startup(monkeypatch, caplog):
    """A pre-warm is best-effort: a model that cannot load must not refuse to serve.

    The chat surface can still answer from what it has, and failing startup here
    would turn a cold cache into an outage.
    """
    _install(monkeypatch, _StubContainer(warm_error=RuntimeError("cold cache")))

    with caplog.at_level(logging.WARNING, logger="travel_agent_main"):
        _run_lifespan()  # must not raise

    assert "rag.prewarm failed" in caplog.text


def test_the_rag_service_warm_delegates_to_the_embedder():
    """`RAGService.warm` exists so the caller does not reach two levels deep.

    Reaching through `retriever.embedder` from the lifespan would make the startup
    path depend on the retriever's internal shape.
    """
    from backend.rag.generation.rag_service import RAGService

    class _Embedder:
        def __init__(self) -> None:
            self.warm_calls = 0

        def warm(self) -> None:
            self.warm_calls += 1

    class _Retriever:
        def __init__(self, embedder) -> None:
            self.embedder = embedder

    embedder = _Embedder()
    service = RAGService(retriever=_Retriever(embedder))

    service.warm()

    assert embedder.warm_calls == 1


def test_the_embedder_warm_forces_the_lazy_load():
    """`warm()` must be the property access, not a second copy of the loader."""
    import inspect

    from backend.rag.embedding.embedder import VectorEmbedder

    source = inspect.getsource(VectorEmbedder.warm)

    assert "self.model" in source, (
        "warm() must go through the same lazy property the request path uses"
    )
    assert "SentenceTransformer" not in source, (
        "a second construction site would load the model twice"
    )
