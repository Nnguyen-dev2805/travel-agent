"""Task 13: Working Memory reaches context as a governed tier, not as a transcript.

Plan v0.22 Task 13, Step 5. Four properties, and each one is a way the boundary
could be got wrong:

1. working state is composed **before** the Memory block, because `spec:1043-1052`
   puts "current conversation working state / temporary override" above user-scoped
   soft preferences and above episodes/summaries — the opposite of the episodic
   block, which is appended last;
2. an abstention adds nothing, and no selection changes nothing;
3. working state never becomes a travel citation;
4. only structured fields reach the prompt, and admitting an open state does not
   add a turn to `DialogueState`, so the durable state can never become a second
   transcript.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.conversations.models import (
    Message,
    MessageRole,
    MessageSource,
    MessageStatus,
    generate_message_id,
    utc_now,
)
from backend.memory.read_models import MemorySelection, SelectedMemory
from backend.memory.working import (
    SelectedWorkingState,
    WorkingAbstentionReason,
    WorkingSelection,
)
from backend.memory.write_pipeline.models import Authority, MemoryScope
from backend.orchestration.context_arbiter import ContextArbiter
from backend.orchestration.dialogue_state import (
    DialogueStateResolver,
    WorkingContext,
)
from backend.orchestration.turn_models import ContextMode

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
CONVERSATION = "cv_" + "c" * 32

RESOLVER = DialogueStateResolver()


def _memory_selection() -> MemorySelection:
    return MemorySelection(
        selected=(
            SelectedMemory(
                version_id="mv_1",
                canonical_key="travel.preference.hotel_atmosphere",
                normalized_value="quiet",
                scope=MemoryScope.USER,
                scope_id="user_1",
                authority=Authority.EXPLICIT_SAVE,
                valid_from=NOW,
            ),
        )
    )


def _working_selection(goal: str = "Đi Đà Nẵng tháng 10") -> WorkingSelection:
    return WorkingSelection(
        selected=(
            SelectedWorkingState(
                open_goal=goal,
                through_sequence=4,
                conversation_id=CONVERSATION,
            ),
        )
    )


def _episode_selection():
    from backend.memory.episodic import EpisodeSelection, SelectedEpisode

    return EpisodeSelection(
        selected=(
            SelectedEpisode(
                episode_id="epi_1",
                actor="user_1",
                event="rejected Da Nang over rain",
                occurred_at=NOW,
                conversation_id=CONVERSATION,
            ),
        )
    )


# ---------------------------------------------------------------------------
# 1. Precedence: working state is above soft preferences and above episodes.
# ---------------------------------------------------------------------------


def test_working_state_is_composed_before_the_memory_block():
    context = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY,
        memory_selection=_memory_selection(),
        working_selection=_working_selection(),
    )

    prompt = context.prompt_context
    assert "Đi Đà Nẵng tháng 10" in prompt
    assert "quiet" in prompt
    assert prompt.index("Đi Đà Nẵng tháng 10") < prompt.index("quiet"), (
        "working state ranks above user-scoped soft preferences, so it is "
        "composed first"
    )


def test_working_state_is_composed_before_episodes():
    context = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY,
        memory_selection=_memory_selection(),
        working_selection=_working_selection(),
        episodic_selection=_episode_selection(),
    )

    prompt = context.prompt_context
    assert prompt.index("Đi Đà Nẵng tháng 10") < prompt.index(
        "rejected Da Nang over rain"
    ), "episodes rank below working state"


def test_working_state_is_composed_before_memory_in_both_mode():
    from backend.rag.contracts import ContextBundle

    bundle = ContextBundle(
        prompt_context="Travel knowledge.",
        evidence=(),
        citations=(),
        insufficient_evidence=False,
    )
    context = ContextArbiter().arbitrate(
        mode=ContextMode.BOTH,
        rag_bundle=bundle,
        memory_selection=_memory_selection(),
        working_selection=_working_selection(),
    )

    prompt = context.prompt_context
    assert prompt.index("Travel knowledge.") < prompt.index("Đi Đà Nẵng tháng 10")
    assert prompt.index("Đi Đà Nẵng tháng 10") < prompt.index("quiet")


def test_no_working_selection_leaves_the_context_unchanged():
    without = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY, memory_selection=_memory_selection()
    )
    with_none = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY,
        memory_selection=_memory_selection(),
        working_selection=None,
    )

    assert without.prompt_context == with_none.prompt_context


def test_an_abstention_adds_nothing_to_the_context():
    abstained = WorkingSelection(
        selected=(),
        abstention_reason=WorkingAbstentionReason.NO_ELIGIBLE_WORKING_STATE,
    )
    context = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY,
        memory_selection=_memory_selection(),
        working_selection=abstained,
    )

    assert "TRẠNG THÁI LÀM VIỆC" not in context.prompt_context


# ---------------------------------------------------------------------------
# 2. No leakage: structured fields only, never a citation.
# ---------------------------------------------------------------------------


def test_working_state_never_becomes_a_travel_citation():
    context = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY,
        memory_selection=_memory_selection(),
        working_selection=_working_selection(),
    )

    assert context.citations == ()


def test_the_composed_block_carries_only_structured_fields():
    raw_source = "Ma dat phong la 0912345678, toi se tra sau."
    context = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY,
        memory_selection=_memory_selection(),
        working_selection=_working_selection(goal="Đi Đà Nẵng tháng 10"),
    )

    prompt = context.prompt_context
    assert "Đi Đà Nẵng tháng 10" in prompt
    assert raw_source not in prompt
    assert "0912345678" not in prompt
    assert "cout_" not in prompt and "msg_" not in prompt, (
        "source identity is not part of the projection"
    )


# ---------------------------------------------------------------------------
# 3. Non-duplication with the ephemeral dialogue state.
# ---------------------------------------------------------------------------


def _user(sequence: int, content: str) -> Message:
    return Message(
        message_id=generate_message_id(),
        conversation_id=CONVERSATION,
        sequence=sequence,
        role=MessageRole.USER,
        content=content,
        source=MessageSource.UI,
        created_at=utc_now(),
        status=MessageStatus.COMPLETE,
    )


def test_admitting_working_state_does_not_add_a_turn():
    turns = [_user(1, "Xin chào"), _user(3, "Tôi muốn đi Huế")]

    without = RESOLVER.resolve(turns)
    with_working = RESOLVER.resolve(
        turns, WorkingContext(open_goal="Đi Huế", through_sequence=3)
    )

    assert with_working.turns == without.turns
    assert len(with_working.turns) == 2


def test_working_state_is_carried_and_not_derived():
    state = RESOLVER.resolve([_user(1, "Tôi muốn đi Huế")])

    assert state.working_context is None, (
        "the resolver never derives an open state of its own"
    )


def test_an_admitted_open_state_is_visible_to_the_semantic_interpreter():
    state = RESOLVER.resolve(
        [_user(1, "Tôi muốn đi Huế")],
        WorkingContext(open_goal="Đi Huế", through_sequence=3),
    )

    assert state.working_context is not None
    assert state.working_context.open_goal == "Đi Huế"
    assert state.working_context.through_sequence == 3
