"""Lifecycle-governed exact-key semantic Memory selection."""
from datetime import datetime, timezone
from backend.memory.lifecycle import LifecycleFacts, LifecycleStage, MemoryLifecyclePolicy
from backend.memory.read_models import AbstentionReason, MemoryReadRequest, MemorySelection, MemoryStore, SelectedMemory, StoredMemoryRow

class MemoryReadEngine:
    def __init__(self, store: MemoryStore, lifecycle: MemoryLifecyclePolicy | None = None, clock=None) -> None:
        self._store = store
        self._lifecycle = lifecycle or MemoryLifecyclePolicy()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def select(self, request: MemoryReadRequest) -> MemorySelection:
        return self._select_rows(request, tuple(self._store.list_storage_scoped(request)), self._clock())

    def _select_rows(self, request: MemoryReadRequest, rows: tuple[StoredMemoryRow, ...], evaluated_at: datetime) -> MemorySelection:
        if not request.requested_keys:
            return MemorySelection((), AbstentionReason.NO_REQUESTED_KEYS)
        conflict_keys = {r.canonical_key for r in rows if r.unresolved_conflict and r.canonical_key in request.requested_keys}
        eligible = []
        for row in rows:
            if row.owner_user_id != request.owner_user_id or row.canonical_key not in request.requested_keys or row.canonical_key in conflict_keys:
                continue
            if row.scope.value == "conversation" and row.scope_id != request.conversation_id:
                continue
            decision = self._lifecycle.evaluate(stage=LifecycleStage.READ, facts=LifecycleFacts(
                retention_mode=row.retention_mode, stamped_generation=row.stamped_generation,
                current_generation=row.current_generation, scope=row.scope, sensitivity=row.sensitivity,
                source_validity=row.source_validity, status=row.status, expires_at=row.expires_at,
                evaluated_at=evaluated_at if row.expires_at else None,
            ))
            if decision.eligible:
                eligible.append(row)
        # A current-conversation value shadows only the same user-scoped key.
        conversation_keys = {r.canonical_key for r in eligible if r.scope.value == "conversation"}
        eligible = [r for r in eligible if not (r.scope.value == "user" and r.canonical_key in conversation_keys)]
        eligible.sort(key=lambda r: (-r.valid_from.timestamp(), r.canonical_key, r.version_id))
        selected = tuple(SelectedMemory(r.version_id, r.canonical_key, r.normalized_value, r.scope, r.scope_id, r.authority, r.valid_from) for r in eligible[:request.max_selected])
        return MemorySelection(selected, None if selected else AbstentionReason.NO_ELIGIBLE_MEMORY)
