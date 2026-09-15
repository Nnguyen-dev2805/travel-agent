"""Episodic Memory vertical slice (Stage 5, plan v0.20 Task 12).

An episode is a *grounded* typed event record. Actor, event, time and provenance
are all required, and missing any one of them refuses formation and activation.
The grounding rule is the whole point of the family: an episode answers "what
happened", and an event with no actor, no time, or no provenance cannot answer
that — it is a fragment of text that merely looks like one.

Three boundaries this module deliberately does **not** own:

- tenant authorization, retention assignment, lifecycle rules, source validity,
  suppression generation and prompt construction stay with their existing
  owners (`RetentionAssignmentPolicy`, `MemoryLifecyclePolicy`, the store);
- the semantic activation thresholds (2 agreeing turns / 3 evidence items across
  2 conversations) do not apply here — one independently grounded event may
  suffice (`spec:1036`, `ADR 0038:81`) — so episodic activation has its own gate
  rather than borrowing `MemoryActivationPolicy`;
- episodes are not semantic registry keys. The read contract is separate and
  typed; encoding an episode as a fake `canonical_key` in registry-v2 would make
  every semantic policy apply to something it was never written for.

There is no universal event ontology. `event` is a bounded string, not a closed
vocabulary, because inventing one before the evaluation says which event types
matter is exactly the speculative family modelling the plan forbids.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, Sequence

from backend.memory.lifecycle import (
    LifecycleFacts,
    LifecycleStage,
    MemoryLifecyclePolicy,
    RetentionAssignmentPolicy,
    SourceValidity,
)
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingRecord,
    allows_background_formation,
)
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryScope,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
)
from backend.memory.write_pipeline.secrets import detect_prohibited_content

#: Bounds on the free-text grounding fields. A grounded fact is a fact, not a
#: transcript: an unbounded `event` string is a raw-source channel wearing a
#: typed field's name, and the architecture keeps raw evidence out of prompt and
#: policy paths by default (`spec:1079`).
MAX_ACTOR_LENGTH = 256
MAX_EVENT_LENGTH = 2000

#: The read bound. Mirrors the semantic bound so one response cannot admit an
#: unbounded episodic selection even if a caller asks for more.
MAX_SELECTED_EPISODES = 8


class EpisodeRefusalReason(str, Enum):
    """Closed vocabulary for why a grounding was refused."""

    MISSING_ACTOR = "missing_actor"
    INVALID_ACTOR = "invalid_actor"
    MISSING_EVENT = "missing_event"
    INVALID_EVENT = "invalid_event"
    MISSING_TIME = "missing_time"
    INVALID_TIME = "invalid_time"
    MISSING_PROVENANCE = "missing_provenance"
    INVALID_PROVENANCE = "invalid_provenance"


@dataclass(frozen=True)
class EpisodeProvenance:
    """Where a grounded event came from.

    The identity pair is the same authority key the source-handling record uses
    (`(source_outbox_id, family)` is storage-side; here the message is carried
    too because evaluation and dedup need the turn, not only the event row).
    Redelivery of one source yields an equal provenance, so it can never be
    counted as independent support (`ADR 0038:90-91`).
    """

    source_outbox_id: Any
    source_message_id: Any


@dataclass(frozen=True)
class EpisodeGrounding:
    """The four facts an episode must carry to be an episode.

    Deliberately *not* validated in `__post_init__`: the validator is the single
    authority for this decision, and a second copy in the constructor would be
    the duplicated rule this architecture keeps removing. Constructing an
    incomplete grounding is allowed so the refusal can be observed and logged
    with its reason, rather than surfacing as a construction-time exception the
    caller cannot classify.
    """

    actor: Any
    event: Any
    occurred_at: Any
    provenance: Any


def _is_bounded_text(value: Any, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def validate_episode_grounding(
    grounding: EpisodeGrounding | None,
) -> EpisodeRefusalReason | None:
    """Return the reason this grounding is incomplete, or `None` when grounded.

    Ordered, and the order is the contract: a caller that fixes the reported
    problem and re-runs gets the next one, so a refusal is always actionable
    rather than merely true.
    """
    if grounding is None:
        return EpisodeRefusalReason.MISSING_PROVENANCE

    actor = grounding.actor
    if actor is None or (isinstance(actor, str) and not actor.strip()):
        return EpisodeRefusalReason.MISSING_ACTOR
    if not _is_bounded_text(actor, MAX_ACTOR_LENGTH):
        return EpisodeRefusalReason.INVALID_ACTOR

    event = grounding.event
    if event is None or (isinstance(event, str) and not event.strip()):
        return EpisodeRefusalReason.MISSING_EVENT
    if not _is_bounded_text(event, MAX_EVENT_LENGTH):
        return EpisodeRefusalReason.INVALID_EVENT

    occurred_at = grounding.occurred_at
    if occurred_at is None:
        return EpisodeRefusalReason.MISSING_TIME
    if (
        not isinstance(occurred_at, datetime)
        or occurred_at.tzinfo is None
        or occurred_at.utcoffset() is None
    ):
        # A naive datetime is a local guess, not an instant. Grounding on it
        # would make "when" depend on the reader's clock.
        return EpisodeRefusalReason.INVALID_TIME

    provenance = grounding.provenance
    if provenance is None:
        return EpisodeRefusalReason.MISSING_PROVENANCE
    if not isinstance(provenance, EpisodeProvenance):
        return EpisodeRefusalReason.INVALID_PROVENANCE
    if not _is_bounded_text(provenance.source_outbox_id, MAX_ACTOR_LENGTH):
        return EpisodeRefusalReason.INVALID_PROVENANCE
    if not _is_bounded_text(provenance.source_message_id, MAX_ACTOR_LENGTH):
        return EpisodeRefusalReason.INVALID_PROVENANCE
    return None


@dataclass(frozen=True)
class EpisodeCandidate:
    """A grounded, authority-approved episode candidate.

    Not yet active. Activation is a separate decision with its own gate, and
    `retention_mode` here is the *assigned* mode that will be persisted — it is
    never re-derived later (`ADR 0037`).
    """

    candidate_id: str
    owner_user_id: str
    conversation_id: str
    scope: MemoryScope
    grounding: EpisodeGrounding
    retention_mode: RetentionMode
    sensitivity: SensitivityBand
    suppression_generation: int

    def provenance_identity(self) -> tuple[str, str]:
        """The dedup key. Two candidates equal here are the same source event."""
        return (
            str(self.grounding.provenance.source_outbox_id),
            str(self.grounding.provenance.source_message_id),
        )


class EpisodeFormationEngine:
    """Forms one grounded episode candidate, or refuses and returns `None`.

    Every refusal returns `None` rather than a partial candidate, because a
    half-grounded episode is not a lesser episode — it is a different thing that
    the read path would treat as grounded.
    """

    def __init__(
        self,
        *,
        lifecycle_policy: MemoryLifecyclePolicy | None = None,
        retention_policy: RetentionAssignmentPolicy | None = None,
    ) -> None:
        self._lifecycle_policy = lifecycle_policy or MemoryLifecyclePolicy()
        self._retention_policy = retention_policy or RetentionAssignmentPolicy()

    def form_episode(
        self,
        *,
        source_outbox_id: str,
        source_message_id: str,
        owner_user_id: str,
        conversation_id: str,
        grounding: EpisodeGrounding | None,
        source_handling_record: SourceHandlingRecord | None,
        stamped_generation: int = 1,
        current_generation: int = 1,
        source_validity: SourceValidity = SourceValidity.VALID,
        observed_at: datetime | None = None,
        expires_at: datetime | None = None,
        secret_scan_text: str | None = None,
    ) -> EpisodeCandidate | None:
        # 1. Positive family-specific authority. `UNHANDLED`, a semantic-family
        #    record, and a blocked episodic outcome all deny (ADR 0038:59).
        if not allows_episodic_formation(source_handling_record):
            return None

        # 2. Grounding. Checked before the model so an ungrounded source is
        #    never paid for.
        if validate_episode_grounding(grounding) is not None:
            return None

        # 3. Pre-model secret scan.
        if secret_scan_text is not None and (
            detect_prohibited_content(secret_scan_text) is not None
        ):
            return None

        # 4. Retention is the shared policy's decision, not ours.
        try:
            retention_mode = self._retention_policy.assign(
                scope=MemoryScope.CONVERSATION,
                authority=Authority.REPEATED_INFERENCE,
            )
        except ValueError:
            return None

        # 5. Lifecycle eligibility at FORMATION.
        observed = observed_at or datetime.now(timezone.utc)
        facts = LifecycleFacts(
            retention_mode=retention_mode,
            stamped_generation=stamped_generation,
            current_generation=current_generation,
            scope=MemoryScope.CONVERSATION,
            sensitivity=SensitivityBand.ORDINARY_PERSONAL,
            source_validity=source_validity,
            expires_at=expires_at,
            evaluated_at=observed if expires_at is not None else None,
        )
        decision = self._lifecycle_policy.evaluate(
            stage=LifecycleStage.FORMATION, facts=facts
        )
        if not decision.eligible:
            return None

        return EpisodeCandidate(
            candidate_id=f"epc_{source_outbox_id}",
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            scope=MemoryScope.CONVERSATION,
            grounding=grounding,
            retention_mode=retention_mode,
            sensitivity=SensitivityBand.ORDINARY_PERSONAL,
            suppression_generation=stamped_generation,
        )


def allows_episodic_formation(record: SourceHandlingRecord | None) -> bool:
    """Whether a persisted record grants *episodic* background formation.

    Both halves are required and neither is inferable from the other: the
    record must be the positive authority (`allows_background_formation`) **and**
    it must name the episodic family. A semantic `BACKGROUND_ELIGIBLE` record is
    positive authority for semantic formation and nothing else, so reusing it
    here would let one family's decision authorize another's work.
    """
    if not isinstance(record, SourceHandlingRecord):
        return False
    if record.family is not MemoryFamily.EPISODIC:
        return False
    return allows_background_formation(record)


class EpisodeActivationReason(str, Enum):
    """Closed reason vocabulary for episodic activation, in precedence order."""

    GROUNDING_INCOMPLETE = "grounding_incomplete"
    LIFECYCLE_DENIED = "lifecycle_denied"
    EPISODIC_GATE_DISABLED = "episodic_gate_disabled"
    EPISODIC_GATE_INCONCLUSIVE = "episodic_gate_inconclusive"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    STALE_GENERATION = "stale_generation"
    SOURCE_INVALID = "source_invalid"
    ELIGIBLE_ACTIVE = "eligible_active"


@dataclass(frozen=True)
class EpisodeActivationFacts:
    """Typed, I/O-free snapshot of the facts episodic activation needs.

    Every permitting fact is required. The two gate flags default to `False`
    because that is the fail-closed direction: a caller that forgets to supply
    the episodic gate must not thereby enable inferred episodic activation, and
    the semantic inferred-activation flag is deliberately *not* an input — the
    plan is explicit that passing semantic evaluation is not evidence that
    episodic activation was evaluated.
    """

    grounding_conclusive: bool
    lifecycle_eligible: bool
    source_validity: SourceValidity | str
    stamped_generation: int | None
    current_generation: int | None
    has_unresolved_conflict: bool
    episodic_gate_enabled: bool = False
    episodic_gate_conclusive: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.source_validity, str):
            object.__setattr__(
                self, "source_validity", SourceValidity(self.source_validity)
            )


@dataclass(frozen=True)
class EpisodeActivationDecision:
    target_status: VersionStatus
    reason: EpisodeActivationReason
    eligible: bool


class EpisodeActivationPolicy:
    """Pure deterministic policy for inferred episodic activation.

    One independently grounded event may suffice. There is no turn or evidence
    count here on purpose: the semantic thresholds answer "how often has the
    user said this", and an episode's question is "did this happen", which one
    grounded event already answers.
    """

    def evaluate(self, facts: EpisodeActivationFacts) -> EpisodeActivationDecision:
        def deny(reason: EpisodeActivationReason) -> EpisodeActivationDecision:
            return EpisodeActivationDecision(
                target_status=VersionStatus.SHADOW, reason=reason, eligible=False
            )

        # 1. Grounding is the family's own prerequisite.
        if not facts.grounding_conclusive:
            return deny(EpisodeActivationReason.GROUNDING_INCOMPLETE)

        # 2. The shared lifecycle owner still decides eligibility.
        if not facts.lifecycle_eligible:
            return deny(EpisodeActivationReason.LIFECYCLE_DENIED)

        # 3. The episodic family/type rollout gate, default off.
        if not facts.episodic_gate_enabled:
            return deny(EpisodeActivationReason.EPISODIC_GATE_DISABLED)
        if not facts.episodic_gate_conclusive:
            return deny(EpisodeActivationReason.EPISODIC_GATE_INCONCLUSIVE)

        # 4. Current canonical state, not a default.
        if facts.has_unresolved_conflict:
            return deny(EpisodeActivationReason.UNRESOLVED_CONFLICT)
        if (
            facts.stamped_generation is None
            or facts.current_generation is None
            or facts.stamped_generation != facts.current_generation
        ):
            return deny(EpisodeActivationReason.STALE_GENERATION)
        if facts.source_validity is SourceValidity.INVALID:
            return deny(EpisodeActivationReason.SOURCE_INVALID)

        return EpisodeActivationDecision(
            target_status=VersionStatus.ACTIVE,
            reason=EpisodeActivationReason.ELIGIBLE_ACTIVE,
            eligible=True,
        )


class EpisodeAbstentionReason(str, Enum):
    """Closed vocabulary for why episodic selection returned nothing."""

    NO_GROUNDED_FILTER = "no_grounded_filter"
    NO_ELIGIBLE_EPISODE = "no_eligible_episode"


@dataclass(frozen=True)
class EpisodeReadRequest:
    """An exact typed episodic query.

    There is no free-text or fuzzy field. An episodic read that could match on
    a string would be doing the retrieval-projection work the plan defers to
    Task 14, and it would answer "something similar happened" when the caller
    asked for a grounded event.
    """

    owner_user_id: str
    conversation_id: str | None = None
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None
    max_selected: int = MAX_SELECTED_EPISODES

    def __post_init__(self) -> None:
        if not isinstance(self.owner_user_id, str) or not self.owner_user_id.strip():
            raise ValueError("owner_user_id must be a non-empty string.")
        if (
            not isinstance(self.max_selected, int)
            or isinstance(self.max_selected, bool)
            or not 1 <= self.max_selected <= MAX_SELECTED_EPISODES
        ):
            raise ValueError(
                f"max_selected must be an integer in 1..{MAX_SELECTED_EPISODES}."
            )
        for field_name in ("occurred_after", "occurred_before"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValueError(f"{field_name} must be a timezone-aware datetime.")


@dataclass(frozen=True)
class StoredEpisodeRow:
    """One physical episode row, already coerced back to domain vocabulary.

    Storage-scoped only. This row does not say whether the episode is
    answer-eligible — `MemoryLifecyclePolicy` decides that, in the engine.
    """

    episode_id: str
    owner_user_id: str
    conversation_id: str
    actor: str
    event: str
    occurred_at: datetime
    source_message_id: str
    source_outbox_id: str
    retention_mode: RetentionMode
    stamped_generation: int
    current_generation: int
    status: VersionStatus
    sensitivity: SensitivityBand
    source_validity: SourceValidity
    expires_at: datetime | None = None
    unresolved_conflict: bool = False


@dataclass(frozen=True)
class SelectedEpisode:
    """The governed projection handed to context composition.

    Structured fields only. The source text, the source-handling row and the
    deleted-source provenance stay behind: an episode that carried its raw
    evidence would be a prompt-instruction channel (`spec:1079`).
    """

    episode_id: str
    actor: str
    event: str
    occurred_at: datetime
    conversation_id: str


@dataclass(frozen=True)
class EpisodeSelection:
    selected: tuple[SelectedEpisode, ...]
    abstention_reason: EpisodeAbstentionReason | None = None


class EpisodeStore(Protocol):
    def list_storage_scoped(
        self, request: EpisodeReadRequest
    ) -> Sequence[StoredEpisodeRow]: ...


class EpisodicReadEngine:
    """Eligibility, relevance and abstention for grounded episodes.

    Abstention is a real outcome, not an error: a query whose exact typed window
    excludes every episode gets `NO_ELIGIBLE_EPISODE`, and the engine never
    widens the window to avoid returning nothing.
    """

    def __init__(
        self,
        store: EpisodeStore,
        lifecycle: MemoryLifecyclePolicy | None = None,
        clock: Any | None = None,
    ) -> None:
        self._store = store
        self._lifecycle = lifecycle or MemoryLifecyclePolicy()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def select(self, request: EpisodeReadRequest) -> EpisodeSelection:
        if request.occurred_after is None and request.occurred_before is None:
            return EpisodeSelection((), EpisodeAbstentionReason.NO_GROUNDED_FILTER)
        rows = tuple(self._store.list_storage_scoped(request))
        return self._select_rows(request, rows, self._clock())

    def _select_rows(
        self,
        request: EpisodeReadRequest,
        rows: tuple[StoredEpisodeRow, ...],
        evaluated_at: datetime,
    ) -> EpisodeSelection:
        eligible: list[StoredEpisodeRow] = []
        for row in rows:
            if row.owner_user_id != request.owner_user_id:
                continue
            if (
                request.conversation_id is not None
                and row.conversation_id != request.conversation_id
            ):
                continue
            if (
                request.occurred_after is not None
                and row.occurred_at < request.occurred_after
            ):
                continue
            if (
                request.occurred_before is not None
                and row.occurred_at >= request.occurred_before
            ):
                continue
            # Conflict exclusion is a read concern the lifecycle policy does not
            # model; the canonical flag is authoritative (`ADR 0037`).
            if row.unresolved_conflict:
                continue
            decision = self._lifecycle.evaluate(
                stage=LifecycleStage.READ,
                facts=LifecycleFacts(
                    retention_mode=row.retention_mode,
                    stamped_generation=row.stamped_generation,
                    current_generation=row.current_generation,
                    scope=MemoryScope.CONVERSATION,
                    sensitivity=row.sensitivity,
                    source_validity=row.source_validity,
                    status=row.status,
                    expires_at=row.expires_at,
                    evaluated_at=evaluated_at if row.expires_at is not None else None,
                ),
            )
            if decision.eligible:
                eligible.append(row)

        eligible.sort(key=lambda r: (-r.occurred_at.timestamp(), r.episode_id))
        selected = tuple(
            SelectedEpisode(
                episode_id=row.episode_id,
                actor=row.actor,
                event=row.event,
                occurred_at=row.occurred_at,
                conversation_id=row.conversation_id,
            )
            for row in eligible[: request.max_selected]
        )
        return EpisodeSelection(
            selected,
            None if selected else EpisodeAbstentionReason.NO_ELIGIBLE_EPISODE,
        )
