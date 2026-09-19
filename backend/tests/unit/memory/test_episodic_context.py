"""Step 5: episodic selection reaches generation context as structured data only.

Plan v0.20 Task 12 Step 5. Three properties, and each one is a way the boundary
could be got wrong:

1. episodes are appended **after** the Memory block, because episodes sit below
   the current request, verified hard constraints and user-scoped soft
   preferences in the precedence ladder;
2. an episode contributes only its structured fields — a recorded event is not a
   channel for the transcript it came from;
3. an episode never becomes a travel citation, and an abstention adds nothing.
"""

from datetime import datetime, timedelta, timezone

from backend.memory.episodic import (
    EpisodeAbstentionReason,
    EpisodeSelection,
    SelectedEpisode,
)
from backend.memory.read_models import MemorySelection, SelectedMemory
from backend.memory.write_pipeline.models import Authority, MemoryScope
from backend.orchestration.context_arbiter import ContextArbiter
from backend.orchestration.turn_models import ContextMode

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


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


def _episode_selection(event: str = "rejected Da Nang over rain") -> EpisodeSelection:
    return EpisodeSelection(
        selected=(
            SelectedEpisode(
                episode_id="epi_1",
                actor="user_1",
                event=event,
                occurred_at=NOW,
                conversation_id="conv_1",
            ),
        )
    )


def test_episodes_are_appended_after_the_memory_block():
    context = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY,
        memory_selection=_memory_selection(),
        episodic_selection=_episode_selection(),
    )

    prompt = context.prompt_context
    assert "quiet" in prompt
    assert "rejected Da Nang over rain" in prompt
    assert prompt.index("quiet") < prompt.index("rejected Da Nang over rain"), (
        "episodes rank below soft preferences, so they are appended last"
    )


def test_an_abstention_adds_nothing_to_the_context():
    abstained = EpisodeSelection(
        selected=(), abstention_reason=EpisodeAbstentionReason.NO_ELIGIBLE_EPISODE
    )
    context = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY,
        memory_selection=_memory_selection(),
        episodic_selection=abstained,
    )
    assert "SỰ KIỆN ĐÃ GHI NHẬN" not in context.prompt_context


def test_no_episodic_selection_leaves_the_context_unchanged():
    without = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY, memory_selection=_memory_selection()
    )
    with_none = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY,
        memory_selection=_memory_selection(),
        episodic_selection=None,
    )
    assert without.prompt_context == with_none.prompt_context


def test_an_episode_never_becomes_a_travel_citation():
    context = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY,
        memory_selection=_memory_selection(),
        episodic_selection=_episode_selection(),
    )
    assert context.citations == ()


def test_the_composed_block_carries_only_structured_fields():
    """The raw source text must not appear, only the governed event summary."""
    raw_source = "Khoan da, toi nghi lai roi. Ma dat phong la 0912345678."
    context = ContextArbiter().arbitrate(
        mode=ContextMode.MEMORY_ONLY,
        memory_selection=_memory_selection(),
        episodic_selection=_episode_selection(event="rejected Da Nang over rain"),
    )

    prompt = context.prompt_context
    assert "rejected Da Nang over rain" in prompt
    assert raw_source not in prompt
    assert "0912345678" not in prompt
    # actor and time are the only other things an episode contributes
    assert "user_1" in prompt
    assert NOW.isoformat() in prompt
