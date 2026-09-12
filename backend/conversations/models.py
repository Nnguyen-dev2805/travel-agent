"""Conversation and message value contracts for runtime milestone R4.

These contracts give later milestones a stable provenance target: `R5` memory
candidates, `R6` selected memories, `R7` itinerary versions and trip decisions,
and a future evaluation trace all reference `conversation_id` and `message_id`.
R4 freezes their format and their generation ownership so those milestones do
not renegotiate identity.

This module must remain storage-agnostic and route-agnostic: it depends on the
Python standard library only, and never on FastAPI, Pydantic, SQLite, RAG,
Chroma, a model provider, or the evaluation subsystem.

Three rules are load-bearing:

1. **Identity and ordering are server-owned.** `ConversationCreate` has no
   `conversation_id`, and `MessageDraft` has neither `message_id` nor
   `sequence`, so caller input cannot forge either.
2. **`content` is deliberately unbounded.** This departs from the R3 rule that
   every text field is bounded. The chat route already accepts an unbounded
   `message`, so a storage limit would turn requests that succeed today into
   failures once a conversation is bound. Request size limiting belongs at the
   API boundary and is recorded as a known gap.
3. **A message carries no retention state of its own.** It follows its parent
   conversation, so a future deletion milestone has exactly one place to express
   intent and cannot leave orphaned message state behind.
4. **Turn status is server-owned.** `MessageStatus` records whether a turn has
   been filled in yet (ADR 0023). It is never accepted from caller input, and it
   is what makes a half-written turn visible rather than indistinguishable from
   a complete one.

Message `content` is user content under the security policy. It is stored here,
never logged, and never deleted by R4.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

CONVERSATION_ID_PREFIX = "cv_"
MESSAGE_ID_PREFIX = "ms_"
TITLE_MAX_LENGTH = 120
DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 200
MIN_MESSAGE_SEQUENCE = 1


class ConversationValidationError(ValueError):
    """A conversation contract rule was violated before any storage write."""


class MessageRole(str, Enum):
    """Message authorship vocabulary from the approved R4 specification."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM_EVENT = "system_event"


class MessageSource(str, Enum):
    """Message provenance vocabulary from the approved R4 specification."""

    UI = "ui"
    TOOL = "tool"
    MODEL = "model"
    SYSTEM = "system"
    IMPORT = "import"


class MessageStatus(str, Enum):
    """Server-owned turn status for a persisted message (ADR 0023).

    A chat turn is written in two phases: the user message and a placeholder
    assistant row commit together, and the assistant row is filled in after
    generation. The status is what makes a half-written turn visible instead of
    indistinguishable from a complete one.

    `status` is server-owned and never accepted from caller input.
    """

    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"


class TraceVisibility(str, Enum):
    """Whether a message may be used as evaluation trace input.

    The default is `EXCLUDED`, so no persisted message becomes evaluation input
    without an explicit decision. This is default-deny, matching the policy that
    full conversation logging is not the default.
    """

    EXCLUDED = "excluded"
    INCLUDED = "included"


class ConversationRetentionState(str, Enum):
    """Conversation retention vocabulary from the approved specification.

    Per ADR 0021, standalone conversations have active or tombstoned lifecycle states.
    """

    ACTIVE = "active"
    TOMBSTONED = "tombstoned"
    SUMMARIZED = "summarized"
    ARCHIVED = "archived"
    DELETION_REQUESTED = "deletion_requested"
    DELETED = "deleted"


PUBLIC_WRITABLE_ROLES = frozenset({MessageRole.USER, MessageRole.SYSTEM_EVENT})
"""Roles a public caller may append.

`ASSISTANT` and `TOOL` are writable only through the orchestrator, so memory
extraction in `R5` cannot be poisoned through the public API.
"""

DEFAULT_MESSAGE_SOURCE = MessageSource.UI
DEFAULT_TRACE_VISIBILITY = TraceVisibility.EXCLUDED
DEFAULT_RETENTION_STATE = ConversationRetentionState.ACTIVE


def generate_conversation_id() -> str:
    """Return a new opaque conversation identifier using the governed prefix."""
    return f"{CONVERSATION_ID_PREFIX}{uuid.uuid4().hex}"


