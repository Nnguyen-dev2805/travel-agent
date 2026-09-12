"""Pytest shared fixtures configuration file for unit and integration tests."""

import os

# --- pin the suite offline, before anything can import HuggingFace -------------
#
# `huggingface_hub.constants` reads these at *import* time, so this has to run
# before the first import that reaches `sentence_transformers` — which the
# `backend.app.main` import below does. Setting them further down, or in a fixture,
# would be too late.
#
# Why it matters: `VectorEmbedder.model` calls `SentenceTransformer(model_name)`,
# and the hub checks remote metadata even when the weights are already cached.
# Measured on this repository: the embedder test took 11.89s with the network
# reachable and 5.83s with `HF_HUB_OFFLINE=1`. Where outbound traffic to
# huggingface.co is blocked rather than merely slow, that check does not fail — it
# hangs, and the whole suite hangs with it.
#
# `setdefault`, not assignment: a developer who deliberately wants the hub can pass
# `HF_HUB_OFFLINE=0`, which is falsy to the hub's own parser.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

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
