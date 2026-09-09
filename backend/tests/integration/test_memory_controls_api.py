"""Integration tests for risk-based memory control routes.

Every test runs against the ISOLATED disposable PostgreSQL addressed by
`PG_TEST_DSN` (dedicated container and database, never user data). When
the variable is unset the module skips distinctly instead of
pretending to be green. The command service is wired to the real
PostgreSQL unit of work; the principal dependency is overridden to a
fixed owner. No test constructs a model client or touches user data.
"""

import os
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


def _test_dsn() -> str:
    dsn = os.environ.get("PG_TEST_DSN")
    if not dsn:
        pytest.skip("isolated PG unavailable: set PG_TEST_DSN to a disposable database")
    return dsn


@pytest.fixture(scope="module")
def pg_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(_test_dsn())
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    except Exception as error:
        engine.dispose()
        pytest.skip(f"isolated PG unreachable: {type(error).__name__}")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated(pg_engine):
    from alembic import command
    from pathlib import Path

    from backend.storage.postgres import alembic_config

    migrations = (
        Path(__file__).resolve().parent.parent.parent / "storage" / "migrations"
    )
    with pg_engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(str(migrations), _test_dsn()), "head")
    yield pg_engine


@pytest.fixture()
def clean(pg_engine, migrated):
    with pg_engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE memory_write_idempotency, memory_outbox, "
                "memory_events, memory_decisions, memory_evidence, "
                "memory_candidates, memory_versions, memory_assertions"
            )
        )
    yield pg_engine


def _principal(owner="owner_a"):
    from backend.security.models import AuthenticatedPrincipal, AuthMode

    return AuthenticatedPrincipal(
        owner_user_id=owner,
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="test",
    )


@pytest.fixture()
def client(clean):
    from backend.app.api.memory_controls import get_command_service
    from backend.app.main import app
    from backend.memory.write_pipeline.postgres import (
        PostgresMemoryUnitOfWork,
        pg_commit_bulk_delete,
        pg_commit_delete_one,
        pg_list_active_versions,
        read_current_versions,
    )
    from backend.memory.write_pipeline.service import MemoryCommandService
    from backend.security.dependencies import require_principal
    from functools import partial

    engine = clean
    uow = PostgresMemoryUnitOfWork(engine)
    service = MemoryCommandService(
        uow=uow,
        read_versions=lambda identity: read_current_versions(engine, identity),
        list_active_versions=partial(pg_list_active_versions, engine),
        commit_delete_one=partial(pg_commit_delete_one, engine),
        commit_bulk_delete=partial(pg_commit_bulk_delete, engine),
    )
    app.dependency_overrides[get_command_service] = lambda: service
    app.dependency_overrides[require_principal] = lambda: _principal()
    yield TestClient(app)
    app.dependency_overrides.pop(get_command_service, None)
    app.dependency_overrides.pop(require_principal, None)


def _version_count(engine, status="active"):
    with engine.connect() as connection:
        return connection.execute(
            sa.text("SELECT COUNT(*) FROM memory_versions WHERE status = :s"),
            {"s": status},
        ).scalar()


# 1. Remember commits directly and emits an app-owned saved event.


