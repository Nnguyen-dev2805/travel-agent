"""Task 3: `DialogueState` is ephemeral, structural, and rebuilt per turn.

Stage-1 responsibility is split by design (`plan:343-348`, `spec:265-275`).
`DialogueStateResolver` assembles deterministic structural context from exactly
one conversation: which turns were delivered, in what order, and which assistant
turn exists to build on. `TurnUnderstanding` (Task 4) owns semantic
interpretation of the current message against that context — topic, referents,
current goal, intent, and pending clarification.

So the resolver infers none of those, and must not: a model-free, database-free,
Working-Memory-free function over message rows cannot produce them. Working Memory
becomes an additional **reconstruction** input in Stage 5 without moving semantic
ownership out of `TurnUnderstanding` (`spec:279-281`).

Only `COMPLETE` rows are turns, and that is the persistence contract rather than
an invented rule: `conversations/models.py:278-285` guarantees content for a
`COMPLETE` row, while the writer empties the others —
`ConversationRepository.fail_turn` (`conversations/postgres_repository.py:791-805`)
stores `content=""` and a `PENDING` row is an in-flight placeholder. A row with no
content cannot contribute dialogue state.

No test here touches a database, a model, HTTP, or the network.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from backend.conversations.models import (
    ConversationValidationError,
    Message,
    MessageRole,
    MessageSource,
    MessageStatus,
    generate_message_id,
    utc_now,
)
from backend.orchestration.dialogue_state import (
    DialogueState,
    DialogueStateResolver,
)

RESOLVER = DialogueStateResolver()

CONVERSATION_A = "cv_" + "a" * 32
CONVERSATION_B = "cv_" + "b" * 32


def _message(
    sequence: int,
    role: MessageRole,
    content: str,
    status: MessageStatus = MessageStatus.COMPLETE,
    conversation_id: str = CONVERSATION_A,
) -> Message:
    return Message(
        message_id=generate_message_id(),
        conversation_id=conversation_id,
        sequence=sequence,
        role=role,
        content=content,
        source=MessageSource.UI if role is MessageRole.USER else MessageSource.MODEL,
        created_at=utc_now(),
        status=status,
    )


def _user(
    sequence: int, content: str, conversation_id: str = CONVERSATION_A
) -> Message:
    return _message(sequence, MessageRole.USER, content, conversation_id=conversation_id)


def _assistant(
    sequence: int,
    content: str,
    status: MessageStatus = MessageStatus.COMPLETE,
    conversation_id: str = CONVERSATION_A,
) -> Message:
    return _message(
        sequence, MessageRole.ASSISTANT, content, status, conversation_id=conversation_id
    )


def _first_turn_shape() -> list[Message]:
    """The exact rows phase one of a first chat turn writes.

    A completed user message plus an **empty** `PENDING` assistant placeholder
    (`tests/unit/test_conversation_orchestrator.py:137-158`).
    """
    return [
        _user(1, "Hà Nội có gì đẹp?"),
        _assistant(2, "", MessageStatus.PENDING),
    ]


def test_an_empty_history_yields_an_empty_state():
    """A brand-new conversation has no rows, and that is not an error.

    Also the negative control for the single-conversation guard: no rows means no
    scope conflict, so an empty input must stay a success rather than raise.
    """
    state = RESOLVER.resolve([])

    assert state.turns == ()
    assert state.latest_user_turn is None
    assert state.latest_assistant_turn is None


def test_rows_from_one_conversation_are_accepted():
    """One conversation is the only supported input, and it must still work.

    Pins the assembled state, not just the count: a guard that silently consumed
    the input would still produce a well-formed but empty state.
    """
    state = RESOLVER.resolve(
        [
            _user(1, "Hà Nội có gì đẹp?"),
            _assistant(2, "Phố cổ và hồ Hoàn Kiếm."),
        ]
    )

    assert [turn.sequence for turn in state.turns] == [1, 2]
    assert state.latest_user_turn.sequence == 1
    assert state.latest_assistant_turn.sequence == 2


def test_a_one_shot_iterable_is_not_silently_emptied():
    """The scope guard must not consume the input it is validating.

    `Sequence` is the declared type, but a one-shot iterable would be drained by
    the scope check, and the resolver would then return an empty state instead of
    the rows it was handed — a fail-open path inside the guard whose whole job is
    to fail closed.
    """
    rows = [
        _user(1, "Hà Nội có gì đẹp?"),
        _assistant(2, "Phố cổ và hồ Hoàn Kiếm."),
    ]

    assert len(RESOLVER.resolve(iter(rows)).turns) == 2


def test_mixed_conversation_input_fails_closed():
    """Rows from more than one conversation must be refused (`spec:268-269`).

    The signature carries no conversation identity (`plan:340`), so the rows are
    the only evidence of scope. Before this rule the resolver merged two
    conversations into one plausible state — `latest_user_turn` from one
    conversation and `latest_assistant_turn` from another.
    """
    with pytest.raises(ConversationValidationError):
        RESOLVER.resolve(
            [
                _user(1, "Kế hoạch Hà Nội của tôi"),
                _assistant(2, "Dạ, tôi đã ghi nhớ.", conversation_id=CONVERSATION_B),
            ]
        )


def test_a_supplied_foreign_row_fails_closed_even_when_it_would_be_filtered():
    """Scope is decided on the rows **supplied**, not on the rows retained.

    `spec:268-269` says "fail closed if rows from more than one conversation are
    supplied". A `PENDING` row from another conversation is filtered out of
    `turns`, but it is still a foreign row in the input, and accepting it would
    make the isolation rule depend on the eligibility filter.
    """
    with pytest.raises(ConversationValidationError):
        RESOLVER.resolve(
            [
                _user(1, "Kế hoạch Hà Nội của tôi"),
                _assistant(
                    2, "", MessageStatus.PENDING, conversation_id=CONVERSATION_B
                ),
            ]
        )


def test_turns_are_ordered_by_sequence_not_input_order():
    """`sequence` exists so turn order is a fact, not an inference.

    `conversations/models.py:429-431`: a stored monotonic integer "rather than an
    inferred timestamp comparison, because later provenance depends on turn order
    being a fact". Trusting caller order would make determinism the caller's job.
    """
    state = RESOLVER.resolve(
        [
            _assistant(2, "Phố cổ và hồ Hoàn Kiếm."),
            _user(1, "Hà Nội có gì đẹp?"),
        ]
    )

    assert [turn.sequence for turn in state.turns] == [1, 2]
    assert state.latest_user_turn.content == "Hà Nội có gì đẹp?"


def test_a_pending_placeholder_is_not_a_turn():
    """The empty placeholder must not become the latest assistant turn."""
    state = RESOLVER.resolve(_first_turn_shape())

    assert [turn.sequence for turn in state.turns] == [1]
    assert state.latest_assistant_turn is None
    assert state.latest_user_turn.sequence == 1


def test_a_failed_row_is_not_a_turn():
    """ADR 0023: a `FAILED` row carries no generated content by construction."""
    state = RESOLVER.resolve(
        [
            _user(1, "Hà Nội có gì đẹp?"),
            _assistant(2, "", MessageStatus.FAILED),
        ]
    )

    assert state.latest_assistant_turn is None


def test_only_delivered_roles_are_turns():
    """Dialogue state is the exchange between the user and the assistant.

    `TOOL` and `SYSTEM_EVENT` rows exist in the vocabulary
    (`conversations/models.py:55-61`) but are not dialogue. Pinning this makes a
    future writer a deliberate change rather than a silent shift in state.
    """
    state = RESOLVER.resolve(
        [
            _user(1, "Hà Nội có gì đẹp?"),
            _message(2, MessageRole.TOOL, "search results"),
            _message(3, MessageRole.SYSTEM_EVENT, "turn started"),
            _assistant(4, "Phố cổ và hồ Hoàn Kiếm."),
        ]
    )

    assert [turn.sequence for turn in state.turns] == [1, 4]


def test_the_latest_user_turn_is_the_last_complete_user_row():
    state = RESOLVER.resolve(
        [
            _user(1, "Hà Nội có gì đẹp?"),
            _assistant(2, "Phố cổ và hồ Hoàn Kiếm."),
            _user(3, "Còn Đà Nẵng?"),
        ]
    )

    assert state.latest_user_turn.content == "Còn Đà Nẵng?"


def test_a_first_turn_has_nothing_to_continue():
    """A first turn has no delivered assistant turn to build on.

    Structural only — this is the state `TurnUnderstanding` reads. Whether the
    current message is a context-dependent turn such as "tiếp tục đi" is decided
    there, not here (`plan:400-403`, `spec:272-275`).
    """
    assert RESOLVER.resolve(_first_turn_shape()).latest_assistant_turn is None


def test_a_completed_exchange_offers_something_to_continue():
    """After one delivered exchange, structural context exists to build on."""
    state = RESOLVER.resolve(
        [
            _user(1, "Hà Nội có gì đẹp?"),
            _assistant(2, "Phố cổ và hồ Hoàn Kiếm."),
        ]
    )

    assert state.latest_assistant_turn.content == "Phố cổ và hồ Hoàn Kiếm."


def test_the_state_does_not_depend_on_the_order_of_the_input():
    """Two orderings of the same rows must produce equal state.

    Resolving one list twice would be near-tautological. Reversing the input
    proves the resolver normalizes by `sequence` instead of trusting the caller.
    """
    turns = [
        _user(1, "Hà Nội có gì đẹp?"),
        _assistant(2, "Phố cổ và hồ Hoàn Kiếm."),
        _user(3, "Còn Đà Nẵng?"),
    ]

    assert RESOLVER.resolve(turns) == RESOLVER.resolve(list(reversed(turns)))


def test_the_state_is_frozen():
    """An immutable closed contract, per `plan:363-365`."""
    state = RESOLVER.resolve([])

    with pytest.raises(dataclasses.FrozenInstanceError):
        state.turns = ()  # type: ignore[misc]


def test_dialogue_state_reaches_no_memory_persistence_or_provider():
    """The plan's review gate (`plan:367-368`) and `spec:555`."""
    forbidden = (
        "fastapi",
        "sqlalchemy",
        "backend.memory",
        "backend.rag",
        "backend.observability",
        "backend.storage",
    )
    path = Path(__file__).resolve().parents[3] / "orchestration" / "dialogue_state.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not [
        module
        for module in imported
        for banned in forbidden
        if module == banned or module.startswith(f"{banned}.")
    ], imported
