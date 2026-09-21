"""Chat-native explicit memory actions handler and semantic proposal contracts.

Stage 2 explicit Remember, Correct, and Forget execution:
- Authoritative speech-act processing (EXPLICIT_REMEMBER, EXPLICIT_CORRECT, EXPLICIT_FORGET)
- Bounded to 8 registry-v2 keys using public registry APIs
- Pure semantic proposals without transaction/turn identity
- Snapshot-bound expected_version_id for optimistic concurrency
- Deterministic template acknowledgements (zero LLM repair calls)
- Governed source handling outcomes (EXPLICIT_APPLIED, EXPLICIT_REFUSED, EXPLICIT_NOOP, FORGET_APPLIED)
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Sequence

if TYPE_CHECKING:
    from backend.memory.commit_coordinators import ExplicitMemoryCommitRequest
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    SourceHandlingReason,
    SourceHandlingRecord,
)
from backend.security.models import AuthenticatedPrincipal
from backend.memory.write_pipeline.model_adapter import LLMProvider, extract_explicit
from backend.memory.write_pipeline.models import (
    Authority,
    Cardinality,
    MemoryCandidate,
    MemoryChangeSet,
    MemoryOperation,
    MemoryRelation,
    MemoryScope,
    MemoryVersion,
    SensitivityBand,
    assertion_identity,
    new_candidate_id,
)
from backend.memory.write_pipeline.registry import (
    RegistryValidationError,
    get_key_definition,
    is_known_key,
    normalize_value,
    registry_keys,
)
from backend.memory.write_pipeline.resolver import resolve_change
from backend.memory.write_pipeline.secrets import detect_prohibited_content
from backend.orchestration.dialogue_state import DialogueState
from backend.orchestration.turn_models import (
    DURABLE_ACTION_MODES,
    InteractionMode,
    TurnUnderstandingResult,
)

logger = logging.getLogger("travel_agent_memory_explicit_actions")

ActiveVersionProvider = Callable[[str, str], tuple[MemoryVersion, ...]]
GenerationProvider = Callable[[str, str], int]


def _matches_term(pattern: str, text: str) -> bool:
    """Check if pattern occurs in text as a boundary-delimited word or phrase.

    Supports optional English plural suffixes ('s', 'es') while preventing
    substring false matches such as 'bus' matching inside 'business'.
    """
    norm_pattern = pattern.replace("_", " ").strip().casefold()
    if not norm_pattern:
        return False
    regex = rf"(?<!\w){re.escape(norm_pattern)}(?:s|es)?(?!\w)"
    return bool(re.search(regex, text, re.IGNORECASE))


class ProposalOutcome(str, Enum):
    """Closed outcome vocabulary for an explicit memory action proposal."""

    MUTATION = "mutation"
    CLARIFICATION = "clarification"
    NOOP = "noop"


@dataclass(frozen=True)
class ExplicitMemoryProposal:
    """Semantic-only proposal for one explicit memory turn."""

    outcome: ProposalOutcome
    canonical_key: str | None = None
    change: MemoryChangeSet | None = None
    expected_version_id: str | None = None
    suppression_generation: int = 1
    acknowledgement_text: str = ""
    clarification_prompt: str | None = None
    reason: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def explicit_semantic_idempotency_key(
    *,
    source_message_id: str,
    owner_user_id: str,
    canonical_key: str,
    operation: str,
    normalized_value: str | tuple[str, ...] | list[str] | set[str],
    suppression_generation: int = 1,
    scope: str = "user",
    scope_id: str = "default",
    subject_key: str = "self",
) -> str:
    """Derive a stable, deterministic idempotency key for an explicit memory action.

    Derived strictly from stable source message ID + owner + assertion key/scope + operation + normalized value + generation.
    Excludes random candidate IDs, timestamps, or random evidence IDs.
    """
    if isinstance(normalized_value, (tuple, list, set)):
        val_str = ",".join(sorted(str(v) for v in normalized_value))
    else:
        val_str = str(normalized_value)

    material = "|".join(
        [
            source_message_id,
            owner_user_id,
            scope,
            scope_id,
            canonical_key,
            subject_key,
            val_str,
            operation,
            str(suppression_generation),
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return f"exp_{digest}"


INSPECT_UNAVAILABLE_REPLY = (
    "Tính năng xem ký ức chưa khả dụng ở giai đoạn này. "
    "Tôi chưa thể liệt kê những gì đã ghi nhớ."
)


@dataclass(frozen=True)
class ExplicitInspectResult:
    """Typed result from an explicit memory inspection."""

    reply: str
    delivered: bool


def format_inspect_reply(selection: Any) -> str:
    """Render a governed MemorySelection into human-readable text."""
    if not selection or not getattr(selection, "selected", ()):
        return "Hiện tại tôi chưa ghi nhớ thông tin nào về sở thích của bạn."
    lines = ["Dưới đây là các sở thích mà tôi đã ghi nhớ:"]
    for item in selection.selected:
        val_str = (
            ", ".join(str(v) for v in item.normalized_value)
            if isinstance(item.normalized_value, (tuple, list, set))
            else str(item.normalized_value)
        )
        scope_label = (
            "trong đoạn hội thoại này"
            if getattr(item.scope, "value", str(item.scope)) == "conversation"
            else "chung cho tài khoản của bạn"
        )
        lines.append(f"- {item.canonical_key}: {val_str} ({scope_label})")
    return "\n".join(lines)


def inspect_explicit_memory(
    read_engine: Any | None,
    *,
    owner_user_id: str,
    conversation_id: str | None = None,
    memory_read_enabled: bool = False,
) -> ExplicitInspectResult:
    """Read and format remembered preferences, or return controlled unavailable."""
    if not memory_read_enabled or read_engine is None:
        return ExplicitInspectResult(
            reply=INSPECT_UNAVAILABLE_REPLY,
            delivered=False,
        )
    from backend.memory.read_models import MemoryReadRequest

    req = MemoryReadRequest(
        owner_user_id=owner_user_id,
        conversation_id=conversation_id,
        requested_keys=registry_keys(),
        max_selected=8,
    )
    selection = read_engine.select(req)
    return ExplicitInspectResult(
        reply=format_inspect_reply(selection),
        delivered=True,
    )


def build_explicit_source_handling_record(
    *,
    source_outbox_id: str,
    source_message_id: str,
    outcome: SourceHandlingOutcome,
    reason_code: SourceHandlingReason = SourceHandlingReason.EXPLICIT_ACTION,
) -> SourceHandlingRecord:
    """Assemble one SourceHandlingRecord for an explicit turn."""
    return SourceHandlingRecord(
        source_outbox_id=source_outbox_id,
        source_message_id=source_message_id,
        family=MemoryFamily.SEMANTIC,
        outcome=outcome,
        reason_code=reason_code,
        recorded_at=datetime.now(timezone.utc),
    )


def build_explicit_commit_request(
    *,
    proposal: ExplicitMemoryProposal,
    principal: AuthenticatedPrincipal,
    conversation_id: str,
    user_message_id: str,
    assistant_message_id: str,
    expected_deletion_epoch: int,
    source_outbox_id: str,
    interaction_mode: InteractionMode | None = None,
) -> ExplicitMemoryCommitRequest:
    """Build an ExplicitMemoryCommitRequest from an explicit mutation proposal."""
    ch = proposal.change
    if ch is None:
        raise ValueError("Cannot build commit request for a proposal without change.")

    from backend.memory.commit_coordinators import ExplicitMemoryCommitRequest
    from backend.memory.write_pipeline.models import SourceValidity

    if (
        interaction_mode is InteractionMode.EXPLICIT_FORGET
        or ch.operation is MemoryOperation.REVOKE
    ):
        sh_outcome = SourceHandlingOutcome.FORGET_APPLIED
    else:
        sh_outcome = SourceHandlingOutcome.EXPLICIT_APPLIED

    sh_record = build_explicit_source_handling_record(
        source_outbox_id=source_outbox_id,
        source_message_id=user_message_id,
        outcome=sh_outcome,
        reason_code=SourceHandlingReason.EXPLICIT_ACTION,
    )

    if ch.new_version is not None:
        c_key = ch.new_version.canonical_key
        c_val = ch.new_version.normalized_value
    elif ch.superseded_version_ids:
        c_key = proposal.canonical_key or "unknown"
        c_val = "forget"
    else:
        c_key = proposal.canonical_key or "unknown"
        c_val = "unknown"

    owner_user_id = principal.owner_user_id
    idem_key = explicit_semantic_idempotency_key(
        owner_user_id=owner_user_id,
        source_message_id=user_message_id,
        canonical_key=c_key,
        operation=ch.operation.value,
        normalized_value=c_val,
        suppression_generation=proposal.suppression_generation,
    )

    return ExplicitMemoryCommitRequest(
        principal=principal,
        conversation_id=conversation_id,
        assistant_message_id=assistant_message_id,
        expected_deletion_epoch=expected_deletion_epoch,
        acknowledgement_text=proposal.acknowledgement_text or "Đã lưu!",
        change=ch,
        evidence=(),
        decision=None,
        idempotency_key=idem_key,
        expected_version_id=proposal.expected_version_id,
        source_validity=SourceValidity.NOT_REQUIRED,
        source_handling_record=sh_record,
    )


class ExplicitMemoryActionHandler:
    """Processes explicit Remember, Correct, and Forget turns into semantic proposals."""

    def __init__(
        self,
        active_version_provider: ActiveVersionProvider,
        provider: LLMProvider | None = None,
        generation_provider: GenerationProvider | None = None,
    ) -> None:
        self._active_version_provider = active_version_provider
        self._provider = provider
        self._generation_provider = generation_provider

    @staticmethod
    def inspect(
        read_engine: Any | None,
        *,
        owner_user_id: str,
        conversation_id: str | None = None,
        memory_read_enabled: bool = False,
    ) -> ExplicitInspectResult:
        """Inspect and format explicit preferences using governed read engine."""
        return inspect_explicit_memory(
            read_engine,
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            memory_read_enabled=memory_read_enabled,
        )

    @staticmethod
    def build_commit_request(
        *,
        proposal: ExplicitMemoryProposal,
        principal: AuthenticatedPrincipal,
        conversation_id: str,
        user_message_id: str,
        assistant_message_id: str,
        expected_deletion_epoch: int,
        source_outbox_id: str,
        interaction_mode: InteractionMode | None = None,
    ) -> ExplicitMemoryCommitRequest:
        """Build an ExplicitMemoryCommitRequest from an explicit proposal."""
        return build_explicit_commit_request(
            proposal=proposal,
            principal=principal,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            expected_deletion_epoch=expected_deletion_epoch,
            source_outbox_id=source_outbox_id,
            interaction_mode=interaction_mode,
        )

    def propose(
        self,
        understanding: TurnUnderstandingResult,
        state: DialogueState,
        *,
        owner_user_id: str,
        utterance: str | None = None,
        conversation_id: str | None = None,
    ) -> ExplicitMemoryProposal:
        """Produce a semantic proposal from explicit turn understanding and dialogue state."""
        # 1. Check inspect mode (read-only)
        if understanding.interaction_mode is InteractionMode.EXPLICIT_INSPECT:
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.NOOP,
                acknowledgement_text=(
                    "Tính năng xem lại sở thích đã lưu chưa hỗ trợ trong phiên bản này. "
                    "(Memory inspection is not yet available.)"
                ),
                reason="inspect_unavailable",
            )

        # 2. Check durable action mode authorization
        if understanding.interaction_mode not in DURABLE_ACTION_MODES:
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.NOOP,
                reason="not_durable_explicit_mode",
            )

        # 3. Check clarification need from understanding
        if understanding.needs_clarification:
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.CLARIFICATION,
                clarification_prompt=(
                    "Tôi chưa hiểu rõ yêu cầu của bạn. "
                    "Bạn có thể nói rõ hơn về sở thích bạn muốn ghi nhớ, sửa hay xóa không?"
                ),
                reason="ambiguous_speech_act",
            )

        # 4. Extract user utterance and conversation_id
        if utterance is None:
            user_msg = state.latest_user_turn
            utterance = user_msg.content if user_msg is not None else ""
        if not utterance or not utterance.strip():
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.NOOP,
                reason="empty_utterance",
            )

        conv_id = (
            conversation_id
            or (state.latest_user_turn.conversation_id if state.latest_user_turn else "")
        )

        # 5. Pre-scan for prohibited secrets (fail closed NOOP)
        if detect_prohibited_content(utterance) is not None:
            logger.warning(
                "Prohibited secret detected in explicit memory utterance; failing closed."
            )
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.NOOP,
                reason="prohibited_secret_detected",
            )

        # 6. Parse target key and value(s)
        canonical_key, raw_values = self._parse_target_key_and_values(
            utterance, understanding.interaction_mode
        )

        if not canonical_key or not is_known_key(canonical_key):
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.CLARIFICATION,
                clarification_prompt=(
                    "Tôi chưa xác định được thông tin hoặc sở thích bạn muốn lưu/sửa/xóa. "
                    "Bạn có thể nói rõ hơn không?"
                ),
                reason="unrecognized_or_unknown_key",
            )

        # 7. Snapshot lookup via read-only seam
        active_versions = self._active_version_provider(owner_user_id, canonical_key)
        expected_version_id = active_versions[-1].version_id if active_versions else None
        if self._generation_provider is not None:
            suppression_generation = self._generation_provider(owner_user_id, canonical_key)
        else:
            suppression_generation = (
                active_versions[-1].suppression_generation if active_versions else 1
            )
        defn = get_key_definition(canonical_key)
        is_set = defn.cardinality is Cardinality.SET

        # 8. Route according to interaction mode
        if understanding.interaction_mode is InteractionMode.EXPLICIT_FORGET:
            return self._propose_forget(
                canonical_key=canonical_key,
                raw_values=raw_values,
                is_set=is_set,
                active_versions=active_versions,
                expected_version_id=expected_version_id,
                owner_user_id=owner_user_id,
                conversation_id=conv_id,
                suppression_generation=suppression_generation,
            )

        if understanding.interaction_mode is InteractionMode.EXPLICIT_CORRECT:
            return self._propose_correct(
                canonical_key=canonical_key,
                raw_values=raw_values,
                is_set=is_set,
                active_versions=active_versions,
                expected_version_id=expected_version_id,
                owner_user_id=owner_user_id,
                conversation_id=conv_id,
                suppression_generation=suppression_generation,
            )

        # Default: EXPLICIT_REMEMBER
        return self._propose_remember(
            canonical_key=canonical_key,
            raw_values=raw_values,
            is_set=is_set,
            active_versions=active_versions,
            expected_version_id=expected_version_id,
            owner_user_id=owner_user_id,
            conversation_id=conv_id,
            suppression_generation=suppression_generation,
        )

    def _propose_remember(
        self,
        *,
        canonical_key: str,
        raw_values: Any,
        is_set: bool,
        active_versions: tuple[MemoryVersion, ...],
        expected_version_id: str | None,
        owner_user_id: str,
        conversation_id: str = "",
        suppression_generation: int = 1,
    ) -> ExplicitMemoryProposal:
        try:
            norm_val = normalize_value(canonical_key, raw_values)
        except RegistryValidationError:
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.CLARIFICATION,
                canonical_key=canonical_key,
                suppression_generation=suppression_generation,
                clarification_prompt=f"Giá trị bạn cung cấp không thuộc danh mục hợp lệ cho {canonical_key}.",
                reason="invalid_value_for_key",
            )

        candidate = self._build_candidate(
            canonical_key=canonical_key,
            normalized_value=norm_val,
            owner_user_id=owner_user_id,
            display_text=str(norm_val),
            conversation_id=conversation_id,
            suppression_generation=suppression_generation,
        )

        if not is_set and active_versions and any(item.normalized_value == norm_val for item in active_versions):
            relation = MemoryRelation.SAME
        elif is_set:
            relation = MemoryRelation.COMPATIBLE
        else:
            relation = MemoryRelation.TEMPORAL_UPDATE
        change = resolve_change(candidate, active_versions, relation=relation)

        if change.operation is MemoryOperation.REINFORCE:
            ack = f"Đã ghi nhận! Bạn đã có sở thích này rồi. ({canonical_key}: {norm_val})"
        else:
            ack = f"Đã lưu! Tôi đã ghi nhớ sở thích của bạn. ({canonical_key}: {norm_val})"

        return ExplicitMemoryProposal(
            outcome=ProposalOutcome.MUTATION,
            canonical_key=canonical_key,
            change=change,
            expected_version_id=expected_version_id,
            suppression_generation=suppression_generation,
            acknowledgement_text=ack,
            reason="remember_mutation",
        )

    def _propose_correct(
        self,
        *,
        canonical_key: str,
        raw_values: Any,
        is_set: bool,
        active_versions: tuple[MemoryVersion, ...],
        expected_version_id: str | None,
        owner_user_id: str,
        conversation_id: str = "",
        suppression_generation: int = 1,
    ) -> ExplicitMemoryProposal:
        try:
            norm_val = normalize_value(canonical_key, raw_values)
        except RegistryValidationError:
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.CLARIFICATION,
                canonical_key=canonical_key,
                suppression_generation=suppression_generation,
                clarification_prompt=f"Giá trị sửa lại không thuộc danh mục hợp lệ cho {canonical_key}.",
                reason="invalid_value_for_key",
            )

        candidate = self._build_candidate(
            canonical_key=canonical_key,
            normalized_value=norm_val,
            owner_user_id=owner_user_id,
            display_text=str(norm_val),
            conversation_id=conversation_id,
            suppression_generation=suppression_generation,
        )

        if is_set:
            desired_members = norm_val if isinstance(norm_val, tuple) else (norm_val,)
            change = resolve_change(
                candidate,
                active_versions,
                relation=MemoryRelation.TEMPORAL_UPDATE,
                desired_members=desired_members,
            )
        else:
            change = resolve_change(
                candidate,
                active_versions,
                relation=MemoryRelation.TEMPORAL_UPDATE,
            )

        ack = f"Đã sửa lại! Sở thích {canonical_key} hiện tại là: {norm_val}"
        return ExplicitMemoryProposal(
            outcome=ProposalOutcome.MUTATION,
            canonical_key=canonical_key,
            change=change,
            expected_version_id=expected_version_id,
            suppression_generation=suppression_generation,
            acknowledgement_text=ack,
            reason="correct_mutation",
        )

    def _propose_forget(
        self,
        *,
        canonical_key: str,
        raw_values: Any,
        is_set: bool,
        active_versions: tuple[MemoryVersion, ...],
        expected_version_id: str | None,
        owner_user_id: str,
        conversation_id: str = "",
        suppression_generation: int = 1,
    ) -> ExplicitMemoryProposal:
        if not active_versions:
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.NOOP,
                canonical_key=canonical_key,
                suppression_generation=suppression_generation,
                acknowledgement_text=f"Không tìm thấy thông tin sở thích nào đã lưu cho {canonical_key}.",
                reason="forget_no_active",
            )

        candidate = self._build_candidate(
            canonical_key=canonical_key,
            normalized_value=active_versions[-1].normalized_value,
            owner_user_id=owner_user_id,
            display_text="forget",
            conversation_id=conversation_id,
            suppression_generation=suppression_generation,
        )

        if not is_set:
            # Whole key revoke for single key
            superseded_ids = tuple(v.version_id for v in active_versions)
            change = MemoryChangeSet(
                operation=MemoryOperation.REVOKE,
                identity=assertion_identity(candidate),
                new_version=None,
                superseded_version_ids=superseded_ids,
                reference_version_id=None,
                reason="explicit_revoke",
            )
            ack = f"Đã xóa sở thích {canonical_key} theo yêu cầu của bạn."
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.MUTATION,
                canonical_key=canonical_key,
                change=change,
                expected_version_id=expected_version_id,
                suppression_generation=suppression_generation,
                acknowledgement_text=ack,
                reason="forget_single_key",
            )

        # Set key: determine if targeted member forget or whole-key forget
        current_members: set[str] = set()
        for v in active_versions:
            if isinstance(v.normalized_value, tuple):
                current_members.update(v.normalized_value)
            elif isinstance(v.normalized_value, str):
                current_members.add(v.normalized_value)

        if raw_values is not None:
            to_remove: set[str] = set()
            try:
                norm_remove = normalize_value(canonical_key, raw_values)
                if isinstance(norm_remove, tuple):
                    to_remove.update(norm_remove)
                else:
                    to_remove.add(norm_remove)
            except RegistryValidationError:
                return ExplicitMemoryProposal(
                    outcome=ProposalOutcome.CLARIFICATION,
                    canonical_key=canonical_key,
                    suppression_generation=suppression_generation,
                    clarification_prompt=f"Mục yêu cầu xóa không thuộc danh mục hợp lệ cho {canonical_key}.",
                    reason="invalid_member_to_forget",
                )

            if not to_remove or not (to_remove & current_members):
                return ExplicitMemoryProposal(
                    outcome=ProposalOutcome.NOOP,
                    canonical_key=canonical_key,
                    suppression_generation=suppression_generation,
                    acknowledgement_text=f"Mục bạn yêu cầu xóa không có trong sở thích đã lưu cho {canonical_key}.",
                    reason="member_not_in_set",
                )

            remaining = tuple(sorted(current_members - to_remove))
        else:
            # Whole set forget (raw_values is None)
            remaining = ()

        change = resolve_change(
            candidate,
            active_versions,
            relation=MemoryRelation.TEMPORAL_UPDATE,
            desired_members=remaining,
        )

        if change.operation is MemoryOperation.REVOKE:
            ack = f"Đã xóa toàn bộ sở thích {canonical_key}."
        else:
            remaining_str = ", ".join(remaining) if isinstance(remaining, (tuple, list)) else str(remaining)
            ack = f"Đã xóa các mục yêu cầu khỏi {canonical_key}. Sở thích còn lại: {remaining_str}."

        return ExplicitMemoryProposal(
            outcome=ProposalOutcome.MUTATION,
            canonical_key=canonical_key,
            change=change,
            expected_version_id=expected_version_id,
            suppression_generation=suppression_generation,
            acknowledgement_text=ack,
            reason="forget_set_key",
        )

    def _build_candidate(
        self,
        *,
        canonical_key: str,
        normalized_value: Any,
        owner_user_id: str,
        display_text: str,
        conversation_id: str,
        suppression_generation: int = 1,
    ) -> MemoryCandidate:
        return MemoryCandidate(
            candidate_id=new_candidate_id(),
            evidence_ids=(),
            owner_user_id=owner_user_id,
            scope=MemoryScope.USER,
            conversation_id=conversation_id,
            canonical_key=canonical_key,
            normalized_value=normalized_value,
            display_text=display_text,
            authority=Authority.EXPLICIT_SAVE,
            sensitivity=SensitivityBand.ORDINARY_PERSONAL,
            subject_key="self",
            condition="",
            observed_at=_utc_now(),
            confidence=1.0,
            suppression_generation=suppression_generation,
        )

    def _parse_target_key_and_values(
        self, utterance: str, mode: InteractionMode
    ) -> tuple[str | None, Any]:
        """Identify canonical key and raw value(s) from utterance.

        First attempts deterministic matching over the 8 registry definitions.
        If undetermined, falls back to at most 1 bounded model call via extract_explicit.
        """
        folded = utterance.strip().casefold()

        if mode is InteractionMode.EXPLICIT_FORGET:
            targeted_match = re.search(
                r"(?:forget|remove|delete|bỏ|xóa|xoá|quên|loại bỏ)\s+(.+?)\s+(?:from|in|of|out of|khỏi|trong)\s+(.+)",
                folded,
            )
            if targeted_match:
                item_part = targeted_match.group(1).strip()
                cat_part = targeted_match.group(2).removesuffix(" đi").strip()
                cat_key = None
                if any(_matches_term(w, cat_part) for w in ("phương tiện", "di chuyển", "đi lại", "transport", "transportation")):
                    cat_key = "travel.preference.transport_mode"
                elif any(_matches_term(w, cat_part) for w in ("chỗ ở", "loại chỗ ở", "nơi ở", "accommodation", "lodging")):
                    cat_key = "travel.preference.accommodation_type"
                elif any(_matches_term(w, cat_part) for w in ("ẩm thực", "ăn uống", "món ăn", "khẩu vị", "food", "cuisine")):
                    cat_key = "travel.preference.food_style"
                elif any(_matches_term(w, cat_part) for w in ("hoạt động", "phong cách hoạt động", "activity", "activities")):
                    cat_key = "travel.preference.activity_style"
                elif any(_matches_term(w, cat_part) for w in ("budget", "ngân sách", "chi phí")):
                    cat_key = "travel.constraint.budget_level"
                elif any(_matches_term(w, cat_part) for w in ("hotel", "khách sạn")):
                    cat_key = "travel.preference.hotel_atmosphere"
                elif any(_matches_term(w, cat_part) for w in ("pace", "nhịp độ")):
                    cat_key = "travel.preference.travel_pace"
                elif any(_matches_term(w, cat_part) for w in ("departure", "khởi hành")):
                    cat_key = "travel.profile.default_departure_city"

                if cat_key is not None:
                    cat_defn = get_key_definition(cat_key)
                    matched_items = []
                    for v in cat_defn.values:
                        syns = cat_defn.synonyms.get(v, ())
                        if _matches_term(v, item_part) or any(_matches_term(s, item_part) for s in syns):
                            matched_items.append(v)
                    if matched_items:
                        return cat_key, matched_items if cat_defn.cardinality is Cardinality.SET else matched_items[0]
                    return cat_key, item_part

            # Specific keyword heuristics for whole-key forget
            # 4 single keys
            if any(_matches_term(w, folded) for w in ("budget", "ngân sách", "chi phí")):
                return "travel.constraint.budget_level", None
            if _matches_term("hotel", folded) or _matches_term("khách sạn", folded):
                if not any(_matches_term(w, folded) for w in ("resort", "homestay", "villa", "apartment", "hostel")):
                    return "travel.preference.hotel_atmosphere", None
            if any(_matches_term(w, folded) for w in ("pace", "nhịp độ")):
                return "travel.preference.travel_pace", None
            if any(_matches_term(w, folded) for w in ("departure", "khởi hành")):
                return "travel.profile.default_departure_city", None

            # 4 set keys
            if any(_matches_term(w, folded) for w in ("chỗ ở", "loại chỗ ở", "nơi ở", "accommodation", "lodging")):
                return "travel.preference.accommodation_type", None
            if any(_matches_term(w, folded) for w in ("phương tiện", "di chuyển", "đi lại", "transport", "transportation")):
                return "travel.preference.transport_mode", None
            if any(_matches_term(w, folded) for w in ("hoạt động", "phong cách hoạt động", "activity style", "activities")):
                return "travel.preference.activity_style", None
            if any(_matches_term(w, folded) for w in ("ẩm thực", "ăn uống", "món ăn", "khẩu vị", "food style", "cuisine")):
                return "travel.preference.food_style", None

        # Deterministic match against all 8 registry keys
        matched_candidates: list[tuple[str, Any, int]] = []

        # Order of checks: longer/more specific value matches first
        # E.g. hotel_atmosphere before accommodation_type if atmosphere terms present
        has_atmosphere_terms = any(
            _matches_term(w, folded)
            for w in (
                "quiet", "yên tĩnh", "yên bình", "calm", "peaceful",
                "lively", "sôi động", "nhộn nhịp", "vibrant", "bustling",
                "central", "trung tâm", "downtown",
                "secluded", "biệt lập", "riêng tư", "private",
            )
        )
        if has_atmosphere_terms:
            for val in ("quiet", "lively", "central", "secluded"):
                defn = get_key_definition("travel.preference.hotel_atmosphere")
                syns = defn.synonyms.get(val, ())
                if _matches_term(val, folded) or any(_matches_term(s, folded) for s in syns):
                    return "travel.preference.hotel_atmosphere", val

        for key in registry_keys():
            if key == "travel.preference.hotel_atmosphere" and has_atmosphere_terms:
                continue
            defn = get_key_definition(key)
            found_members: list[str] = []
            max_match_len = 0
            for val in defn.values:
                syns = defn.synonyms.get(val, ())
                val_space = val.replace("_", " ")
                matched_str = None
                if _matches_term(val_space, folded):
                    matched_str = val_space
                elif _matches_term(val, folded):
                    matched_str = val
                else:
                    for s in syns:
                        if _matches_term(s, folded):
                            matched_str = s
                            break
                if matched_str is not None:
                    found_members.append(val)
                    if len(matched_str) > max_match_len:
                        max_match_len = len(matched_str)
            if found_members:
                if defn.cardinality is Cardinality.SET:
                    matched_candidates.append((key, found_members, max_match_len))
                else:
                    matched_candidates.append((key, found_members[0], max_match_len))

        if len(matched_candidates) == 1:
            return matched_candidates[0][0], matched_candidates[0][1]

        if len(matched_candidates) > 1:
            # Disambiguate: prefer longer match length, then more matched members
            matched_candidates.sort(
                key=lambda item: (
                    item[2],
                    len(item[1]) if isinstance(item[1], list) else 1,
                ),
                reverse=True,
            )
            return matched_candidates[0][0], matched_candidates[0][1]

        # Model fallback if provider is available: strictly bounded 1 call, 0 repair
        if self._provider is not None:
            extracted = extract_explicit(self._provider, utterance)
            if extracted:
                first = extracted[0]
                return first.canonical_key, first.value

        return None, None