def generate_message_id() -> str:
    """Return a new opaque message identifier using the governed prefix."""
    return f"{MESSAGE_ID_PREFIX}{uuid.uuid4().hex}"


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def require_text(value: Any, field_name: str, max_length: int | None = None) -> str:
    """Strip and validate a required text field."""
    if not isinstance(value, str):
        raise ConversationValidationError(
            f"Conversation field '{field_name}' must be a string."
        )
    stripped = value.strip()
    if not stripped:
        raise ConversationValidationError(
            f"Conversation field '{field_name}' must not be empty."
        )
    if max_length is not None and len(stripped) > max_length:
        raise ConversationValidationError(
            f"Conversation field '{field_name}' must be at most "
            f"{max_length} characters."
        )
    return stripped


def _normalize_optional_text(
    value: Any, field_name: str, max_length: int
) -> str | None:
    """Strip an optional text field, treating a blank value as absent."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConversationValidationError(
            f"Conversation field '{field_name}' must be a string or null."
        )
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) > max_length:
        raise ConversationValidationError(
            f"Conversation field '{field_name}' must be at most "
            f"{max_length} characters."
        )
    return stripped


def _require_identity(value: Any, field_name: str, prefix: str) -> str:
    """Validate a server-generated identifier and its governed prefix."""
    identity = require_text(value, field_name)
    if not identity.startswith(prefix):
        raise ConversationValidationError(
            f"Conversation field '{field_name}' must start with '{prefix}'."
        )
    return identity


def _coerce_enum(
    value: Any, field_name: str, enum_type: type[Enum], default: Any
) -> Any:
    """Resolve an absent, enum, or governed string vocabulary value.

    A `None` default means the field is required, so an absent value raises
    rather than silently selecting a member.
    """
    if value is None:
        if default is None:
            raise ConversationValidationError(
                f"Conversation field '{field_name}' is required."
            )
        return default
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError as error:
            allowed = ", ".join(member.value for member in enum_type)
            raise ConversationValidationError(
                f"Unknown {field_name} value. Allowed values: {allowed}."
            ) from error
    raise ConversationValidationError(
        f"Conversation field '{field_name}' must be a {enum_type.__name__} value."
    )


def _require_utc(value: Any, field_name: str) -> datetime:
    """Require a timezone-aware datetime and normalize it to UTC."""
    if not isinstance(value, datetime):
        raise ConversationValidationError(
            f"Conversation field '{field_name}' must be a datetime."
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise ConversationValidationError(
            f"Conversation field '{field_name}' must be timezone-aware UTC."
        )
    return value.astimezone(timezone.utc)


def _require_bounded_int(
    value: Any, field_name: str, minimum: int, maximum: int | None = None
) -> int:
    """Require a plain integer inside an inclusive range.

    `bool` is rejected explicitly. It is a subclass of `int`, so `True` would
    otherwise pass as the value `1`.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConversationValidationError(
            f"Conversation field '{field_name}' must be an integer."
        )
    if value < minimum:
        raise ConversationValidationError(
            f"Conversation field '{field_name}' must be at least {minimum}."
        )
    if maximum is not None and value > maximum:
        raise ConversationValidationError(
            f"Conversation field '{field_name}' must be at most {maximum}."
        )
    return value


