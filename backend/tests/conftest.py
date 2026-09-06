"""Pytest shared fixtures configuration file for unit and integration tests."""

# pyrefly: ignore [missing-import]
import pytest
from pathlib import Path
from typing import Any, Dict
from fastapi.testclient import TestClient

from backend.app.main import app

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def _compat_auth_by_default(monkeypatch):
    """Pin compatibility mode unless a test explicitly opts into auth.

    R9 route authorization reads the global auth gate. Without this pin,
    an ambient `AUTH_REQUIRED=true` would change legacy expectations that
    were written before the gate existed. Auth tests override the flag in
    their own bodies, which apply after this fixture.
    """
    from backend.app.config import settings

    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)


@pytest.fixture
def api_client() -> TestClient:
    """Provide a reusable FastAPI TestClient instance."""
    return TestClient(app)


@pytest.fixture
def sample_travel_document() -> Dict[str, Any]:
    """Provide a standard sample travel document for chunking and indexing tests."""
    return {
        "document_id": "test_doc_ha_long_01",
        "title": "Kinh nghiệm du lịch Vịnh Hạ Long",
        "url": "https://vietnam.travel/ha-long",
        "text": (
            "# Khám phá Vịnh Hạ Long\n\n"
            "Vịnh Hạ Long là di sản thiên nhiên thế giới nổi tiếng với hàng ngàn hòn đảo đá vôi.\n\n"
            "## Thời điểm du lịch lý tưởng\n"
            "Thời điểm tuyệt vời nhất để ghé thăm Vịnh Hạ Long là vào mùa thu từ tháng 9 đến tháng 11.\n\n"
            "## Trải nghiệm không thể bỏ qua\n"
            "Du khách có thể trải nghiệm chèo thuyền kayak, ngắm hoàng hôn trên du thuyền năm sao."
        ),
    }
