"""Sync Chroma child chunks into Elasticsearch for BM25 retrieval."""

from __future__ import annotations

import argparse
import logging

from backend.app.config import settings
from backend.rag.retrieval import ChromaVectorStore, ElasticsearchBM25Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("travel_agent_index_elasticsearch")


def sync_elasticsearch_index(
    collection_name: str | None = None,
    index_name: str | None = None,
    recreate: bool = False,
    batch_size: int = 500,
) -> int:
    """Copy existing Chroma documents into Elasticsearch."""
    vector_store = ChromaVectorStore(collection_name=collection_name or settings.RAG_COLLECTION_NAME)
    bm25_store = ElasticsearchBM25Store(
        url=settings.ELASTICSEARCH_URL,
        index_name=index_name or settings.ELASTICSEARCH_INDEX,
        username=settings.ELASTICSEARCH_USERNAME,
        password=settings.ELASTICSEARCH_PASSWORD,
        api_key=settings.ELASTICSEARCH_API_KEY,
        verify_certs=settings.ELASTICSEARCH_VERIFY_CERTS,
        request_timeout=settings.ELASTICSEARCH_REQUEST_TIMEOUT,
    )
    return bm25_store.index_from_chroma(
        vector_store=vector_store,
        batch_size=batch_size,
        recreate=recreate,
        refresh=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index Chroma chunks into Elasticsearch for BM25 search.")
    parser.add_argument("--collection", default=settings.RAG_COLLECTION_NAME, help="Chroma collection name.")
    parser.add_argument("--index", default=settings.ELASTICSEARCH_INDEX, help="Elasticsearch index name.")
    parser.add_argument("--batch-size", type=int, default=500, help="Bulk indexing batch size.")
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate the ES index first.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    count = sync_elasticsearch_index(
        collection_name=args.collection,
        index_name=args.index,
        recreate=args.recreate,
        batch_size=args.batch_size,
    )
    logger.info("Elasticsearch BM25 indexing complete. Indexed %s documents.", count)