def _normalize_message_fields(instance: Any) -> None:
    """Normalize the fields shared by `MessageDraft` and `Message`.

    `MessageDraft` validates service-assembled input; `Message` validates the
    same fields again because it is also rehydrated from storage, where a row
    could violate the contract. Both call sites are required, so the rules live
    here once instead of being written twice.
    """
    object.__setattr__(
        instance,
        "conversation_id",
        require_text(instance.conversation_id, "conversation_id"),
    )
    object.__setattr__(
        instance, "role", _coerce_enum(instance.role, "role", MessageRole, None)
    )
    status = _coerce_enum(
        instance.status, "status", MessageStatus, MessageStatus.COMPLETE
    )
    object.__setattr__(instance, "status", status)
    # `content` is required only for a COMPLETE message. A PENDING or FAILED row
    # carries no generated content by construction (ADR 0023), so it may be
    # empty — but it must still be a string, and a FAILED row must never hold a
    # partial reply or a provider error string.
    if status is MessageStatus.COMPLETE:
        content = require_text(instance.content, "content")
    elif isinstance(instance.content, str):
        content = instance.content
    else:
        raise ConversationValidationError(
            "Conversation field 'content' must be a string."
        )
    object.__setattr__(instance, "content", content)
    object.__setattr__(
        instance,
        "source",
        _coerce_enum(instance.source, "source", MessageSource, DEFAULT_MESSAGE_SOURCE),
    )
    object.__setattr__(
        instance,
        "trace_visibility",
        _coerce_enum(
            instance.trace_visibility,
            "trace_visibility",
            TraceVisibility,
            DEFAULT_TRACE_VISIBILITY,
        ),
    )
    object.__setattr__(
        instance, "created_at", _require_utc(instance.created_at, "created_at")
    )


@dataclass(frozen=True)
class ConversationCreate:
    """Validated input for creating one conversation.

    This contract deliberately has no `conversation_id` field. Identity is
    generated by the conversation service, never accepted from caller input.

    Per ADR 0021 the conversation is owned directly by `owner_user_id`.
    """

    owner_user_id: str
    title: str | None = None
    retention_state: Literal["active", "tombstoned"] | ConversationRetentionState = (
        ConversationRetentionState.ACTIVE
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "owner_user_id", require_text(self.owner_user_id, "owner_user_id")
        )
        object.__setattr__(
            self,
            "title",
            _normalize_optional_text(self.title, "title", TITLE_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "retention_state",
            _coerce_enum(
                self.retention_state,
                "retention_state",
                ConversationRetentionState,
                ConversationRetentionState.ACTIVE,
            ),
        )


@dataclass(frozen=True)
class Conversation:
    """One persisted standalone conversation record owned directly by a user.

    Per ADR 0021 `owner_user_id` is the authorization owner and conversations
    are standalone without workspace dependency.
    """

    conversation_id: str
    owner_user_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime
    retention_state: ConversationRetentionState | Literal["active", "tombstoned"] = (
        field(default=DEFAULT_RETENTION_STATE)
    )
    deletion_epoch: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "conversation_id",
            _require_identity(
                self.conversation_id, "conversation_id", CONVERSATION_ID_PREFIX
            ),
        )
        object.__setattr__(
            self, "owner_user_id", require_text(self.owner_user_id, "owner_user_id")
        )
        object.__setattr__(
            self,
            "title",
            _normalize_optional_text(self.title, "title", TITLE_MAX_LENGTH),
        )
        object.__setattr__(
            self, "created_at", _require_utc(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _require_utc(self.updated_at, "updated_at")
        )
        object.__setattr__(
            self,
            "retention_state",
            _coerce_enum(
                self.retention_state,
                "retention_state",
                ConversationRetentionState,
                DEFAULT_RETENTION_STATE,
            ),
        )
        object.__setattr__(
            self,
            "deletion_epoch",
            _require_bounded_int(self.deletion_epoch, "deletion_epoch", 0),
        )


@dataclass(frozen=True)
class MessageDraft:
    """A message ready to persist, before storage assigns its position.

    `sequence` is absent because the repository allocates it inside the write
    transaction, and `message_id` is absent because the service generates it.
    """

    conversation_id: str
    role: MessageRole | str
    content: str
    source: MessageSource | str | None = None
    trace_visibility: TraceVisibility | str | None = None
    created_at: datetime | None = None
    status: MessageStatus | str | None = None

    def __post_init__(self) -> None:
        _normalize_message_fields(self)


@dataclass(frozen=True)
class Message:
    """One persisted message record inside a conversation.

    `sequence` is a stored monotonic integer rather than an inferred timestamp
    comparison, because later provenance depends on turn order being a fact.
    """

    message_id: str
    conversation_id: str
    sequence: int
    role: MessageRole | str
    content: str
    source: MessageSource | str | None = None
    trace_visibility: TraceVisibility | str | None = None
    created_at: datetime | None = None
    status: MessageStatus | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "message_id",
            _require_identity(self.message_id, "message_id", MESSAGE_ID_PREFIX),
        )
        object.__setattr__(
            self,
            "sequence",
            _require_bounded_int(self.sequence, "sequence", MIN_MESSAGE_SEQUENCE),
        )
        _normalize_message_fields(self)


