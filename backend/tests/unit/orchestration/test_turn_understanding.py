"""Task 4: `TurnUnderstanding` owns semantic interpretation.

The Stage-1 boundary (`plan v0.7:431-435`, `spec:272-275`) is that
`DialogueStateResolver` stays structural and `TurnUnderstanding` reads meaning
out of the current message **against** that structure. These tests pin both
halves of that claim:

- the same message with a different `DialogueState` produces a different reading,
  so context-dependent semantics live here and not in the resolver; and
- the resolution is deterministic-first and closed — every outcome carries a
  reason code from the approved vocabulary, and nothing is guessed into a
  durable action.

No test here touches a database, a model, HTTP, or the network.
"""

from __future__ import annotations

import ast
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
from backend.orchestration.dialogue_state import DialogueState, DialogueStateResolver
from backend.orchestration.turn_models import (
    DURABLE_ACTION_MODES,
    InteractionMode,
    TurnUnderstandingResult,
    UnderstandingReason,
)
from backend.orchestration.turn_understanding import TurnUnderstanding

UNDERSTANDING = TurnUnderstanding()
RESOLVER = DialogueStateResolver()

EMPTY_STATE = RESOLVER.resolve([])


def _message(sequence: int, role: MessageRole, content: str) -> Message:
    return Message(
        message_id=generate_message_id(),
        conversation_id="cv_" + "a" * 32,
        sequence=sequence,
        role=role,
        content=content,
        source=MessageSource.UI if role is MessageRole.USER else MessageSource.MODEL,
        created_at=utc_now(),
        status=MessageStatus.COMPLETE,
    )


def _state_with_prior_context() -> DialogueState:
    """One delivered exchange: something a follow-up can refer back to."""
    return RESOLVER.resolve(
        [
            _message(1, MessageRole.USER, "Gợi ý lịch trình Đà Nẵng 3 ngày"),
            _message(
                2,
                MessageRole.ASSISTANT,
                "Ngày 1: Bà Nà Hills. Ngày 2: biển Mỹ Khê. Ngày 3: Hội An.",
            ),
        ]
    )


def _understand(message: str, state: DialogueState = EMPTY_STATE):
    return UNDERSTANDING.understand(message, state)


# ---------------------------------------------------------------------------
# The closed result contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Hà Nội có gì đẹp?",
        "nhớ là tôi thích cà phê muối",
        "sửa lại, tôi thích trà sữa chứ không phải cà phê",
        "quên chuyện cà phê đi",
        "bạn nhớ gì về tôi?",
        '"nhớ là tôi thích cà phê muối"',
        "đừng nhớ chuyện đó",
        "nhớ nhưng cũng quên",
        "tiếp tục đi",
        "cái đầu tiên",
        "giữ cái đó nhưng đổi ngày",
    ],
)
def test_every_reading_is_a_closed_contract_with_a_reason(message):
    """No free text escapes: every outcome is typed and carries a closed reason."""
    result = _understand(message)

    assert isinstance(result, TurnUnderstandingResult)
    assert isinstance(result.interaction_mode, InteractionMode)
    assert result.reason_codes, f"{message!r} produced no reason code"
    for reason in result.reason_codes:
        assert isinstance(reason, UnderstandingReason)


def test_an_ordinary_query_claims_nothing():
    result = _understand("Hà Nội có gì đẹp?")

    assert result.interaction_mode is InteractionMode.NORMAL_QUERY
    assert result.reason_codes == (UnderstandingReason.NO_EXPLICIT_SIGNAL,)
    assert result.topics == ()
    assert result.needs_clarification is False


# ---------------------------------------------------------------------------
# Deterministic-first explicit recognition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,expected",
    [
        ("nhớ là tôi thích cà phê muối", InteractionMode.EXPLICIT_REMEMBER),
        ("remember that I prefer window seats", InteractionMode.EXPLICIT_REMEMBER),
        (
            "sửa lại, tôi thích trà sữa chứ không phải cà phê",
            InteractionMode.EXPLICIT_CORRECT,
        ),
        ("quên chuyện cà phê đi", InteractionMode.EXPLICIT_FORGET),
        ("forget my seat preference", InteractionMode.EXPLICIT_FORGET),
        ("bạn nhớ gì về tôi?", InteractionMode.EXPLICIT_INSPECT),
        ("what do you remember about me?", InteractionMode.EXPLICIT_INSPECT),
    ],
)
def test_an_obvious_explicit_command_is_recognised_deterministically(message, expected):
    result = _understand(message)

    assert result.interaction_mode is expected
    assert UnderstandingReason.DETERMINISTIC_MATCH in result.reason_codes


