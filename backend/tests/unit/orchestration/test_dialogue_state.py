"""Task 3: `DialogueState` is ephemeral, structural, and rebuilt per turn.

`spec:907` scopes Stage 1 to **recent turns only**, and `plan:355` forbids a
model, a DB write, and a Working Memory dependency. So the resolver reconstructs
only facts about the rows it is handed: which turns were delivered, in what
order, and which assistant turn a follow-up could continue from. It infers no
topic and no goal — those arrive with Working Memory in Stage 5 (`spec:265-267`),
and a model-free function over message rows could not produce them anyway.

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


def _message(
    sequence: int,
    role: MessageRole,
    content: str,
    status: MessageStatus = MessageStatus.COMPLETE,
) -> Message:
    return Message(
        message_id=generate_message_id(),
        conversation_id="cv_" + "0" * 32,
        sequence=sequence,
        role=role,
        content=content,
        source=MessageSource.UI if role is MessageRole.USER else MessageSource.MODEL,
        created_at=utc_now(),
        status=status,
    )


def _user(sequence: int, content: str) -> Message:
    return _message(sequence, MessageRole.USER, content)


def _assistant(
    sequence: int,
    content: str,
    status: MessageStatus = MessageStatus.COMPLETE,
) -> Message:
    return _message(sequence, MessageRole.ASSISTANT, content, status)


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
    """A brand-new conversation has no rows, and that is not an error."""
    state = RESOLVER.resolve([])

    assert state.turns == ()
    assert state.latest_user_turn is None
    assert state.latest_assistant_turn is None


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
    """A context-dependent turn such as "tiếp tục đi" has no referent yet.

    This is the state Task 4's understanding reads; the resolver does not
    interpret the cue itself (`plan:351-352`, `spec:260-264`).
    """
    assert RESOLVER.resolve(_first_turn_shape()).latest_assistant_turn is None


def test_a_completed_exchange_offers_something_to_continue():
    """After one answered turn, a follow-up does have prior context."""
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
    """An immutable closed contract, per `plan:354`."""
    state = RESOLVER.resolve([])

    with pytest.raises(dataclasses.FrozenInstanceError):
        state.turns = ()  # type: ignore[misc]


def test_dialogue_state_reaches_no_memory_persistence_or_provider():
    """The plan's review gate (`plan:357-358`) and `spec:530-531`."""
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
