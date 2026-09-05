"""Memory storage interface and repository error types for milestone R5.

Per ADR 0006 product code depends on this interface rather than on SQLite
details. Route handlers and the memory service must not embed table DDL, SQL
statements, path creation, or connection management.
"""

from __future__ import annotations

from typing import Optional, Protocol, Sequence

from backend.memory.models import (
    MemoryCandidate,
    MemoryExtractionRun,
    MemoryPromotionRun,
    MemoryRecord,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemorySelectionTrace,
)


class MemoryRepositoryError(Exception):
    """Base class for memory storage failures."""


class MemoryAlreadyExistsError(MemoryRepositoryError):
    """A run or candidate with the same identity is already recorded."""


class MemoryStorageError(MemoryRepositoryError):
    """Storage could not complete the requested memory operation.

    Messages raised as this type are safe for a controlled HTTP 500 response.
    They must not carry local filesystem paths, full SQL text, credentials,
    or message and candidate content.
    """


class MemoryRepository(Protocol):
    """Persistence boundary for shadow memory candidate evidence."""

    def create_run(self, run: MemoryExtractionRun) -> MemoryExtractionRun:
        """Persist a new extraction run and return the stored record.

        Raises:
            MemoryAlreadyExistsError: The run identity is already used.
            MemoryStorageError: Storage failed for another reason.
        """
        ...

    def create_candidates(
        self, candidates: Sequence[MemoryCandidate]
    ) -> tuple[MemoryCandidate, ...]:
        """Persist candidate rows atomically and return them in input order.

        Raises:
            MemoryAlreadyExistsError: A candidate identity or the governed
                per-run uniqueness tuple is already recorded.
            MemoryStorageError: Storage failed for another reason, including
                a candidate whose parent run does not exist.
        """
        ...

    def list_runs(
        self, workspace_id: str, conversation_id: str | None = None
    ) -> tuple[MemoryExtractionRun, ...]:
        """Return runs for one workspace, newest first.

        Raises:
            MemoryStorageError: Storage failed.
        """
        ...

    def list_candidates(
        self,
        run_id: str | None = None,
        workspace_id: str | None = None,
        conversation_id: str | None = None,
    ) -> tuple[MemoryCandidate, ...]:
        """Return candidates matching every supplied filter.

        With `run_id`, order is `source_sequence` ascending, then
        `candidate_id` ascending. Without it, candidates group by parent run
        newest first, then follow the same in-run order.

        Raises:
            MemoryStorageError: Storage failed.
        """
        ...

    def create_promotion_run(self, run: MemoryPromotionRun) -> MemoryPromotionRun:
        """Persist a new promotion run and return the stored record.

        Raises:
            MemoryAlreadyExistsError: The run identity is already used.
            MemoryStorageError: Storage failed for another reason.
        """
        ...

    def list_promotion_runs(
        self,
        workspace_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> tuple[MemoryPromotionRun, ...]:
        """Return promotion runs for the supplied filters, newest first.

        Raises:
            MemoryStorageError: Storage failed.
        """
        ...

    def create_records(
        self, records: Sequence[MemoryRecord]
    ) -> tuple[MemoryRecord, ...]:
        """Persist answer-eligible records atomically, in input order.

        Raises:
            MemoryAlreadyExistsError: A record identity or a source
                candidate is already recorded.
            MemoryStorageError: Storage failed for another reason.
        """
        ...

    def list_records(
        self,
        workspace_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        owner_user_id: Optional[str] = None,
        scope: Optional[MemoryRecordScope] = None,
        status: Optional[MemoryRecordStatus] = None,
    ) -> tuple[MemoryRecord, ...]:
        """Return records matching every supplied filter, oldest first.

        Order is `created_at` ascending, then `memory_id` ascending, so age
        comparisons read in stored order.

        Raises:
            MemoryStorageError: Storage failed.
        """
        ...

    def mark_records_superseded(self, memory_ids: Sequence[str]) -> int:
        """Flip active records to `superseded` and return the flipped count.

        Only rows still `active` move; unknown or already-superseded
        identities contribute zero. Promotion resolves targets before
        calling, so this method performs no scope or age reasoning.

        Raises:
            MemoryStorageError: Storage failed.
        """
        ...

    def write_retrieval_event(
        self, trace: MemorySelectionTrace
    ) -> MemorySelectionTrace:
        """Persist one retrieval event and return it.

        Raises:
            MemoryAlreadyExistsError: The trace identity is already used.
            MemoryStorageError: Storage failed for another reason.
        """
        ...

    def list_retrieval_events(
        self,
        workspace_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> tuple[MemorySelectionTrace, ...]:
        """Return retrieval events for the supplied filters, newest first.

        Raises:
            MemoryStorageError: Storage failed.
        """
        ...
