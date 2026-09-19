"""Unit tests for PostgresMemoryStore projection and coercion."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.memory.lifecycle import SourceValidity
from backend.memory.postgres_store import PostgresMemoryStore
from backend.memory.read_models import MemoryReadRequest
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryScope,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
)

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)


def _make_fake_row(
    version_id="ver_1",
    owner_user_id="user_123",
    value_payload=None,
    authority="explicit_save",
    sensitivity="ordinary_personal",
    status="active",
    valid_from=NOW,
    retention_mode="user_durable",
    expires_at=None,
    stamped_generation=1,
    canonical_key="travel.preference.hotel_atmosphere",
    scope="user",
    scope_id="user_123",
    current_generation=1,
    has_unresolved_conflict=False,
    has_valid_evidence=True,
):
    if value_payload is None:
        value_payload = {"normalized_value": "quiet"}
    return {
        "version_id": version_id,
        "owner_user_id": owner_user_id,
        "value_payload": value_payload,
        "authority": authority,
        "sensitivity": sensitivity,
        "status": status,
        "valid_from": valid_from,
        "retention_mode": retention_mode,
        "expires_at": expires_at,
        "stamped_generation": stamped_generation,
        "canonical_key": canonical_key,
        "scope": scope,
        "scope_id": scope_id,
        "current_generation": current_generation,
        "has_unresolved_conflict": has_unresolved_conflict,
        "has_valid_evidence": has_valid_evidence,
    }


def _store_with_mock_rows(rows, owner="user_123"):
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    def _mock_execute(statement, *args, **kwargs):
        res = MagicMock()
        res.scalar.return_value = owner
        res.mappings.return_value.all.return_value = rows
        return res

    mock_conn.execute.side_effect = _mock_execute
    return PostgresMemoryStore(mock_engine)


def test_store_returns_empty_tuple_when_requested_keys_empty():
    mock_engine = MagicMock()
    store = PostgresMemoryStore(mock_engine)
    request = MemoryReadRequest(owner_user_id="user_123", requested_keys=())
    result = store.list_storage_scoped(request)
    assert result == ()
    mock_engine.connect.assert_not_called()


def test_store_projects_canonical_key_and_distinct_generations():
    # Stamped generation from version (1), current generation from assertion (2)
    fake_row = _make_fake_row(
        stamped_generation=1,
        current_generation=2,
        canonical_key="travel.preference.hotel_atmosphere",
    )
    store = _store_with_mock_rows([fake_row])
    request = MemoryReadRequest(
        owner_user_id="user_123",
        requested_keys=("travel.preference.hotel_atmosphere",),
    )
    results = store.list_storage_scoped(request)
    assert len(results) == 1
    row = results[0]
    assert row.canonical_key == "travel.preference.hotel_atmosphere"
    assert row.stamped_generation == 1
    assert row.current_generation == 2


def test_store_coerces_database_strings_to_domain_enums():
    fake_row = _make_fake_row(
        scope="conversation",
        authority="explicit_statement",
        retention_mode="conversation_bound",
        status="active",
        sensitivity="ordinary_personal",
    )
    store = _store_with_mock_rows([fake_row])
    request = MemoryReadRequest(
        owner_user_id="user_123",
        requested_keys=("travel.preference.hotel_atmosphere",),
    )
    row = store.list_storage_scoped(request)[0]
    assert row.scope is MemoryScope.CONVERSATION
    assert row.authority is Authority.EXPLICIT_STATEMENT
    assert row.retention_mode is RetentionMode.CONVERSATION_BOUND
    assert row.status is VersionStatus.ACTIVE
    assert row.sensitivity is SensitivityBand.ORDINARY_PERSONAL


def test_store_reconstructs_set_values_as_immutable_tuples():
    fake_row = _make_fake_row(
        canonical_key="travel.preference.transport_mode",
        value_payload={"normalized_value": ["flight", "train"]},
    )
    store = _store_with_mock_rows([fake_row])
    request = MemoryReadRequest(
        owner_user_id="user_123",
        requested_keys=("travel.preference.transport_mode",),
    )
    row = store.list_storage_scoped(request)[0]
    assert isinstance(row.normalized_value, tuple)
    assert row.normalized_value == ("flight", "train")


def test_store_projects_unresolved_conflict_flag():
    fake_row = _make_fake_row(has_unresolved_conflict=True)
    store = _store_with_mock_rows([fake_row])
    request = MemoryReadRequest(
        owner_user_id="user_123",
        requested_keys=("travel.preference.hotel_atmosphere",),
    )
    row = store.list_storage_scoped(request)[0]
    assert row.unresolved_conflict is True


def test_store_source_validity_user_durable_is_not_required():
    fake_row = _make_fake_row(
        retention_mode="user_durable",
        has_valid_evidence=False,  # Even with false evidence, user_durable is NOT_REQUIRED
    )
    store = _store_with_mock_rows([fake_row])
    request = MemoryReadRequest(
        owner_user_id="user_123",
        requested_keys=("travel.preference.hotel_atmosphere",),
    )
    row = store.list_storage_scoped(request)[0]
    assert row.source_validity is SourceValidity.NOT_REQUIRED


def test_store_source_validity_source_bound_with_evidence():
    fake_row_valid = _make_fake_row(
        retention_mode="source_bound",
        has_valid_evidence=True,
    )
    store_valid = _store_with_mock_rows([fake_row_valid])
    request = MemoryReadRequest(
        owner_user_id="user_123",
        requested_keys=("travel.preference.hotel_atmosphere",),
    )
    row_valid = store_valid.list_storage_scoped(request)[0]
    assert row_valid.source_validity is SourceValidity.VALID

    fake_row_invalid = _make_fake_row(
        retention_mode="source_bound",
        has_valid_evidence=False,
    )
    store_invalid = _store_with_mock_rows([fake_row_invalid])
    row_invalid = store_invalid.list_storage_scoped(request)[0]
    assert row_invalid.source_validity is SourceValidity.INVALID
