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
    _probe_memory_pipeline,
    _probe_postgres,
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


def _seed_chroma_collection(chroma_dir: Path) -> None:
    """Create a real, queryable Chroma collection so the probe can open it."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    client = chromadb.PersistentClient(
        path=str(chroma_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(name="vietnam_travel_parent_child")
    collection.add(
        ids=["seed_1"],
        documents=["seed document"],
        embeddings=[[0.1, 0.2, 0.3]],
    )


def test_readiness_when_postgres_healthy_and_alembic_at_head(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_mock_token_12345")
    chroma_dir = tmp_path / "chromadb"
    _seed_chroma_collection(chroma_dir)

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
    secret_dsn = (
        f"postgresql+psycopg://{secret_user}:{secret_pw}@{secret_host}:5432/travel_db"
    )
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


def test_existing_chroma_dir_without_collection_is_not_ready(tmp_path: Path):
    """A present directory is not proof of an openable index."""
    chroma_dir = tmp_path / "chromadb"
    chroma_dir.mkdir()

    snapshot = build_readiness_snapshot(chroma_dir=chroma_dir)
    chroma = _components(snapshot)["rag_chroma"]

    assert chroma.status is ReadinessStatus.NOT_READY
    assert chroma.reason_code == "index_missing"


def test_probe_creates_no_state_in_empty_directory(tmp_path: Path):
    """The probe is read-only: an empty directory stays empty."""
    chroma_dir = tmp_path / "chromadb"
    chroma_dir.mkdir()

    build_readiness_snapshot(chroma_dir=chroma_dir)

    assert sorted(child.name for child in chroma_dir.iterdir()) == []


def test_probe_leaves_seeded_store_untouched(tmp_path: Path):
    """Probing a live store must not add WAL/shared-memory sidecars."""
    chroma_dir = tmp_path / "chromadb"
    _seed_chroma_collection(chroma_dir)
    before = sorted(child.name for child in chroma_dir.iterdir())

    build_readiness_snapshot(chroma_dir=chroma_dir)

    assert sorted(child.name for child in chroma_dir.iterdir()) == before


def _seed_chroma_collection_named(
    chroma_dir: Path, name: str, with_vector: bool
) -> None:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    client = chromadb.PersistentClient(
        path=str(chroma_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(name=name)
    if with_vector:
        collection.add(
            ids=["seed_1"],
            documents=["seed document"],
            embeddings=[[0.1, 0.2, 0.3]],
        )


def test_chroma_missing_collection_is_not_ready(tmp_path: Path):
    """A store without the expected collection cannot serve retrieval."""
    from backend.observability.readiness import _probe_rag_chroma

    chroma_dir = tmp_path / "chromadb"
    _seed_chroma_collection_named(chroma_dir, "other_collection", with_vector=True)

    component = _probe_rag_chroma(chroma_dir)

    assert component.status is ReadinessStatus.NOT_READY
    assert component.reason_code == "collection_missing"


def test_chroma_empty_collection_is_degraded(tmp_path: Path):
    from backend.observability.readiness import _probe_rag_chroma

    chroma_dir = tmp_path / "chromadb"
    _seed_chroma_collection_named(
        chroma_dir, "vietnam_travel_parent_child", with_vector=False
    )

    component = _probe_rag_chroma(chroma_dir)

    assert component.status is ReadinessStatus.DEGRADED
    assert component.reason_code == "collection_empty"


def test_chroma_corrupt_file_is_not_ready(tmp_path: Path):
    from backend.observability.readiness import _probe_rag_chroma

    chroma_dir = tmp_path / "chromadb"
    chroma_dir.mkdir()
    (chroma_dir / "chroma.sqlite3").write_bytes(b"not a sqlite file")

    component = _probe_rag_chroma(chroma_dir)

    assert component.status is ReadinessStatus.NOT_READY
    assert component.reason_code == "collection_unavailable"


def test_chroma_unreadable_index_is_degraded(monkeypatch, tmp_path: Path):
    """Count>0 but no sample row means the index cannot be trusted."""
    import sqlite3

    from backend.observability import readiness as readiness_module

    class _FakeCursor:
        def __init__(self, rows):
            self._rows = list(rows)

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            # The probe now also reads the VECTOR segment ids to confirm their
            # directories exist, so the double must support a full fetch.
            return list(self._rows)

    class _FakeConnection:
        def execute(self, sql, params=()):
            if "FROM collections" in sql:
                return _FakeCursor([("collection-id-1",)])
            if "COUNT(*)" in sql:
                return _FakeCursor([(3,)])
            return _FakeCursor([])

        def close(self):
            pass

    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: _FakeConnection())

    # A real directory + file so the probe reaches the query stage.
    chroma_dir = tmp_path / "chromadb"
    chroma_dir.mkdir()
    (chroma_dir / "chroma.sqlite3").write_bytes(b"stubbed")

    probed = readiness_module._probe_rag_chroma(chroma_dir)

    assert probed.status is ReadinessStatus.DEGRADED
    assert probed.reason_code == "index_unreadable"


def test_memory_pipeline_probe_reports_unknown_when_disabled(monkeypatch):
    """C7: this probe used to return READY unconditionally.

    With the pipeline disabled there is nothing to observe, so the honest
    status is UNKNOWN — reporting READY made a dead pipeline indistinguishable
    from a healthy one.
    """
    from backend.observability.readiness import _probe_memory_pipeline

    monkeypatch.setattr(settings, "MEMORY_WRITE_PIPELINE_ENABLED", False, raising=False)

    component = _probe_memory_pipeline()

    assert component.status is ReadinessStatus.UNKNOWN
    assert component.reason_code == "disabled"


def test_memory_pipeline_probe_reports_not_ready_when_outbox_unreadable(monkeypatch):
    from backend.observability.readiness import _probe_memory_pipeline

    monkeypatch.setattr(settings, "MEMORY_WRITE_PIPELINE_ENABLED", True, raising=False)

    probe = MagicMock()
    probe.count_ready_outbox_events.side_effect = RuntimeError("outbox gone")
    container = MagicMock()
    container.readiness_probe.return_value = probe

    component = _probe_memory_pipeline(container)

    assert component.status is ReadinessStatus.NOT_READY
    assert component.reason_code == "outbox_unavailable"


def test_memory_pipeline_probe_no_longer_treats_depth_as_health(monkeypatch):
    """Two tests used to assert the defect. They are corrected, not deleted.

    `test_memory_pipeline_probe_reports_degraded_with_backlog` asserted that seven
    queued events made the component DEGRADED — and the ops route turns DEGRADED
    into HTTP 503, so a healthy worker draining a normal queue took the whole API
    out of service. Its companion asserted an empty queue was READY, which is also
    exactly what a dead worker with nothing queued looks like.

    Same inputs, corrected mapping: depth is *reported*, and staleness decides.
    """
    from backend.observability.readiness import _probe_memory_pipeline

    monkeypatch.setattr(settings, "MEMORY_WRITE_PIPELINE_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "MEMORY_BACKLOG_STALE_SECONDS", 900.0, raising=False)

    def _probe_with(pending, oldest_age):
        probe = MagicMock()
        probe.count_ready_outbox_events.return_value = pending
        probe.oldest_ready_outbox_event_age_seconds.return_value = oldest_age
        probe.dead_letter_outbox_event_count.return_value = 0
        container = MagicMock()
        container.readiness_probe.return_value = probe
        return _probe_memory_pipeline(container)

    draining = _probe_with(pending=7, oldest_age=5)
    assert draining.status is ReadinessStatus.READY
    assert draining.reason_code == "ok"
    assert draining.details["ready_events"] == 7, "depth is reported, not judged"

    empty = _probe_with(pending=0, oldest_age=0)
    assert empty.status is ReadinessStatus.READY
    assert empty.reason_code == "ok"

    stalled = _probe_with(pending=7, oldest_age=3600)
    assert stalled.status is ReadinessStatus.DEGRADED
    assert stalled.reason_code == "backlog_stale"


def test_chroma_not_ready_when_a_segment_directory_is_missing(tmp_path: Path):
    """C6: catalogue rows survive a deleted HNSW segment, so counting them lies."""
    import shutil

    from backend.observability.readiness import _probe_rag_chroma

    chroma_dir = tmp_path / "chromadb"
    _seed_chroma_collection_named(
        chroma_dir, "vietnam_travel_parent_child", with_vector=True
    )

    healthy = _probe_rag_chroma(chroma_dir)
    assert healthy.status is ReadinessStatus.READY

    segment_dirs = [
        entry for entry in chroma_dir.iterdir() if entry.is_dir()
    ]
    assert segment_dirs, "seeded store has no segment directory to delete"
    shutil.rmtree(segment_dirs[0])

    component = _probe_rag_chroma(chroma_dir)

    assert component.status is ReadinessStatus.NOT_READY
    assert component.reason_code == "segment_missing"


def test_snapshot_dict_contains_no_absolute_paths(tmp_path: Path):
    snapshot = build_readiness_snapshot(chroma_dir=tmp_path / "custom")
    payload = json.dumps(snapshot.to_dict())

    assert tmp_path.as_posix() not in payload
    assert str(tmp_path) not in payload


# --- the model provider needs both halves of its configuration ----------------


def test_model_provider_not_ready_without_an_endpoint(monkeypatch):
    """A token alone is not a usable provider.

    `config.py` deliberately provides no endpoint fallback, so an empty
    `GITHUB_MODELS_URL` makes the first model call fail with
    `APIConnectionError`. Checking the token alone reported `ready` for a
    deployment that could not answer a single request.
    """
    from backend.observability.models import ReadinessStatus
    from backend.observability.readiness import _probe_model_provider

    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_mock_token_12345")
    monkeypatch.setattr(settings, "GITHUB_MODELS_URL", "")

    component = _probe_model_provider()
    assert component.status is ReadinessStatus.NOT_READY
    assert component.reason_code == "endpoint_missing"


def test_model_provider_ready_with_both_halves(monkeypatch):
    from backend.observability.models import ReadinessStatus
    from backend.observability.readiness import _probe_model_provider

    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_mock_token_12345")
    monkeypatch.setattr(settings, "GITHUB_MODELS_URL", "https://api.example.test/v1")

    assert _probe_model_provider().status is ReadinessStatus.READY


def test_model_provider_not_ready_without_a_credential(monkeypatch):
    from backend.observability.models import ReadinessStatus
    from backend.observability.readiness import _probe_model_provider

    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
    monkeypatch.setattr(settings, "GITHUB_MODELS_URL", "https://api.example.test/v1")

    component = _probe_model_provider()
    assert component.status is ReadinessStatus.NOT_READY
    assert component.reason_code == "credential_missing"


# --- a probe must not compose the application ---------------------------------


def test_a_probe_without_a_container_refuses_instead_of_composing_one():
    """`_resolve_probe` used to build a production container inside a probe.

    That broke this module's own stated contract — "component probes never create
    state as a side effect" — because constructing a `RuntimeContainer` creates an
    engine and a pool. Worse, it was reachable from a unit test, so a probe's
    result depended on whether a database happened to be reachable and on which
    role it granted.

    Composition happens in the FastAPI lifespan. A probe with no container says so.
    """
    from types import SimpleNamespace

    from backend.app.runtime_container import ContainerUnavailableError
    from backend.observability.readiness import _resolve_probe

    with pytest.raises(ContainerUnavailableError):
        _resolve_probe()

    # A container-shaped object with neither a probe nor an engine is not a
    # container, so it must be refused rather than half-used.
    with pytest.raises(ContainerUnavailableError):
        _resolve_probe(SimpleNamespace())


def test_the_probe_failures_surface_as_not_ready_components(monkeypatch):
    """The refusal must not escape as a 500 from the probe functions.

    A missing container is a readiness fact, not a crash: the components that need
    a probe report NOT_READY with a reason code, which is what an operator reads.
    """
    from types import SimpleNamespace

    from backend.observability.readiness import (
        _probe_memory_pipeline,
        _probe_postgres,
    )

    empty = SimpleNamespace()
    assert _probe_postgres(empty).status is ReadinessStatus.NOT_READY
    assert _probe_postgres(empty).reason_code is not None
    # The Memory component is gated: with the pipeline disabled it reports UNKNOWN
    # without touching a probe at all, which is the documented behaviour.
    assert _probe_memory_pipeline(empty).status in (
        ReadinessStatus.UNKNOWN,
        ReadinessStatus.NOT_READY,
    )


# --- the memory component answers the right question ---------------------------


class _FakeMemoryProbe:
    """A probe with controllable signals, so the mapping is asserted exactly."""

    def __init__(self, pending=0, oldest_age=0, dead_letters=0, raises=None):
        self._pending = pending
        self._oldest_age = oldest_age
        self._dead_letters = dead_letters
        self._raises = raises

    def _maybe_raise(self):
        if self._raises is not None:
            raise self._raises

    def count_ready_outbox_events(self):
        self._maybe_raise()
        return self._pending

    def oldest_ready_outbox_event_age_seconds(self):
        self._maybe_raise()
        return self._oldest_age

    def dead_letter_outbox_event_count(self):
        self._maybe_raise()
        return self._dead_letters


class _FakeContainer:
    def __init__(self, probe):
        self._probe = probe

    def readiness_probe(self):
        return self._probe


@pytest.fixture
def memory_pipeline_enabled(monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_WRITE_PIPELINE_ENABLED", True)
    monkeypatch.setattr(settings, "MEMORY_BACKLOG_STALE_SECONDS", 900.0)


def test_a_draining_backlog_is_healthy(memory_pipeline_enabled):
    """The defect, first half: a healthy worker with one queued job reported DEGRADED.

    Depth is not health. Five events being drained steadily is a healthy pipeline.
    """
    component = _probe_memory_pipeline(
        _FakeContainer(_FakeMemoryProbe(pending=5, oldest_age=3))
    )

    assert component.status is ReadinessStatus.READY
    assert component.reason_code == "ok"
    assert component.details["ready_events"] == 5


def test_a_stale_backlog_is_degraded(memory_pipeline_enabled):
    """The other half, inverted: what *should* be alarming.

    One event nobody has claimed for twenty minutes is a stalled worker — the
    condition the old mapping could not see when the queue was empty and could not
    distinguish from a busy one when it was not.
    """
    component = _probe_memory_pipeline(
        _FakeContainer(_FakeMemoryProbe(pending=1, oldest_age=1200))
    )

    assert component.status is ReadinessStatus.DEGRADED
    assert component.reason_code == "backlog_stale"
    assert component.details["oldest_ready_event_age_seconds"] == 1200


def test_the_staleness_boundary_is_not_stale(memory_pipeline_enabled):
    """Exactly at the threshold is still healthy; the comparison is strict."""
    component = _probe_memory_pipeline(
        _FakeContainer(_FakeMemoryProbe(pending=1, oldest_age=900))
    )

    assert component.status is ReadinessStatus.READY


def test_dead_letters_are_reported_without_degrading(memory_pipeline_enabled):
    """A dead letter is a data condition, not a reason to 503 the whole API."""
    component = _probe_memory_pipeline(
        _FakeContainer(_FakeMemoryProbe(pending=0, oldest_age=0, dead_letters=3))
    )

    assert component.status is ReadinessStatus.READY
    assert component.details["dead_letters"] == 3


def test_an_unreadable_outbox_is_not_ready(memory_pipeline_enabled):
    component = _probe_memory_pipeline(
        _FakeContainer(_FakeMemoryProbe(raises=RuntimeError("outbox gone")))
    )

    assert component.status is ReadinessStatus.NOT_READY
    assert component.reason_code == "outbox_unavailable"


def test_a_disabled_pipeline_is_unknown_and_is_never_probed(monkeypatch):
    """With the gate off the component must not touch the database at all."""
    from backend.observability.readiness import _probe_memory_pipeline

    monkeypatch.setattr(settings, "MEMORY_WRITE_PIPELINE_ENABLED", False)

    class _Exploding:
        def readiness_probe(self):
            raise AssertionError("a disabled pipeline must not be probed")

    component = _probe_memory_pipeline(_Exploding())

    assert component.status is ReadinessStatus.UNKNOWN
    assert component.reason_code == "disabled"


def test_the_component_is_not_a_constant(memory_pipeline_enabled):
    """C7's lesson, re-asserted against the mapping that replaced it.

    Every status must be reachable, or the component is answering a fixed question
    again — which is how it reported a dead worker as healthy the first time.
    """
    statuses = {
        _probe_memory_pipeline(_FakeContainer(_FakeMemoryProbe())).status,
        _probe_memory_pipeline(
            _FakeContainer(_FakeMemoryProbe(oldest_age=10_000))
        ).status,
        _probe_memory_pipeline(
            _FakeContainer(_FakeMemoryProbe(raises=RuntimeError()))
        ).status,
    }

    assert statuses == {
        ReadinessStatus.READY,
        ReadinessStatus.DEGRADED,
        ReadinessStatus.NOT_READY,
    }


# --- a background failure must not take the instance out of rotation -----------


def test_a_stalled_background_worker_does_not_make_the_instance_not_ready():
    """The failure-domain decision, asserted.

    `ops.py` turns any aggregate other than READY into HTTP 503, and that status is
    what a load balancer reads. Memory formation is a background service the chat
    surface works without, so a stalled worker must be *reported* — with its own
    status and reason code — without removing a healthy instance from rotation.
    """
    from backend.observability.models import ReadinessComponent
    from backend.observability.readiness import _compose_status

    components = [
        ReadinessComponent(name="app", status=ReadinessStatus.READY, reason_code="ok"),
        ReadinessComponent(
            name="database", status=ReadinessStatus.READY, reason_code="ok"
        ),
        ReadinessComponent(
            name="memory_write_pipeline",
            status=ReadinessStatus.DEGRADED,
            reason_code="backlog_stale",
            critical=False,
        ),
    ]

    assert _compose_status(components) is ReadinessStatus.READY


def test_a_critical_component_still_drives_the_aggregate():
    """The control: non-critical must not have quietly made everything optional."""
    from backend.observability.models import ReadinessComponent
    from backend.observability.readiness import _compose_status

    components = [
        ReadinessComponent(name="app", status=ReadinessStatus.READY, reason_code="ok"),
        ReadinessComponent(
            name="database",
            status=ReadinessStatus.NOT_READY,
            reason_code="unavailable",
        ),
    ]

    assert _compose_status(components) is ReadinessStatus.NOT_READY


def test_the_memory_component_reports_itself_as_non_critical(memory_pipeline_enabled):
    """Asserted on the probe, so the flag cannot be dropped without a failure.

    Dropping it would not break any status assertion — it would only make a
    background stall able to take the whole API out of service, which is the defect.
    """
    component = _probe_memory_pipeline(
        _FakeContainer(_FakeMemoryProbe(oldest_age=10_000))
    )

    assert component.status is ReadinessStatus.DEGRADED, "still reported"
    assert component.critical is False, "and not aggregated"
