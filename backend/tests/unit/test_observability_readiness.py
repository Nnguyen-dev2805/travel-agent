"""Unit tests for the clean-break read-only readiness service and ops route.

Tests verify:
- Readiness when PostgreSQL is healthy & Alembic is at head -> READY (200).
- Readiness when PostgreSQL is unavailable -> NOT_READY (503).
- Readiness when Alembic revision is behind -> NOT_READY (503).
- Responses leak no raw DSNs or secrets.
- Component probes never create state as a side effect.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.api.ops import get_readiness
from backend.app.config import settings
from backend.app.main import app
from backend.app.runtime_container import (
    PostgresReadinessProbe,
    RuntimeContainer,
    get_runtime_container,
)
from backend.observability.models import ReadinessStatus
from backend.observability.readiness import (
    EXPECTED_ALEMBIC_HEAD,
    build_readiness_snapshot,
)

AUTH_TOKEN = "readiness-test-token"
REGISTRY = '{"ops_tester": "readiness-test-token"}'


@pytest.fixture(autouse=True)
def _setup_auth(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(REGISTRY))


def _components(snapshot):
    return {item.name: item for item in snapshot.components}


class MockDBConnection:
    def __init__(self, revision=EXPECTED_ALEMBIC_HEAD, can_connect=True):
        self.revision = revision
        self.can_connect = can_connect

    def __enter__(self):
        if not self.can_connect:
            raise RuntimeError("PostgreSQL connection refused: connection failed")
        return self

    def __exit__(self, *args):
        pass

    def execute(self, stmt):
        text_stmt = str(stmt).lower()
        if "alembic_version" in text_stmt:
            row = (self.revision,) if self.revision is not None else None
            return MagicMock(first=lambda: row)
        return MagicMock(first=lambda: (1,))


class MockDBEngine:
    def __init__(self, revision=EXPECTED_ALEMBIC_HEAD, can_connect=True):
        self.revision = revision
        self.can_connect = can_connect

    def connect(self):
        return MockDBConnection(revision=self.revision, can_connect=self.can_connect)


class MockRuntimeContainer:
    def __init__(self, revision=EXPECTED_ALEMBIC_HEAD, can_connect=True):
        self.engine = MockDBEngine(revision=revision, can_connect=can_connect)
        self._readiness_probe = PostgresReadinessProbe(self.engine)

    def readiness_probe(self):
        return self._readiness_probe


def test_readiness_when_postgres_healthy_and_alembic_at_head(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_mock_token_12345")
    chroma_dir = tmp_path / "chromadb"
    chroma_dir.mkdir()

    container = MockRuntimeContainer(revision=EXPECTED_ALEMBIC_HEAD, can_connect=True)
    snapshot = build_readiness_snapshot(container=container, chroma_dir=chroma_dir)

    assert snapshot.status is ReadinessStatus.READY
    comps = _components(snapshot)
    assert comps["database"].status is ReadinessStatus.READY
    assert comps["database"].reason_code == "ok"
    assert comps["alembic"].status is ReadinessStatus.READY
    assert comps["alembic"].reason_code == "ok"
    assert comps["alembic"].details["revision"] == EXPECTED_ALEMBIC_HEAD

    # Route verification -> HTTP 200
    app.dependency_overrides[get_runtime_container] = lambda: container
    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/ops/readiness",
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["status"] in ("ready", "READY")
    finally:
        app.dependency_overrides.pop(get_runtime_container, None)


def test_readiness_when_postgres_unavailable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_mock_token_12345")
    chroma_dir = tmp_path / "chromadb"
    chroma_dir.mkdir()

    container = MockRuntimeContainer(can_connect=False)
    snapshot = build_readiness_snapshot(container=container, chroma_dir=chroma_dir)

    assert snapshot.status is ReadinessStatus.NOT_READY
    comps = _components(snapshot)
    assert comps["database"].status is ReadinessStatus.NOT_READY
    assert comps["database"].reason_code == "connectivity_failed"
    assert comps["alembic"].status is ReadinessStatus.NOT_READY

    # Route verification -> HTTP 503
    app.dependency_overrides[get_runtime_container] = lambda: container
    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/ops/readiness",
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        )
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
    finally:
        app.dependency_overrides.pop(get_runtime_container, None)


def test_readiness_when_alembic_revision_behind(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_mock_token_12345")
    chroma_dir = tmp_path / "chromadb"
    chroma_dir.mkdir()

    behind_revision = "20260907_01"
    container = MockRuntimeContainer(revision=behind_revision, can_connect=True)
    snapshot = build_readiness_snapshot(container=container, chroma_dir=chroma_dir)

    assert snapshot.status is ReadinessStatus.NOT_READY
    comps = _components(snapshot)
    assert comps["database"].status is ReadinessStatus.READY
    assert comps["alembic"].status is ReadinessStatus.NOT_READY
    assert comps["alembic"].reason_code == "revision_mismatch"
    assert comps["alembic"].details["expected"] == EXPECTED_ALEMBIC_HEAD
    assert comps["alembic"].details["current"] == behind_revision

    # Route verification -> HTTP 503
    app.dependency_overrides[get_runtime_container] = lambda: container
    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/ops/readiness",
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        )
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
    finally:
        app.dependency_overrides.pop(get_runtime_container, None)


def test_readiness_response_leaks_no_raw_dsns_or_secrets(tmp_path: Path, monkeypatch):
    secret_pw = "secret_db_password_xyz987"
    secret_user = "secret_db_user_abc123"
    secret_host = "db.secret.cluster.internal"
    secret_dsn = f"postgresql+psycopg://{secret_user}:{secret_pw}@{secret_host}:5432/travel_db"
    secret_token = "ghp_ultra_secret_token_value_999"

    monkeypatch.setattr(settings, "DATABASE_URL", secret_dsn)
    monkeypatch.setattr(settings, "PG_PASSWORD", SecretStr(secret_pw))
    monkeypatch.setattr(settings, "GITHUB_TOKEN", secret_token)

    container = MockRuntimeContainer(revision=EXPECTED_ALEMBIC_HEAD, can_connect=True)
    snapshot = build_readiness_snapshot(container=container, chroma_dir=tmp_path)
    payload_json = json.dumps(snapshot.to_dict())

    app.dependency_overrides[get_runtime_container] = lambda: container
    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/ops/readiness",
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        )
        route_text = response.text
    finally:
        app.dependency_overrides.pop(get_runtime_container, None)

    for secret in (secret_pw, secret_user, secret_host, secret_token):
        assert secret not in payload_json
        assert secret not in route_text


def test_missing_token_reports_model_not_ready(monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")

    snapshot = build_readiness_snapshot()
    model = _components(snapshot)["model_provider"]

    assert model.status is ReadinessStatus.NOT_READY
    assert model.reason_code == "credential_missing"


def test_missing_chroma_path_reports_unknown_without_creating(tmp_path: Path):
    missing = tmp_path / "no-chromadb-here"

    snapshot = build_readiness_snapshot(chroma_dir=missing)

    assert _components(snapshot)["rag_chroma"].status in (
        ReadinessStatus.UNKNOWN,
        ReadinessStatus.NOT_READY,
    )
    assert not missing.exists()


def test_memory_pipeline_probe_reports_ready():
    snapshot = build_readiness_snapshot()
    mem = _components(snapshot)["memory_write_pipeline"]

    assert mem.status is ReadinessStatus.READY
    assert mem.reason_code == "ok"


def test_snapshot_dict_contains_no_absolute_paths(tmp_path: Path):
    snapshot = build_readiness_snapshot(chroma_dir=tmp_path / "custom")
    payload = json.dumps(snapshot.to_dict())

    assert tmp_path.as_posix() not in payload
    assert str(tmp_path) not in payload
