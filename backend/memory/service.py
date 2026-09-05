"""Memory shadow-extraction and promotion use cases for milestones R5 and R6.

Per ADR 0006 the service owns provenance validation, extraction
orchestration, run-count accuracy, and controlled errors. Per ADR 0007 it
additionally owns candidate-to-record promotion behind the same provenance
boundary. It depends on the memory contracts, the memory repository
interface, the conversation repository interface, and the workspace
repository interface only. It never imports RAG, orchestration, FastAPI, or
SQLite.

Provenance is enforced before extraction: the workspace must exist, the
conversation must exist and belong to that workspace, and the conversation
must be active. Role and trace gating stays in the policy, so excluded or
non-user turns become explicit rejected candidates rather than silent gaps.

Message and candidate content passes through this module and is never
logged or placed inside an error.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from backend.conversations.models import ConversationRetentionState
from backend.conversations.service import (
    ConversationNotFoundError,
    WorkspaceNotFoundError,
)
from backend.memory.extraction import MemoryExtractor, RuleBasedMemoryExtractor
from backend.memory.models import (
    MemoryCandidate,
    MemoryCandidateStatus,
    MemoryExtractionRun,
    MemoryExtractionTrigger,
    MemoryPromotionResult,
    MemoryPromotionRun,
    MemoryRecord,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryRunStatus,
    MemorySourceMessage,
    MemoryValidationError,
    PromotionSkipCount,
    PromotionSkipReason,
    generate_memory_candidate_id,
    generate_memory_promotion_run_id,
    generate_memory_record_id,
    generate_memory_run_id,
    require_text,
    utc_now,
)
from backend.memory.policy import MemoryPolicy
from backend.memory.promotion import MemoryPromotionPolicy
from backend.memory.repository import MemoryRepository

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from backend.conversations.repository import ConversationRepository
    from backend.workspaces.repository import WorkspaceRepository

logger = logging.getLogger("travel_agent_memory")

EXTRACTION_FAILED_REASON = "extraction_failed"
"""Controlled failure label for a run whose extractor raised."""

_HISTORY_PAGE_SIZE = 200
"""Message page size matching the conversation history maximum."""


class MemoryServiceError(Exception):
    """A memory use case could not complete.

    Messages raised as this type carry identifiers and controlled labels
    only, never message or candidate content.
    """


class MemoryScopeMismatchError(MemoryServiceError):
    """A conversation or run does not belong to the requested workspace."""


class MemoryRunNotFoundError(MemoryServiceError):
    """The referenced memory extraction run does not exist."""


class MemoryService:
    """Run shadow extraction and inspect candidate evidence behind contracts."""

    def __init__(
        self,
        memory_repository: MemoryRepository,
        conversation_repository: "ConversationRepository",
        workspace_repository: "WorkspaceRepository",
        extractor: MemoryExtractor | None = None,
        policy: MemoryPolicy | None = None,
        promotion_policy: MemoryPromotionPolicy | None = None,
    ) -> None:
        self._memory = memory_repository
        self._conversations = conversation_repository
        self._workspaces = workspace_repository
        self._extractor = extractor or RuleBasedMemoryExtractor()
        self._policy = policy or MemoryPolicy()
        self._promotion = promotion_policy or MemoryPromotionPolicy()

    def run_conversation_extraction(
        self,
        workspace_id: str,
        conversation_id: str,
        trigger: MemoryExtractionTrigger | str = MemoryExtractionTrigger.MANUAL,
    ) -> MemoryExtractionRun:
        """Extract shadow candidates for one conversation and persist the run.

        Raises:
            MemoryValidationError: An identifier is blank, the trigger is
                ungoverned, or the conversation is not active.
            WorkspaceNotFoundError: The workspace does not exist.
            ConversationNotFoundError: The conversation does not exist.
            MemoryScopeMismatchError: The conversation belongs elsewhere.
            MemoryServiceError: Extraction failed after a failed run was
                recorded, or storage failed.
        """
        workspace_id = require_text(workspace_id, "workspace_id")
        conversation_id = require_text(conversation_id, "conversation_id")
        resolved_trigger = self._coerce_trigger(trigger)

        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError("The parent workspace does not exist.")
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("The conversation does not exist.")
        if conversation.workspace_id != workspace_id:
            raise MemoryScopeMismatchError(
                f"The conversation '{conversation_id}' does not belong to "
                f"workspace '{workspace_id}'."
            )
        if conversation.retention_state is not ConversationRetentionState.ACTIVE:
            raise MemoryValidationError(
                "Memory extraction requires an active conversation."
            )

        source_messages = self._eligible_source_messages(workspace_id, conversation_id)
        started_at = utc_now()
        try:
            drafts = self._extractor.extract(source_messages)
        except Exception as error:
            logger.error(
                "memory.extraction failed workspace_id=%s conversation_id=%s "
                "failure_class=%s",
                workspace_id,
                conversation_id,
                type(error).__name__,
            )
            failed = MemoryExtractionRun(
                run_id=generate_memory_run_id(),
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                trigger=resolved_trigger,
                extractor_id=self._extractor_id(),
                policy_id=self._policy_id(),
                status=MemoryRunStatus.FAILED,
                started_at=started_at,
                finished_at=utc_now(),
                candidate_count=0,
                accepted_count=0,
                rejected_count=0,
                needs_user_action_count=0,
                invalid_count=0,
                failure_reason=EXTRACTION_FAILED_REASON,
            )
            self._memory.create_run(failed)
            raise MemoryServiceError("Memory extraction could not complete.") from error

        decided = [self._policy.evaluate(draft) for draft in drafts]
        accepted = sum(
            1 for item in decided if item.status is MemoryCandidateStatus.ACCEPTED
        )
        rejected = sum(
            1 for item in decided if item.status is MemoryCandidateStatus.REJECTED
        )
        needs_action = sum(
            1
            for item in decided
            if item.status is MemoryCandidateStatus.NEEDS_USER_ACTION
        )
        invalid = sum(
            1 for item in decided if item.status is MemoryCandidateStatus.INVALID
        )
        status = (
            MemoryRunStatus.COMPLETED
            if rejected == 0 and needs_action == 0 and invalid == 0
            else MemoryRunStatus.COMPLETED_WITH_REJECTIONS
        )
        finished_at = utc_now()
        run = MemoryExtractionRun(
            run_id=generate_memory_run_id(),
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            trigger=resolved_trigger,
            extractor_id=self._extractor_id(),
            policy_id=self._policy_id(),
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            candidate_count=len(decided),
            accepted_count=accepted,
            rejected_count=rejected,
            needs_user_action_count=needs_action,
            invalid_count=invalid,
            failure_reason=None,
        )
        persisted = self._memory.create_run(run)
        self._memory.create_candidates(
            [
                self._to_candidate(persisted.run_id, finished_at, item)
                for item in decided
            ]
        )
        logger.info(
            "memory.extraction completed run_id=%s workspace_id=%s "
            "conversation_id=%s accepted=%s rejected=%s needs_user_action=%s "
            "invalid=%s",
            persisted.run_id,
            workspace_id,
            conversation_id,
            accepted,
            rejected,
            needs_action,
            invalid,
        )
        return persisted

    def promote_workspace(
        self,
        workspace_id: str,
        conversation_id: Optional[str] = None,
        trigger: MemoryExtractionTrigger | str = MemoryExtractionTrigger.MANUAL,
    ) -> MemoryPromotionResult:
        """Promote eligible shadow candidates into answer-eligible records.

        Every candidate in scope is assessed; ineligible ones contribute
        controlled skip reasons and write nothing. Promoted corrections
        suppress their supersession targets, which the repository flips to
        `superseded` in the same use case.

        Raises:
            MemoryValidationError: An identifier is blank or the trigger is
                ungoverned.
            WorkspaceNotFoundError: The workspace does not exist.
            ConversationNotFoundError: The conversation does not exist.
            MemoryScopeMismatchError: The conversation belongs elsewhere.
            MemoryServiceError: Storage failed.
        """
        workspace_id = require_text(workspace_id, "workspace_id")
        if conversation_id is not None:
            conversation_id = require_text(conversation_id, "conversation_id")
        resolved_trigger = self._coerce_trigger(trigger)
        self._require_scope(workspace_id, conversation_id)

        workspace = self._workspaces.get(workspace_id)
        assert workspace is not None  # checked by _require_scope
        candidates = self._memory.list_candidates(
            workspace_id=workspace_id, conversation_id=conversation_id
        )
        active_records = self._memory.list_records(
            owner_user_id=workspace.owner_user_id,
            status=MemoryRecordStatus.ACTIVE,
        )

        started_at = utc_now()
        assessments = []
        for candidate in candidates:
            conversation = self._conversations.get(candidate.conversation_id)
            message_exists = (
                self._conversations.get_message(candidate.source_message_id) is not None
            )
            assessments.append(
                self._promotion.assess(
                    candidate,
                    workspace=workspace,
                    conversation=conversation,
                    message_exists=message_exists,
                    active_records=active_records,
                )
            )

        moment = utc_now()
        created: list[MemoryRecord] = []
        supersede_ids: list[str] = []
        multi_target_corrections = 0
        for candidate, assessment in zip(candidates, assessments):
            if assessment.outcome is not PromotionSkipReason.PROMOTED:
                continue
            assert assessment.scope_id is not None  # set for every promotion
            created.append(
                MemoryRecord(
                    memory_id=generate_memory_record_id(),
                    source_candidate_id=candidate.candidate_id,
                    workspace_id=candidate.workspace_id,
                    conversation_id=candidate.conversation_id,
                    source_message_id=candidate.source_message_id,
                    source_sequence=candidate.source_sequence,
                    owner_user_id=workspace.owner_user_id,
                    scope=MemoryRecordScope(candidate.proposed_scope.value),
                    scope_id=assessment.scope_id,
                    memory_type=candidate.proposed_type.value,  # type: ignore[arg-type]
                    status=MemoryRecordStatus.ACTIVE,
                    text=candidate.text,
                    confidence=candidate.confidence,
                    sensitivity_label=candidate.sensitivity_label,
                    supersedes_memory_id=(
                        assessment.superseded_ids[0]
                        if assessment.superseded_ids
                        else None
                    ),
                    created_at=moment,
                    updated_at=moment,
                    expires_at=None,
                )
            )
            supersede_ids.extend(assessment.superseded_ids)
            if len(assessment.superseded_ids) > 1:
                multi_target_corrections += 1
        persisted_records = self._memory.create_records(created)
        if supersede_ids:
            self._memory.mark_records_superseded(supersede_ids)

        skip_counter: dict[PromotionSkipReason, int] = {}
        for assessment in assessments:
            if assessment.outcome is PromotionSkipReason.PROMOTED:
                continue
            skip_counter[assessment.outcome] = (
                skip_counter.get(assessment.outcome, 0) + 1
            )
        if multi_target_corrections:
            skip_counter[PromotionSkipReason.CORRECTION_SUPERSEDES_MULTIPLE] = (
                multi_target_corrections
            )
        skip_reasons = tuple(
            PromotionSkipCount(reason, skip_counter[reason])
            for reason in sorted(skip_counter, key=lambda item: item.value)
        )
        run = MemoryPromotionRun(
            promotion_run_id=generate_memory_promotion_run_id(),
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            source_candidate_count=len(candidates),
            promoted_count=len(persisted_records),
            skipped_count=len(candidates) - len(persisted_records),
            skip_reasons=skip_reasons,
            started_at=started_at,
            finished_at=utc_now(),
        )
        persisted_run = self._memory.create_promotion_run(run)
        logger.info(
            "memory.promotion completed promotion_run_id=%s workspace_id=%s "
            "promoted=%s skipped=%s",
            persisted_run.promotion_run_id,
            workspace_id,
            len(persisted_records),
            len(candidates) - len(persisted_records),
        )
        return MemoryPromotionResult(
            promotion_run_id=persisted_run.promotion_run_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            source_candidate_count=len(candidates),
            promoted_count=len(persisted_records),
            skipped_count=len(candidates) - len(persisted_records),
            skip_reasons=skip_reasons,
            promoted_memory_ids=tuple(record.memory_id for record in persisted_records),
            started_at=persisted_run.started_at,
            finished_at=persisted_run.finished_at,
        )

    def list_runs(
        self, workspace_id: str, conversation_id: Optional[str] = None
    ) -> tuple[MemoryExtractionRun, ...]:
        """Return extraction runs for one workspace, newest first."""
        workspace_id = require_text(workspace_id, "workspace_id")
        if conversation_id is not None:
            conversation_id = require_text(conversation_id, "conversation_id")
        self._require_scope(workspace_id, conversation_id)
        return self._memory.list_runs(workspace_id, conversation_id)

    def list_candidates(
        self,
        workspace_id: str,
        conversation_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> tuple[MemoryCandidate, ...]:
        """Return candidate evidence for the supplied workspace filters."""
        workspace_id = require_text(workspace_id, "workspace_id")
        if conversation_id is not None:
            conversation_id = require_text(conversation_id, "conversation_id")
        if run_id is not None:
            run_id = require_text(run_id, "run_id")
        self._require_scope(workspace_id, conversation_id)
        if run_id is not None:
            self._require_run(workspace_id, conversation_id, run_id)
        return self._memory.list_candidates(run_id, workspace_id, conversation_id)

    def _require_scope(self, workspace_id: str, conversation_id: Optional[str]) -> None:
        if self._workspaces.get(workspace_id) is None:
            raise WorkspaceNotFoundError("The parent workspace does not exist.")
        if conversation_id is None:
            return
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("The conversation does not exist.")
        if conversation.workspace_id != workspace_id:
            raise MemoryScopeMismatchError(
                f"The conversation '{conversation_id}' does not belong to "
                f"workspace '{workspace_id}'."
            )

    def _require_run(
        self, workspace_id: str, conversation_id: Optional[str], run_id: str
    ) -> None:
        scoped = self._memory.list_runs(workspace_id, conversation_id)
        if any(item.run_id == run_id for item in scoped):
            return
        if self._memory.list_candidates(run_id=run_id):
            raise MemoryScopeMismatchError(
                f"The extraction run '{run_id}' does not belong to workspace "
                f"'{workspace_id}'."
            )
        raise MemoryRunNotFoundError("The memory extraction run does not exist.")

    def _eligible_source_messages(
        self, workspace_id: str, conversation_id: str
    ) -> list[MemorySourceMessage]:
        """Collect non-empty messages with their trace fields preserved.

        Role and trace gating stays in the policy: an excluded or non-user
        turn becomes an explicit rejected candidate instead of a silent gap.
        """
        collected: list[MemorySourceMessage] = []
        after_sequence: int | None = None
        while True:
            page = self._conversations.list_messages(
                conversation_id, after_sequence, _HISTORY_PAGE_SIZE
            )
            if not page:
                break
            for message in page:
                if message.content.strip():
                    collected.append(
                        MemorySourceMessage(
                            message_id=message.message_id,
                            conversation_id=conversation_id,
                            workspace_id=workspace_id,
                            sequence=message.sequence,
                            role=getattr(message.role, "value", message.role),
                            source=getattr(message.source, "value", message.source),
                            trace_visibility=getattr(
                                message.trace_visibility,
                                "value",
                                message.trace_visibility,
                            ),
                            content=message.content,
                            created_at=message.created_at,
                        )
                    )
            if len(page) < _HISTORY_PAGE_SIZE:
                break
            after_sequence = page[-1].sequence
        return collected

    def _to_candidate(self, run_id: str, created_at, decided) -> MemoryCandidate:
        if decided.status is None or decided.reason is None:
            raise MemoryServiceError(
                "Memory policy returned a candidate without a decision."
            )
        return MemoryCandidate(
            candidate_id=generate_memory_candidate_id(),
            run_id=run_id,
            workspace_id=decided.workspace_id,
            conversation_id=decided.conversation_id,
            source_message_id=decided.source_message_id,
            source_sequence=decided.source_sequence,
            proposed_scope=decided.proposed_scope,
            proposed_type=decided.proposed_type,
            status=decided.status,
            confidence=decided.confidence,
            sensitivity_label=decided.sensitivity_label,
            text=decided.text,
            evidence_summary=decided.evidence_summary,
            reason=decided.reason,
            created_at=created_at,
        )

    def _coerce_trigger(self, trigger: MemoryExtractionTrigger | str):
        if isinstance(trigger, MemoryExtractionTrigger):
            return trigger
        try:
            return MemoryExtractionTrigger(trigger)
        except ValueError:
            allowed = sorted(item.value for item in MemoryExtractionTrigger)
            raise MemoryValidationError(
                f"Memory field 'trigger' must be one of {allowed}."
            ) from None

    def _extractor_id(self) -> str:
        return str(getattr(self._extractor, "extractor_id", "custom-extractor"))

    def _policy_id(self) -> str:
        return str(getattr(self._policy, "policy_id", "custom-policy"))
