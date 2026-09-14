"""Tenant-scoped physical projection for semantic Memory reads."""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import exists, select
from sqlalchemy.engine import Engine

from backend.memory.lifecycle import SourceValidity
from backend.memory.read_models import MemoryReadRequest, StoredMemoryRow
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryScope,
    NormalizedSemanticValue,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
)
from backend.memory.write_pipeline.postgres import (
    assertions_table,
    evidence_table,
    versions_table,
)
from backend.storage.postgres import require_tenant_context, set_tenant


class PostgresMemoryStore:
    """Projects physical memory rows for an owner under tenant-level isolation.

    Owns only physical query projection and type coercion back to domain enums
    and immutable tuples. Never computes read eligibility verdicts; that belongs
    exclusively to MemoryLifecyclePolicy inside MemoryReadEngine.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_storage_scoped(
        self, request: MemoryReadRequest
    ) -> Sequence[StoredMemoryRow]:
        if not request.requested_keys:
            return ()

        with self._engine.connect() as connection:
            set_tenant(connection, request.owner_user_id)
            require_tenant_context(connection)

            has_valid_evidence = exists(
                select(evidence_table.c.evidence_id).where(
                    evidence_table.c.assertion_id == versions_table.c.assertion_id,
                    evidence_table.c.invalidated_at.is_(None),
                )
            ).label("has_valid_evidence")

            query = (
                select(
                    versions_table.c.version_id,
                    versions_table.c.owner_user_id,
                    versions_table.c.value_payload,
                    versions_table.c.authority,
                    versions_table.c.sensitivity,
                    versions_table.c.status,
                    versions_table.c.valid_from,
                    versions_table.c.retention_mode,
                    versions_table.c.expires_at,
                    versions_table.c.suppression_generation.label("stamped_generation"),
                    assertions_table.c.canonical_key,
                    assertions_table.c.scope,
                    assertions_table.c.scope_id,
                    assertions_table.c.suppression_generation.label("current_generation"),
                    assertions_table.c.has_unresolved_conflict,
                    has_valid_evidence,
                )
                .select_from(
                    versions_table.join(
                        assertions_table,
                        versions_table.c.assertion_id == assertions_table.c.assertion_id,
                    )
                )
                .where(
                    versions_table.c.owner_user_id == request.owner_user_id,
                    assertions_table.c.canonical_key.in_(request.requested_keys),
                )
            )

            rows = connection.execute(query).mappings().all()

            results: list[StoredMemoryRow] = []
            for r in rows:
                raw_val = (
                    r["value_payload"].get("normalized_value")
                    if isinstance(r["value_payload"], dict)
                    else r["value_payload"]
                )
                normalized_value: NormalizedSemanticValue = (
                    tuple(raw_val) if isinstance(raw_val, list) else str(raw_val)
                )

                scope = MemoryScope(r["scope"])
                authority = Authority(r["authority"])
                retention_mode = RetentionMode(r["retention_mode"])
                status = VersionStatus(r["status"])
                sensitivity = SensitivityBand(r["sensitivity"])

                if retention_mode is RetentionMode.USER_DURABLE:
                    source_validity = SourceValidity.NOT_REQUIRED
                elif r["has_valid_evidence"]:
                    source_validity = SourceValidity.VALID
                else:
                    source_validity = SourceValidity.INVALID

                results.append(
                    StoredMemoryRow(
                        version_id=str(r["version_id"]),
                        canonical_key=str(r["canonical_key"]),
                        normalized_value=normalized_value,
                        owner_user_id=str(r["owner_user_id"]),
                        scope=scope,
                        scope_id=str(r["scope_id"]),
                        authority=authority,
                        valid_from=r["valid_from"],
                        retention_mode=retention_mode,
                        stamped_generation=int(r["stamped_generation"]),
                        current_generation=int(r["current_generation"]),
                        status=status,
                        sensitivity=sensitivity,
                        source_validity=source_validity,
                        expires_at=r["expires_at"],
                        unresolved_conflict=bool(r["has_unresolved_conflict"]),
                    )
                )

            return tuple(results)
