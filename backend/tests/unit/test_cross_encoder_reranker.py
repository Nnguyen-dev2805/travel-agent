"""Unit tests for TEI cross-encoder reranking."""

import httpx

from backend.rag.reranking import TEICrossEncoderReranker


def test_tei_cross_encoder_reranker_sorts_by_returned_rank():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read().decode("utf-8")
        assert "Nha Trang rooftop" in payload
        assert "Skylight is a rooftop bar" in payload
        return httpx.Response(
            200,
            json=[
                {"index": 1, "score": 0.92},
                {"index": 0, "score": 0.41},
            ],
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    reranker = TEICrossEncoderReranker(
        rerank_url="http://tei.test/rerank",
        client=client,
        max_text_chars=2000,
    )
    results = [
        {
            "chunk_id": "chunk_a",
            "text": "A generic travel chunk.",
            "metadata": {"title": "Generic"},
            "score": 0.7,
            "retriever": "hybrid_bm25_dense_rrf",
        },
        {
            "chunk_id": "chunk_b",
            "text": "Skylight is a rooftop bar in Nha Trang.",
            "metadata": {"title": "Nha Trang rooftop bars"},
            "score": 0.6,
            "retriever": "hybrid_bm25_dense_rrf",
        },
    ]

    reranked = reranker.rerank("Nha Trang rooftop", results, top_k=2)

    assert [item["chunk_id"] for item in reranked] == ["chunk_b", "chunk_a"]
    assert reranked[0]["rerank_score"] == 0.92
    assert reranked[0]["pre_rerank_score"] == 0.6
    assert reranked[0]["pre_rerank_retriever"] == "hybrid_bm25_dense_rrf"
    assert reranked[0]["reranker"] == "tei_cross_encoder"
