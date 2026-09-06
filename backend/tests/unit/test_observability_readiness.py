"""Unit tests for the R8 read-only readiness service.

Probes never create databases, directories, or collections; tests assert
the inspected paths stay absent. No test calls a model provider, Chroma,
embeddings, or the network.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from backend.app.config import settings
from backend.observability.models import ReadinessStatus
from backend.observability.readiness import build_readiness_snapshot
from backend.storage.schema_registry import (
    open_application_database,
    register_module_schema,
)


def _components(snapshot):
    return {item.name: item for item in snapshot.components}


def test_missing_token_reports_model_not_ready(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")

    snapshot = build_readiness_snapshot(
        reports_dir=tmp_path, db_path=tmp_path / "missing.sqlite3"
    )
    model = _components(snapshot)["model_provider"]

    assert model.status is ReadinessStatus.NOT_READY
    assert model.reason_code == "credential_missing"


def test_missing_chroma_path_reports_unknown_without_creating(tmp_path: Path):
    missing = tmp_path / "no-chromadb-here"

    snapshot = build_readiness_snapshot(
        reports_dir=tmp_path,
        db_path=tmp_path / "missing.sqlite3",
        chroma_dir=missing,
    )

    assert _components(snapshot)["rag_chroma"].status in (
        ReadinessStatus.UNKNOWN,
        ReadinessStatus.NOT_READY,
    )
    assert not missing.exists()


def test_missing_db_reports_unknown_without_creating(tmp_path: Path):
    missing = tmp_path / "missing.sqlite3"

    snapshot = build_readiness_snapshot(reports_dir=tmp_path, db_path=missing)

    assert _components(snapshot)["app_db"].status in (
        ReadinessStatus.UNKNOWN,
        ReadinessStatus.NOT_READY,
    )
    assert not missing.exists()


def test_incompatible_schema_row_reports_not_ready(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"
    connection = open_application_database(db_path)
    try:
        register_module_schema(connection, "memory", 99, lambda _: None)
    finally:
        connection.close()

    snapshot = build_readiness_snapshot(reports_dir=tmp_path, db_path=db_path)

    app_db = _components(snapshot)["app_db"]
    assert app_db.status is ReadinessStatus.NOT_READY
    assert app_db.reason_code == "schema_incompatible"


def test_disabled_memory_flag_reports_degraded(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "MEMORY_RETRIEVAL_ENABLED", False)

    snapshot = build_readiness_snapshot(
        reports_dir=tmp_path, db_path=tmp_path / "missing.sqlite3"
    )
    memory = _components(snapshot)["memory"]

    assert memory.status is ReadinessStatus.DEGRADED
    assert memory.reason_code == "memory_retrieval_disabled"


def test_existing_pass_report_surfaces_as_safe_metadata(tmp_path: Path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "r6-retrieval-v0.1.json").write_text(
        json.dumps({"result_state": "PASS"}), encoding="utf-8"
    )

    snapshot = build_readiness_snapshot(
        reports_dir=tmp_path, db_path=tmp_path / "missing.sqlite3"
    )
    details = _components(snapshot)["memory"].details

    assert details["report"] == "PASS"


def test_snapshot_dict_contains_no_absolute_paths(tmp_path: Path):
    snapshot = build_readiness_snapshot(
        reports_dir=tmp_path, db_path=tmp_path / "missing.sqlite3"
    )
    payload = json.dumps(
        {
            "status": snapshot.status.value,
            "components": [
                {
                    "name": item.name,
                    "status": item.status.value,
                    "reason_code": item.reason_code,
                    "details": item.details,
                }
                for item in snapshot.components
            ],
        }
    )

    assert tmp_path.as_posix() not in payload
    assert str(tmp_path) not in payload