def test_remember_direct_saved_event_and_row(client, clean):
    response = client.post(
        "/api/v1/memory/controls/commands",
        json={"utterance": "remember quiet hotels"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "saved"
    assert body["operation"] == "add"
    assert body["scope"] == "user"
    assert body["canonical_key"] == "travel.preference.hotel_atmosphere"
    assert body["normalized_value"] == "quiet"
    assert body["version_id"].startswith("mem_")
    assert _version_count(clean) == 1


def test_correct_direct_supersedes(client, clean):
    client.post(
        "/api/v1/memory/controls/commands", json={"utterance": "remember quiet"}
    )
    response = client.post(
        "/api/v1/memory/controls/commands",
        json={"utterance": "sửa lại thành trung tâm"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "saved"
    assert response.json()["operation"] == "supersede"
    assert _version_count(clean) == 1
    assert _version_count(clean, "superseded") == 1


def test_delete_one_direct_undo_and_ledger(client, clean):
    client.post(
        "/api/v1/memory/controls/commands", json={"utterance": "remember quiet"}
    )
    response = client.post(
        "/api/v1/memory/controls/commands", json={"utterance": "delete quiet"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "deleted"
    assert body["undo"]["version_ids"]
    assert _version_count(clean) == 0
    with clean.connect() as connection:
        ledger = connection.execute(
            sa.text("SELECT COUNT(*) FROM memory_deletion_ledger")
        ).scalar()
    assert ledger == 1


def test_toggle_direct_without_durable_claim(client, clean):
    response = client.post(
        "/api/v1/memory/controls/commands", json={"utterance": "disable memory"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "toggled"
    assert body["persistent"] is False
    assert _version_count(clean) == 0


# 2. Bulk delete travels preview → token → confirm → commit.


def test_bulk_preview_token_confirm_commit(client, clean):
    client.post(
        "/api/v1/memory/controls/commands", json={"utterance": "remember quiet"}
    )
    client.post(
        "/api/v1/memory/controls/commands",
        json={
            "utterance": "remember a lively room in this chat",
            "scope": "conversation",
            "conversation_id": "cv_trip",
        },
    )
    offered = client.post(
        "/api/v1/memory/controls/commands", json={"utterance": "delete"}
    ).json()
    assert offered["status"] == "preview_required"
    assert len(offered["preview"]["targets"]) == 2

    committed = client.post(
        "/api/v1/memory/controls/confirmations",
        json={
            "preview_id": offered["preview"]["preview_id"],
            "token": offered["preview"]["token"],
        },
    )
    assert committed.status_code == 200
    assert committed.json()["status"] == "committed"
    assert len(committed.json()["committed_version_ids"]) == 2
    assert _version_count(clean) == 0

    replayed = client.post(
        "/api/v1/memory/controls/confirmations",
        json={
            "preview_id": offered["preview"]["preview_id"],
            "token": offered["preview"]["token"],
        },
    )
    assert replayed.status_code == 404


def test_stale_preview_conflicts_without_mutation(client, clean):
    client.post(
        "/api/v1/memory/controls/commands", json={"utterance": "remember quiet"}
    )
    client.post(
        "/api/v1/memory/controls/commands",
        json={
            "utterance": "remember a lively room in this chat",
            "scope": "conversation",
            "conversation_id": "cv_trip",
        },
    )
    offered = client.post(
        "/api/v1/memory/controls/commands", json={"utterance": "delete"}
    ).json()
    first_target = offered["preview"]["targets"][0]["version_id"]
    direct = client.post(
        "/api/v1/memory/controls/deletions", json={"version_ids": [first_target]}
    )
    assert direct.status_code == 200

    stale = client.post(
        "/api/v1/memory/controls/confirmations",
        json={
            "preview_id": offered["preview"]["preview_id"],
            "token": offered["preview"]["token"],
        },
    )
    assert stale.status_code == 409
    assert _version_count(clean) == 1


def test_cross_owner_ids_miss_without_leak(client, clean):
    client.post(
        "/api/v1/memory/controls/commands", json={"utterance": "remember quiet"}
    )
    with clean.connect() as connection:
        foreign_id = connection.execute(
            sa.text("SELECT version_id FROM memory_versions LIMIT 1")
        ).scalar()

    from backend.app.main import app
    from backend.security.dependencies import require_principal

    app.dependency_overrides[require_principal] = lambda: _principal("owner_b")
    try:
        listed = client.get("/api/v1/memory/controls/memories")
        assert listed.status_code == 200
        assert listed.json()["memories"] == []
        removal = client.post(
            "/api/v1/memory/controls/deletions", json={"version_ids": [foreign_id]}
        )
        assert removal.status_code == 404
        assert foreign_id not in removal.text
    finally:
        app.dependency_overrides[require_principal] = lambda: _principal()


def test_sensitive_input_no_store_no_prompt(client, clean):
    response = client.post(
        "/api/v1/memory/controls/commands",
        json={"utterance": "remember api key sk-test-AbC999 please"},
    )

    assert response.status_code == 200
    assert response.json()["status"] in ("held", "refused")
    assert "sk-test-AbC999" not in response.text
    assert _version_count(clean) == 0
    with clean.connect() as connection:
        decisions = connection.execute(
            sa.text("SELECT COUNT(*) FROM memory_decisions")
        ).scalar()
    assert decisions == 0


def test_ack_only_after_commit_on_storage_failure(client, clean):
    from backend.app.api.memory_controls import get_command_service
    from backend.app.main import app
    from backend.memory.write_pipeline.uow import MemoryWriteError

    class FailingUoW:
        def apply_memory_change(self, *args, **kwargs):
            raise MemoryWriteError("injected commit failure")

    from backend.memory.write_pipeline.service import MemoryCommandService

    app.dependency_overrides[get_command_service] = lambda: MemoryCommandService(
        uow=FailingUoW(),
        read_versions=lambda identity: (),
        list_active_versions=lambda owner: (),
        commit_delete_one=lambda o, v, r: (_ for _ in ()).throw(
            AssertionError("no control write on this path")
        ),
        commit_bulk_delete=lambda o, v, r: (_ for _ in ()).throw(
            AssertionError("no control write on this path")
        ),
    )
    try:
        response = client.post(
            "/api/v1/memory/controls/commands", json={"utterance": "remember quiet"}
        )
    finally:
        app.dependency_overrides.pop(get_command_service, None)

    assert response.status_code == 500
    assert "saved" not in response.text
    assert _version_count(clean) == 0


def test_preview_display_names_operation_and_scopes(client, clean):
    client.post(
        "/api/v1/memory/controls/commands", json={"utterance": "remember quiet"}
    )
    client.post(
        "/api/v1/memory/controls/commands",
        json={
            "utterance": "remember a lively room in this chat",
            "scope": "conversation",
            "conversation_id": "cv_trip",
        },
    )
    offered = client.post(
        "/api/v1/memory/controls/commands", json={"utterance": "delete"}
    ).json()

    assert offered["status"] == "preview_required"
    assert offered["preview"]["operation"] == "bulk_delete"
    assert {target["scope"] for target in offered["preview"]["targets"]} == {
        "user",
        "conversation",
    }


def test_scope_expansion_preview_confirm_and_tombstone(client, clean):
    save_resp = client.post(
        "/api/v1/memory/controls/commands",
        json={
            "utterance": "remember a lively atmosphere in this chat",
            "scope": "conversation",
            "conversation_id": "cv_paris",
        },
    )
    assert save_resp.status_code == 200
    conv_version_id = save_resp.json()["version_id"]

    expand_resp = client.post(
        "/api/v1/memory/controls/expansions",
        json={"version_id": conv_version_id},
    )
    assert expand_resp.status_code == 200
    offer = expand_resp.json()
    assert offer["status"] == "preview_required"
    preview = offer["preview"]
    assert preview["operation"] == "scope_expansion"
    assert preview["targets"][0]["old_scope"] == "conversation"
    assert preview["targets"][0]["new_scope"] == "user"

    confirm_resp = client.post(
        "/api/v1/memory/controls/confirmations",
        json={
            "preview_id": preview["preview_id"],
            "token": preview["token"],
        },
    )
    assert confirm_resp.status_code == 200
    result = confirm_resp.json()
    assert result["status"] == "saved"
    assert result["scope"] == "user"
    assert result["normalized_value"] == "lively"

    listed = client.get("/api/v1/memory/controls/memories").json()["memories"]
    assert len(listed) == 1
    assert listed[0]["scope"] == "user"
    assert listed[0]["normalized_value"] == "lively"
    assert _version_count(clean, "active") == 1
    assert _version_count(clean, "superseded") == 1


def test_command_service_singleton_lifecycle():
    from backend.app.api.memory_controls import get_command_service

    svc1 = get_command_service()
    svc2 = get_command_service()
    assert svc1 is svc2
