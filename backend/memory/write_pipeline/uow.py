"""Memory write unit-of-work contract.

`MemoryWriteResult` lives here (not in the pure domain models) because
it describes a persistence outcome — stamped identifiers included —
while the domain package stays free of storage concepts. This module
imports the Child-2 contracts and the existing R9 security principal
only; it never touches SQLAlchemy, drivers, or the network, so the
protocol stays implementable against any backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.memory.write_pipeline.models import (
    MemoryChangeSet,
    MemoryDecisionDraft,
    MemoryEvidence,
    MemoryOperation,
)
from backend.security.models import AuthenticatedPrincipal


class MemoryWriteError(Exception):
    """A memory write could not complete. Messages carry identifiers and
    governed reason codes only, never memory content or credentials."""


class CrossOwnerDeniedError(MemoryWriteError):
    """The principal does not own the change, record, or idempotency key."""


class StaleVersionError(MemoryWriteError):
    """The expected current version no longer matches stored state."""


class ConcurrentWriteError(MemoryWriteError):
    """A concurrent writer won the assertion; re-resolve and retry."""


@dataclass(frozen=True)
class MemoryWriteResult:
    """One applied change: stamped identifiers plus the decided shape."""

    operation: MemoryOperation
    version_id: str | None
    superseded_version_ids: tuple[str, ...]
    reference_version_id: str | None
    decision_id: str | None
    reason: str


class MemoryUnitOfWork(Protocol):
    """Atomic, idempotent persistence boundary for resolved changes."""

    def apply_memory_change(
        self,
        change: MemoryChangeSet,
        principal: AuthenticatedPrincipal,
        *,
        evidence: tuple[MemoryEvidence, ...] = (),
        decision: MemoryDecisionDraft | None = None,
        idempotency_key: str | None = None,
        expected_version_id: str | None = None,
    ) -> MemoryWriteResult:
        """Apply one resolved change atomically and idempotently.

        `evidence` and `decision` drafts are persisted alongside the
        version mutation in the same transaction when the operation
        writes anything. `idempotency_key`, when given, deduplicates
        redelivery to one semantic outcome. `expected_version_id`, when
        given, must match the stored current version or the write is
        rejected without touching state.
        """
        ...
