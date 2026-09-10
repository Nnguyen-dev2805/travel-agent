"""Unit tests for the clean-break read-only readiness service.

Probes inspect local metadata and service connectivity without creating state.
PostgreSQL connectivity is probed via the engine connection pool.
No provider is called for generation; Chroma and models are configuration/path checked.
"""

import json
from pathlib import Path
import pytest

from backend.app.config import settings
from backend.observability.models import ReadinessStatus
from backend.observability.readiness import build_readiness_snapshot


def _components(snapshot):
    return {item.name: item for item in snapshot.components}


def test_missing_token_reports_model_not_ready(monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")

    snapshot = build_readiness_snapshot()
    model = _components(snapshot)["model_provider"]

    assert model.status is ReadinessStatus.NOT_READY
    assert model.reason_code == "credential_missing"


def test_present_token_reports_model_ready(monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_fake_test_token_12345")

    snapshot = build_readiness_snapshot()
    model = _components(snapshot)["model_provider"]

    assert model.status is ReadinessStatus.READY
    assert model.reason_code == "ok"


def test_missing_chroma_path_reports_unknown_without_creating(tmp_path: Path):
    missing = tmp_path / "no-chromadb-here"

    snapshot = build_readiness_snapshot(chroma_dir=missing)

    assert _components(snapshot)["rag_chroma"].status in (
        ReadinessStatus.UNKNOWN,
        ReadinessStatus.NOT_READY,
    )
    assert not missing.exists()


def test_present_chroma_path_reports_ready(tmp_path: Path):
    chroma_dir = tmp_path / "chromadb"
    chroma_dir.mkdir()

    snapshot = build_readiness_snapshot(chroma_dir=chroma_dir)

    assert _components(snapshot)["rag_chroma"].status is ReadinessStatus.READY
    assert _components(snapshot)["rag_chroma"].reason_code == "path_present"


def test_database_probe_reports_ready_and_not_ready():
    class FakeEngine:
        def __init__(self, succeeds=True):
            self.succeeds = succeeds

        def connect(self):
            class FakeConn:
                def __init__(self_inner, succeeds):
                    self_inner.succeeds = succeeds

                def __enter__(self_inner):
                    if not self_inner.succeeds:
                        raise RuntimeError("DB connection failed")
                    return self_inner

                def __exit__(self_inner, *args):
                    pass

                def execute(self_inner, stmt):
                    pass

            return FakeConn(self.succeeds)

    class FakeContainer:
        def __init__(self, succeeds=True):
            self.engine = FakeEngine(succeeds=succeeds)

    snap_ok = build_readiness_snapshot(container=FakeContainer(succeeds=True))
    assert _components(snap_ok)["database"].status is ReadinessStatus.READY

    snap_fail = build_readiness_snapshot(container=FakeContainer(succeeds=False))
    assert _components(snap_fail)["database"].status is ReadinessStatus.NOT_READY
    assert _components(snap_fail)["database"].reason_code == "connectivity_failed"


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
