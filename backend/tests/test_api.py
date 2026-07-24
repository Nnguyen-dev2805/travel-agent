import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health_check_endpoint():
    """Test health check API returns status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "Vietnam Travel Agent API"

def test_chat_empty_message():
    """Test chat endpoint returns 400 when message is empty."""
    response = client.post("/api/v1/chat", json={"message": "   "})
    assert response.status_code == 400
    assert "cannot be empty" in response.json()["detail"]
