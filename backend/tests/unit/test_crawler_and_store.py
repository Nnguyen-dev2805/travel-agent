"""Unit tests for crawler stub fail-fast and read-only vector store.

The fetcher submodules are not vendored, so crawling must fail loudly
instead of reporting zeroed success. Retrieval must open the store
read-only so chat and evaluation never materialize empty indexes.
"""

import pytest

from backend.preprocessing import crawler as crawler_module
from backend.preprocessing.crawler import VietnamTravelCrawler


def test_crawler_reports_stub_status():
    assert crawler_module._HAVE_FETCHER is False


def test_crawler_run_fails_fast_without_fetcher():
    with pytest.raises(RuntimeError, match="not vendored"):
        VietnamTravelCrawler(config=None).run()


def test_crawler_discover_fails_fast_without_fetcher():
    with pytest.raises(RuntimeError, match="not vendored"):
        VietnamTravelCrawler(config=None).discover_urls()


def test_read_only_store_creates_nothing(tmp_path):
    """Opening a missing store read-only raises instead of creating state."""
    from backend.rag.retrieval.vector_store import ChromaVectorStore

    missing = tmp_path / "no-store-here"
    with pytest.raises(Exception):
        ChromaVectorStore(
            persist_directory=missing,
            collection_name="vietnam_travel_parent_child",
            read_only=True,
        )
    assert not missing.exists()


def test_writable_store_keeps_legacy_create_behavior(tmp_path):
    """Default mode still materializes the store for indexing flows."""
    from backend.rag.retrieval.vector_store import ChromaVectorStore

    target = tmp_path / "fresh-store"
    store = ChromaVectorStore(
        persist_directory=target,
        collection_name="test_collection",
    )
    assert target.exists()
    assert store.collection.count() == 0