@dataclass(frozen=True)
class TransitionResult:
    """The outcome of a guarded turn transition.

    Carries **whether this call is the one that moved the row**, separately from the
    row it ended up with.

    The repository is deliberately idempotent: a row that is no longer `pending` is
    returned unchanged, so `message` alone cannot tell a caller whether it wrote the
    reply or merely observed someone else's. A caller that reports success on
    `message` alone will, when a second writer got there first, hand its client a
    reply the database does not contain.

    Comparing `message.content` against the reply the caller generated is not the
    fix: that infers ownership from a value, and it breaks the moment two turns
    legitimately produce the same text. `applied` is the fact itself, and it is what
    a recovery actor, a resume actor, or an agent state machine will need to branch
    on.
    """

    message: Message
    #: `True` only when this call performed the `pending -> terminal` transition.
    applied: bool


@dataclass(frozen=True)
class MessageHistoryQuery:
    """Validated cursor-paginated message history request.

    Messages are read in `sequence` ascending order, which is the reading order
    of a transcript and the opposite direction from the newest-first conversation lists.
    """

    conversation_id: str
    after_message_id: str | None = None
    limit: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "conversation_id",
            require_text(self.conversation_id, "conversation_id"),
        )
        object.__setattr__(
            self,
            "after_message_id",
            _normalize_optional_text(
                self.after_message_id, "after_message_id", TITLE_MAX_LENGTH
            ),
        )
        resolved = DEFAULT_HISTORY_LIMIT if self.limit is None else self.limit
        object.__setattr__(
            self,
            "limit",
            _require_bounded_int(resolved, "limit", 1, MAX_HISTORY_LIMIT),
        )


#: The one outbox event family the Memory worker is allowed to process.
#:
#: `conversation_outbox` is a single queue with a single `event_type` column, and
#: the Memory worker's claim path filtered only on release, status, lease expiry,
#: retry time, debounce and the conversation lock — never on the family. That is
#: harmless while exactly one family exists and stops being harmless the moment a
#: second one does: an agent or tool event (`agent.resume`, `summary.generate`,
#: `memory.reprocess`) would be claimed by the Memory worker and extracted as if it
#: were a conversation range.
#:
#: The constant lives here, beside `OutboxIntent`, because this is the module both
#: sides already import: the orchestrator produces the intent and the write
#: pipeline consumes it. Putting it in either one would make the other depend on a
#: layer it does not otherwise need.
MEMORY_EXTRACT_EVENT_TYPE = "memory.extract.conversation_range"


@dataclass(frozen=True)
class OutboxIntent:
    """An intent to write an outbox event atomically alongside a message.

    Encapsulates event_type and structured payload, avoiding primitive obsession
    and loose dict passing across conversation and write pipeline boundaries.
    """

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "event_type", require_text(self.event_type, "event_type")
        )
        if not isinstance(self.payload, dict):
            raise ConversationValidationError(
                "Conversation field 'payload' must be a dict."
            )


def coerce_outbox_intent(value: Any) -> OutboxIntent | None:
    """Coerce an OutboxIntent, dict, or None to an OutboxIntent instance."""
    if value is None:
        return None
    if isinstance(value, OutboxIntent):
        return value
    if isinstance(value, dict):
        event_type = value.get("event_type")
        if not isinstance(event_type, str) or not event_type.strip():
            raise ConversationValidationError(
                "A message outbox event requires a non-empty string 'event_type'."
            )
        payload = value.get("payload", {})
        if not isinstance(payload, dict):
            raise ConversationValidationError(
                "A message outbox event payload must be a dict."
            )
        return OutboxIntent(event_type=event_type.strip(), payload=dict(payload))
    raise ConversationValidationError(
        "Outbox event must be an OutboxIntent, dict, or None."
    )
