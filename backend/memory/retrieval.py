"""Deterministic lexical memory retrieval for milestone R6.

Retrieval selects active, unexpired, non-sensitive records whose scope
matches the current owner, workspace, or conversation, then ranks them by
deterministic token overlap with the turn query. Records that are direct
active corrections are selected even with zero overlap, per retrieval rule
9. There is no semantic search, no embedding, and no Chroma involvement:
auditability outranks recall in R6.

The service reads records through the repository interface and never logs
content. Ranking ties break by `memory_id` ascending so repeated turns
select identically.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from backend.memory.models import (
    MemoryRecord,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryRecordType,
    MemorySelection,
    MemorySelectionReason,
    SensitivityLabel,
    utc_now,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from backend.memory.repository import MemoryRepository

logger = logging.getLogger("travel_agent_memory")

MEMORY_MAX_SELECTED = 5
"""Default cap on selected memories per turn per the approved R6 spec."""

_RETRIEVABLE_SENSITIVITIES = frozenset(
    {SensitivityLabel.NONE, SensitivityLabel.PERSONAL}
)

_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_TOKEN_PATTERN.findall(text.lower()))


def _lexical_score(query_tokens: frozenset[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    return len(query_tokens & _tokens(text)) / len(query_tokens)


class MemoryRetrievalService:
    """Select in-scope active memory records for one turn."""

    def __init__(
        self,
        memory_repository: "MemoryRepository",
        max_selected: int = MEMORY_MAX_SELECTED,
    ) -> None:
        self._memory = memory_repository
        self._max_selected = max_selected

    def select_memories(
        self,
        *,
        owner_user_id: str,
        workspace_id: str,
        conversation_id: str,
        query: str,
        max_selected: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> tuple[MemorySelection, ...]:
        """Return up to `max_selected` selections in deterministic rank order.

        Only active, unexpired, non-sensitive records in a matching scope are
        eligible. A record is selected when its lexical score is above zero
        or it is a direct active correction.
        """
        moment = now or utc_now()
        limit = self._max_selected if max_selected is None else max_selected
        query_tokens = _tokens(query)
        ranked: list[tuple[float, str, MemoryRecord]] = []
        for record in self._eligible_records(owner_user_id, moment):
            if not self._scope_matches(
                record, owner_user_id, workspace_id, conversation_id
            ):
                continue
            if record.memory_type is MemoryRecordType.CORRECTION:
                ranked.append((0.0, record.memory_id, record))
                continue
            score = _lexical_score(query_tokens, record.text)
            if score > 0.0:
                ranked.append((score, record.memory_id, record))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return tuple(
            MemorySelection(
                memory_id=record.memory_id,
                scope=record.scope,
                memory_type=record.memory_type,
                reason=(
                    MemorySelectionReason.ACTIVE_CORRECTION
                    if record.memory_type is MemoryRecordType.CORRECTION
                    else MemorySelectionReason.LEXICAL_MATCH
                ),
                score=score,
                text=record.text,
            )
            for score, _, record in ranked[:limit]
        )

    def _eligible_records(
        self, owner_user_id: str, moment: datetime
    ) -> tuple[MemoryRecord, ...]:
        records = self._memory.list_records(
            owner_user_id=owner_user_id, status=MemoryRecordStatus.ACTIVE
        )
        eligible = []
        for record in records:
            if record.status is not MemoryRecordStatus.ACTIVE:
                continue
            if record.sensitivity_label not in _RETRIEVABLE_SENSITIVITIES:
                continue
            if record.expires_at is not None and record.expires_at <= moment:
                continue
            eligible.append(record)
        logger.info(
            "memory.retrieval eligible owner_user_id=%s count=%s",
            owner_user_id,
            len(eligible),
        )
        return tuple(eligible)

    @staticmethod
    def _scope_matches(
        record: MemoryRecord,
        owner_user_id: str,
        workspace_id: str,
        conversation_id: str,
    ) -> bool:
        if record.scope is MemoryRecordScope.USER:
            return record.scope_id == owner_user_id
        if record.scope is MemoryRecordScope.WORKSPACE:
            return record.scope_id == workspace_id
        if record.scope is MemoryRecordScope.CONVERSATION:
            return record.scope_id == conversation_id
        return False
