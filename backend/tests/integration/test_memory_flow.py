"""Integration tests for End-to-End Chat API, Memory Routing, and Memory Management Endpoints."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker
# pyrefly: ignore [missing-import]
from sqlalchemy.pool import StaticPool

from backend.app.main import app
from backend.app.database import Base, get_db
from backend.app.models import User, UserMemory, ChatMessage, ChatSession


@pytest.fixture
def client_and_db():
    """Create a multithread-safe SQLite in-memory DB and FastAPI TestClient."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client, TestingSessionLocal()

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@patch("backend.app.api.chat.get_rag_service")
@patch("backend.memory.fact_memory.FactMemoryService.extract_facts")
def test_guest_chat_flow_and_history(mock_extract_facts, mock_get_rag, client_and_db):
    """Test End-to-End Chat flow for Guest User (No Auth Token)."""
    client, db = client_and_db

    # Mock RAG Service answer generation
    mock_rag = MagicMock()
    mock_rag.generate_answer.return_value = {
        "reply": "Hà Nội có 36 phố phường và Hồ Hoàn Kiếm.",
        "model": "gpt-4o-mini",
        "citations": [{"title": "Cẩm nang Hà Nội", "url": "https://vietnam.travel/hanoi"}],
    }
    mock_get_rag.return_value = mock_rag

    # 1. Guest sends chat message (No Authorization Header)
    req_payload = {"message": "Hà Nội có gì đẹp?"}
    chat_resp = client.post("/api/v1/chat", json=req_payload)

    assert chat_resp.status_code == 200, chat_resp.text
    body = chat_resp.json()

    assert body["reply"] == "Hà Nội có 36 phố phường và Hồ Hoàn Kiếm."
    assert "session_id" in body
    session_id = body["session_id"]

    # 2. Query history for session_id via GET /api/v1/memory/history/{session_id}
    hist_resp = client.get(f"/api/v1/memory/history/{session_id}")
    assert hist_resp.status_code == 200
    history = hist_resp.json()

    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Hà Nội có gì đẹp?"}
    assert history[1] == {"role": "assistant", "content": "Hà Nội có 36 phố phường và Hồ Hoàn Kiếm."}

    # 3. Guest tries to access long-term facts -> 401 Unauthorized
    facts_resp = client.get("/api/v1/memory/facts")
    assert facts_resp.status_code == 401


@patch("backend.app.api.chat.get_rag_service")
@patch("backend.memory.fact_memory.FactMemoryService.extract_facts")
@patch("backend.memory.fact_memory.FactMemoryService.retrieve_relevant_facts")
def test_authenticated_user_chat_flow_and_fact_management(mock_retrieve, mock_extract_facts, mock_get_rag, client_and_db):
    """Test End-to-End Chat flow for Authenticated User and Memory Fact endpoints."""
    client, db = client_and_db

    # Mock RAG Service
    mock_rag = MagicMock()
    mock_rag.generate_answer.return_value = {
        "reply": "Đà Nẵng có bãi biển Mỹ Khê và Cầu Vàng.",
        "model": "gpt-4o-mini",
        "citations": [],
    }
    mock_get_rag.return_value = mock_rag

    # 1. Register & Login
    client.post(
        "/api/v1/auth/register",
        json={"email": "memoryuser@travel.vn", "password": "password123", "full_name": "Traveler A"},
    )
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "memoryuser@travel.vn", "password": "password123"},
    )
    token = login_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 2. Add a fact directly to DB for this user
    user_in_db = db.query(User).filter_by(email="memoryuser@travel.vn").first()
    mem = UserMemory(
        user_id=user_in_db.id,
        fact_type="dietary",
        fact_key="allergy",
        content="Dị ứng hải sản",
        status="active"
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)

    # 3. Authenticated Chat request
    chat_resp = client.post(
        "/api/v1/chat",
        json={"message": "Gợi ý điểm du lịch"},
        headers=auth_headers,
    )
    assert chat_resp.status_code == 200
    session_id = chat_resp.json()["session_id"]

    # 4. Fetch user facts via GET /api/v1/memory/facts
    facts_resp = client.get("/api/v1/memory/facts", headers=auth_headers)
    assert facts_resp.status_code == 200
    facts_list = facts_resp.json()
    assert len(facts_list) == 1
    assert facts_list[0]["content"] == "Dị ứng hải sản"

    # 5. Fetch user sessions via GET /api/v1/memory/sessions
    sessions_resp = client.get("/api/v1/memory/sessions", headers=auth_headers)
    assert sessions_resp.status_code == 200
    sessions_list = sessions_resp.json()
    assert len(sessions_list) == 1
    assert sessions_list[0]["id"] == session_id
    assert sessions_list[0]["title"] is not None

    # 6. Delete fact via DELETE /api/v1/memory/facts/{fact_id}
    del_resp = client.delete(f"/api/v1/memory/facts/{mem.id}", headers=auth_headers)
    assert del_resp.status_code == 204  # 204 No Content

    # Verify fact deleted
    facts_after = client.get("/api/v1/memory/facts", headers=auth_headers).json()
    assert len(facts_after) == 0
