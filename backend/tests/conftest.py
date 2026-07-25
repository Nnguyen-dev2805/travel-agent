"""Pytest shared fixtures configuration file for unit and integration tests."""

# pyrefly: ignore [missing-import]
import pytest
from pathlib import Path
from typing import Any, Dict
from fastapi.testclient import TestClient

from backend.app.main import app

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


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
