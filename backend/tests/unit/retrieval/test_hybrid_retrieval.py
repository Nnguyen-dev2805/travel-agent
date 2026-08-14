"""Unit tests for Elasticsearch BM25 and hybrid retrieval."""

from backend.rag.retrieval.elasticsearch_bm25 import ElasticsearchBM25Store
from backend.rag.retrieval.hybrid_retriever import HybridRetriever


class FakeIndices:
    def __init__(self):
        self.created = False

    def exists(self, index):
        return self.created

    def create(self, index, **body):
        self.created = True
        self.index = index
        self.body = body


class FakeElasticsearchClient:
    def __init__(self):
        self.indices = FakeIndices()
        self.last_search = None

    def search(self, index, **body):
        self.last_search = {"index": index, "body": body}
        return {
            "hits": {
                "hits": [
                    {
                        "_id": "child_1",
                        "_score": 12.5,
                        "_source": {
                            "chunk_id": "child_1",
                            "title": "Nha Trang rooftop bars",
                            "retrieval_text": "Article: Nha Trang rooftop bars",
                            "source_text": "Skylight is a rooftop bar in Nha Trang.",
                            "url": "https://example.test/nha-trang",
                            "metadata": {"title": "Nha Trang rooftop bars"},
                        },
                    }
                ]
            }
        }


class FakeVectorStore:
    def search_similar(self, query_embedding, top_k=4, where=None):
        return [
            {
                "chunk_id": "dense_only",
                "text": "Semantic result",
                "metadata": {"title": "Semantic"},
                "score": 0.9,
            },
            {
                "chunk_id": "shared",
                "text": "Shared result from dense",
                "metadata": {"title": "Shared"},
                "score": 0.8,
            },
        ][:top_k]


class FakeBM25Store:
    def search(self, query_text, top_k=4):
        return [
            {
                "chunk_id": "shared",
                "text": "Shared result from BM25",
                "metadata": {"title": "Shared"},
                "score": 14.0,
            },
            {
                "chunk_id": "bm25_only",
                "text": "Lexical result",
                "metadata": {"title": "Lexical"},
                "score": 9.0,
            },
        ][:top_k]


def test_build_document_preserves_child_metadata():
    document = ElasticsearchBM25Store.build_document(
        chunk_id="child_1",
        retrieval_text="Article: Da Nang\nLocation: Da Nang",
        metadata={
            "child_id": "child_1",
            "parent_id": "parent_1",
            "title": "Da Nang guide",
            "source_text": "Da Nang has beaches.",
            "locations": "Da Nang",
            "category": "destination",
            "url": "https://example.test/da-nang",
        },
    )

    assert document["child_id"] == "child_1"
    assert document["retrieval_text"] == "Article: Da Nang\nLocation: Da Nang"
    assert document["source_text"] == "Da Nang has beaches."
    assert document["metadata"]["title"] == "Da Nang guide"


def test_elasticsearch_bm25_search_uses_boosted_multi_match():
    client = FakeElasticsearchClient()
    store = ElasticsearchBM25Store(client=client, index_name="travel_test")

    results = store.search("Nha Trang rooftop", top_k=3)

    assert len(results) == 1
    assert results[0]["chunk_id"] == "child_1"
    assert results[0]["text"] == "Skylight is a rooftop bar in Nha Trang."
    assert results[0]["retriever"] == "bm25_elasticsearch"
    assert client.last_search["index"] == "travel_test"
    query = client.last_search["body"]["query"]["bool"]["must"][0]["multi_match"]
    assert query["query"] == "Nha Trang rooftop"
    assert "title^4" in query["fields"]
    assert "retrieval_text" in query["fields"]
    assert client.last_search["body"]["size"] == 3


def test_hybrid_retriever_fuses_dense_and_bm25_with_rrf():
    retriever = HybridRetriever(
        vector_store=FakeVectorStore(),
        bm25_store=FakeBM25Store(),
        candidate_k=10,
        rrf_k=60,
        dense_weight=0.65,
        bm25_weight=0.35,
    )

    results = retriever.search("rooftop bar", [0.1, 0.2], top_k=3)

    assert [item["chunk_id"] for item in results] == ["shared", "dense_only", "bm25_only"]
    assert results[0]["retriever"] == "hybrid_bm25_dense_rrf"
    assert results[0]["dense_rank"] == 2
    assert results[0]["bm25_rank"] == 1
    assert results[0]["text"] == "Shared result from dense"