def test_a_quoted_command_is_not_issued():
    """Quoting someone else's command is a question about it, not an action.

    This is the high-precision safety check that runs before the domain rules
    (`spec:319-327`). Treating the quoted text as the user's own speech act would
    let a quotation authorize a durable write.
    """
    result = _understand('"nhớ là tôi thích cà phê muối"')

    assert result.interaction_mode is InteractionMode.NORMAL_QUERY
    assert result.reason_codes == (UnderstandingReason.QUOTED_SPEECH_ACT,)


def test_a_negated_command_never_becomes_the_action_it_names():
    """`đừng ghi nhớ …` must not be read as a remember.

    Negation is only meaningful when it governs a recognized durable cue, so the
    fixture uses the declarative form the vocabulary matches.
    """
    result = _understand("đừng ghi nhớ chuyện đó")

    assert result.interaction_mode is InteractionMode.AMBIGUOUS
    assert UnderstandingReason.NEGATED_SPEECH_ACT in result.reason_codes
    assert result.needs_clarification is True


def test_a_negation_of_a_bare_verb_is_simply_not_an_action():
    """With no durable cue recognized, nothing is proposed — which is the safe outcome.

    `đừng nhớ …` no longer matches a remember cue, so it proposes no mutation. The
    user's instruction is honoured by doing nothing, and the fail-closed direction
    is preserved.
    """
    result = _understand("đừng nhớ chuyện đó")

    assert result.interaction_mode not in DURABLE_ACTION_MODES


def test_conflicting_speech_acts_are_ambiguous_not_guessed():
    result = _understand("nhớ là tôi thích cà phê nhưng cũng quên")

    assert result.interaction_mode is InteractionMode.AMBIGUOUS
    assert UnderstandingReason.AMBIGUOUS_SPEECH_ACT in result.reason_codes
    assert result.needs_clarification is True


def test_inspect_is_recognised_but_declared_unavailable():
    """`explicit_inspect` is a capability Stage 1 cannot deliver (`spec:397-401`)."""
    result = _understand("bạn nhớ gì về tôi?")

    assert result.interaction_mode is InteractionMode.EXPLICIT_INSPECT
    assert UnderstandingReason.INSPECT_CAPABILITY_UNAVAILABLE in result.reason_codes
    assert result.current_assertions == ()


def test_no_durable_action_is_authorized_by_understanding_alone():
    """Understanding proposes; only the gate authorizes (`ADR 0036:34-41`)."""
    for message in (
        "nhớ là tôi thích cà phê muối",
        "sửa lại, tôi thích trà sữa",
        "quên chuyện cà phê đi",
    ):
        result = _understand(message)
        assert result.interaction_mode in DURABLE_ACTION_MODES
        # The result carries no authorization field at all — there is nothing a
        # caller could misread as permission.
        assert not hasattr(result, "authorized")


# ---------------------------------------------------------------------------
# Context-dependent turns: the semantics live HERE, not in the resolver
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    ["tiếp tục đi", "cái đầu tiên", "giữ cái đó nhưng đổi ngày"],
)
def test_a_context_dependent_turn_without_context_asks_for_clarification(message):
    """With nothing delivered yet, the referent does not exist.

    The resolver still returns a perfectly well-formed structural state; it is
    `TurnUnderstanding` that reads the missing referent out of the cue plus that
    state.
    """
    result = _understand(message, EMPTY_STATE)

    assert result.interaction_mode is InteractionMode.AMBIGUOUS
    assert UnderstandingReason.CONTEXT_MISSING in result.reason_codes
    assert result.needs_clarification is True


@pytest.mark.parametrize(
    "message",
    ["tiếp tục đi", "cái đầu tiên", "giữ cái đó nhưng đổi ngày"],
)
def test_the_same_cue_resolves_once_prior_context_exists(message):
    """Same message, different state, different reading.

    That difference is the proof that semantic interpretation belongs to
    `TurnUnderstanding`: a structural resolver cannot produce it, and the
    resolver's own contract has no field that could hold it.
    """
    result = _understand(message, _state_with_prior_context())

    assert result.interaction_mode is InteractionMode.NORMAL_QUERY
    assert UnderstandingReason.CONTEXT_REQUIRED in result.reason_codes
    assert result.needs_clarification is False


