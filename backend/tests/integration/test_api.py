"""Integration tests for general API endpoints."""

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
