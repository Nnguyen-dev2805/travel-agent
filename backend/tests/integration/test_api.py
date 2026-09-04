# pyrefly: ignore [missing-import]
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

def test_health_check_endpoint(api_client):
    """Test health check API returns status ok."""
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "Vietnam Travel Agent API"

def test_chat_empty_message(api_client):
    """Test chat endpoint returns 400 when message is empty."""
    response = api_client.post("/api/v1/chat", json={"message": "   "})
    assert response.status_code == 400
    assert "cannot be empty" in response.json()["detail"]


class FakeChatRAGService:
    """Stub RAGService facade returning a canned projected response dict."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.response = {
            "reply": "Câu trả lời giả lập từ RAG service.",
            "model": "gpt-4o-mini",
            "citations": [
                {"title": "Hà Nội", "url": "https://vietnam.travel/ha-noi"},
                {"title": "Hạ Long", "url": "https://vietnam.travel/ha-long"},
            ],
        }

    def generate_answer(self, user_message: str, top_k: int = 4) -> dict:
        self.calls.append((user_message, top_k))
        return self.response


def test_chat_returns_reply_model_citations_with_stubbed_rag_service(monkeypatch, api_client):
    """Chat returns exactly reply/model/citations from the stubbed RAG facade."""
    fake_service = FakeChatRAGService()
    monkeypatch.setattr(
        "backend.app.api.chat.get_rag_service", lambda: fake_service
    )

    response = api_client.post("/api/v1/chat", json={"message": "  Hà Nội có gì đẹp?  "})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"reply", "model", "citations"}
    assert body["reply"] == fake_service.response["reply"]
    assert body["model"] == fake_service.response["model"]
    assert body["citations"] == fake_service.response["citations"]
    for citation in body["citations"]:
        assert set(citation.keys()) == {"title", "url"}
    # The route strips the message and forwards the default top_k=4.
    assert fake_service.calls == [("Hà Nội có gì đẹp?", 4)]


def test_chat_empty_message_rejected_before_stubbed_service(monkeypatch, api_client):
    """Empty messages still return 400 without reaching the stubbed RAG service."""
    fake_service = FakeChatRAGService()
    monkeypatch.setattr(
        "backend.app.api.chat.get_rag_service", lambda: fake_service
    )

    response = api_client.post("/api/v1/chat", json={"message": "   "})

    assert response.status_code == 400
    assert "cannot be empty" in response.json()["detail"]
    assert fake_service.calls == []