def test_a_continuation_inherits_the_prior_topic_from_the_state():
    result = _understand("tiếp tục đi", _state_with_prior_context())

    assert result.topics, "a resolved continuation must carry the topic it continues"


def test_the_first_referent_resolves_against_the_prior_answer():
    result = _understand("cái đầu tiên", _state_with_prior_context())

    assert result.entities, "the first referent must name something from the state"


def test_an_override_records_what_changes_and_keeps_the_rest():
    result = _understand("giữ cái đó nhưng đổi ngày", _state_with_prior_context())

    assert result.current_overrides, "an override must record the dimension it changes"


def test_the_resolver_contributes_no_semantics_of_its_own():
    """The boundary, stated as an executable check.

    `DialogueState` exposes structure only. If a topic or referent field ever
    appears there, interpretation has leaked back into the resolver.
    """
    state = _state_with_prior_context()

    assert set(vars(state)) == {"turns", "latest_user_turn", "latest_assistant_turn"}


# ---------------------------------------------------------------------------
# Determinism and dependency boundary
# ---------------------------------------------------------------------------


def test_understanding_is_deterministic():
    message = "giữ cái đó nhưng đổi ngày"
    state = _state_with_prior_context()

    assert UNDERSTANDING.understand(message, state) == UNDERSTANDING.understand(
        message, state
    )


def test_understanding_reaches_no_model_provider_or_storage():
    """Stage 1 is deterministic-first and makes no model call (`plan v0.7:468-472`)."""
    forbidden = (
        "fastapi",
        "sqlalchemy",
        "backend.memory",
        "backend.rag",
        "backend.observability",
        "backend.storage",
        "openai",
        "requests",
        "httpx",
    )
    path = Path(__file__).resolve().parents[3] / "orchestration" / "turn_understanding.py"
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


def test_the_parser_failure_reason_is_reserved_and_unemitted():
    """The vocabulary carries the bounded-parser failure mode; Stage 1 never emits it.

    No Stage-1 path makes a model call, so a parser-failure reading would be a
    fabricated cause.
    """
    for message in (
        "Hà Nội có gì đẹp?",
        "nhớ là tôi thích cà phê muối",
        "tiếp tục đi",
        "đừng nhớ chuyện đó",
    ):
        assert (
            UnderstandingReason.PARSER_FAILED_CLOSED not in _understand(message).reason_codes
        )


# ---------------------------------------------------------------------------
# Precision: a question is not a command (review finding 1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "bạn có nhớ tôi không?",
        "khi nào tôi nên nhớ đặt vé?",
        "tôi nhớ",
        "nhớ",
    ],
)
def test_a_memory_verb_inside_a_question_is_not_a_durable_command(message):
    """Bare `nhớ` appears in questions too, and a question cannot authorize a write.

    The remember cues are declarative/imperative forms for exactly this reason.
    """
    result = _understand(message)

    assert result.interaction_mode not in DURABLE_ACTION_MODES


def test_a_question_about_memory_is_recognised_as_inspect():
    result = _understand("bạn có nhớ gì về tôi không?")

    assert result.interaction_mode is InteractionMode.EXPLICIT_INSPECT


# ---------------------------------------------------------------------------
# Quoting fails closed (review findings 5 and 6)
# ---------------------------------------------------------------------------


def test_an_unterminated_quote_does_not_expose_the_text_as_the_users_own():
    """Failing open here would authorize a write from possibly-quoted text."""
    result = _understand('"nhớ là tôi thích cà phê muối')

    assert result.interaction_mode not in DURABLE_ACTION_MODES
    assert result.reason_codes == (UnderstandingReason.QUOTED_SPEECH_ACT,)


def test_a_quoted_second_cue_does_not_create_a_conflict():
    """Only the user's own words count toward the speech-act conflict."""
    result = _understand('nhớ là tôi thích "quên"')

    assert result.interaction_mode is InteractionMode.EXPLICIT_REMEMBER
    assert UnderstandingReason.AMBIGUOUS_SPEECH_ACT not in result.reason_codes
