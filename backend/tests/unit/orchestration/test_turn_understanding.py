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
    result = _understand("nhớ là tôi thích cà phê, nhưng quên chuyện cũ đi")

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

    assert set(vars(state)) == {
        "turns",
        "latest_user_turn",
        "latest_assistant_turn",
        # Stage 5: eligible Working Memory is an additional governed *input* to
        # reconstruction (`spec:324-328`). It is carried, never inferred — there
        # is still no topic, referent or goal field the resolver computes.
        "working_context",
    }
    assert state.working_context is None, (
        "the resolver never derives an open state of its own; orchestration reads "
        "one from the governed store and passes it in"
    )


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


# ---------------------------------------------------------------------------
# A question or a mention is not a speech act (review fix 1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Should I remember to bring a passport?",
        "Can you remember what I said?",
        "Why do people forget things?",
        "quên mang hộ chiếu thì làm sao?",
        "xóa nghĩa là gì?",
    ],
)
def test_a_question_or_mention_never_authorizes_a_durable_action(message):
    """A cue word appearing in a question is not the user issuing a command.

    Precision is the whole point of this layer: a false positive here would
    authorize a durable write from a question about Memory.
    """
    result = _understand(message)

    assert result.interaction_mode not in DURABLE_ACTION_MODES


@pytest.mark.parametrize(
    "message",
    [
        "Should I remember to bring a passport?",
        "quên mang hộ chiếu thì làm sao?",
        "xóa nghĩa là gì?",
    ],
)
def test_a_question_never_reaches_the_gate_as_an_action(message):
    """The gate must never be asked to authorize a question."""
    from backend.orchestration.action_router import ActionRouter
    from backend.orchestration.turn_models import RoutingDecision

    decision = ActionRouter().route(_understand(message))

    assert decision is not RoutingDecision.EXPLICIT_MEMORY_ACTION


def test_an_imperative_command_is_still_recognised():
    """The question gate must not swallow real commands."""
    for message, expected in (
        ("nhớ là tôi thích cà phê muối", InteractionMode.EXPLICIT_REMEMBER),
        ("ghi nhớ giúp tôi: tôi thích ghế cửa sổ", InteractionMode.EXPLICIT_REMEMBER),
        ("quên chuyện cà phê đi", InteractionMode.EXPLICIT_FORGET),
        ("forget my seat preference", InteractionMode.EXPLICIT_FORGET),
    ):
        result = _understand(message)
        assert result.interaction_mode is expected, message


# ---------------------------------------------------------------------------
# Context-dependent replies, not only the three cue phrases (review fix 3)
# ---------------------------------------------------------------------------


def _state_ending_in_a_question() -> DialogueState:
    return RESOLVER.resolve(
        [
            _message(1, MessageRole.USER, "Gợi ý lịch trình Đà Nẵng"),
            _message(2, MessageRole.ASSISTANT, "Bạn muốn đi mấy ngày?"),
        ]
    )


def test_a_reply_to_a_pending_clarification_is_resolved_against_it():
    """Any reply, not just a hard-coded cue phrase, resolves against the question.

    The pending question is derived from the structural state — the last
    delivered assistant turn asked something — so no semantic field had to move
    into `DialogueState`.
    """
    result = UNDERSTANDING.understand("3 ngày", _state_ending_in_a_question())

    assert result.answers_pending_clarification is True
    assert result.current_goal, "the active goal must be carried"
    assert UnderstandingReason.CONTEXT_REQUIRED in result.reason_codes


def test_a_reply_after_a_statement_is_not_a_clarification_answer():
    state = RESOLVER.resolve(
        [
            _message(1, MessageRole.USER, "Gợi ý lịch trình Đà Nẵng"),
            _message(2, MessageRole.ASSISTANT, "Ngày 1: Bà Nà Hills."),
        ]
    )

    result = UNDERSTANDING.understand("cảm ơn", state)

    assert result.answers_pending_clarification is False


def test_a_cue_phrase_still_wins_over_the_pending_clarification_reading():
    """A real speech act is not demoted to "answering a question"."""
    result = UNDERSTANDING.understand(
        "nhớ là tôi thích cà phê muối", _state_ending_in_a_question()
    )

    assert result.interaction_mode is InteractionMode.EXPLICIT_REMEMBER
    assert result.answers_pending_clarification is False


def test_the_current_goal_is_derived_from_the_conversation_not_the_message():
    state = _state_ending_in_a_question()

    result = UNDERSTANDING.understand("3 ngày", state)

    assert result.current_goal == state.latest_user_turn.content


# ---------------------------------------------------------------------------
# A statement about memory is not a speech act (re-review finding 1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "I remember my trip to Paris.",
        "People forget their passports all the time.",
        "Tôi quên mang hộ chiếu hôm qua.",
        "Delete is a common database operation.",
    ],
)
def test_a_statement_about_memory_is_not_a_speech_act(message):
    """A cue word in a *statement* is a description, not an instruction.

    `I remember …` and `People forget …` are the user talking about memory, not
    asking the assistant to change durable state. Treating the cue's presence as
    corroboration is what "deterministically corroborate a speech act" forbids.
    """
    result = _understand(message)

    assert result.interaction_mode not in DURABLE_ACTION_MODES


@pytest.mark.parametrize(
    "message",
    [
        "I remember my trip to Paris.",
        "People forget their passports all the time.",
        "Tôi quên mang hộ chiếu hôm qua.",
        "Delete is a common database operation.",
    ],
)
def test_a_statement_never_reaches_the_gate_as_an_action(message):
    from backend.orchestration.action_router import ActionRouter
    from backend.orchestration.turn_models import RoutingDecision

    assert (
        ActionRouter().route(_understand(message))
        is not RoutingDecision.EXPLICIT_MEMORY_ACTION
    )


@pytest.mark.parametrize(
    "message,expected",
    [
        ("nhớ là tôi thích cà phê muối", InteractionMode.EXPLICIT_REMEMBER),
        ("hãy nhớ là tôi thích ghế cửa sổ", InteractionMode.EXPLICIT_REMEMBER),
        ("quên chuyện cà phê đi", InteractionMode.EXPLICIT_FORGET),
        ("forget my seat preference", InteractionMode.EXPLICIT_FORGET),
        ("please remember that I prefer trains", InteractionMode.EXPLICIT_REMEMBER),
    ],
)
def test_an_addressed_command_is_still_a_speech_act(message, expected):
    """The speech-act frame must not swallow real commands, addressed or bare."""
    assert _understand(message).interaction_mode is expected


# ---------------------------------------------------------------------------
# The current goal survives a clarification exchange (re-review finding 3)
# ---------------------------------------------------------------------------


def _state_after_two_clarifications() -> DialogueState:
    """A goal, then two question-and-answer exchanges about it."""
    return RESOLVER.resolve(
        [
            _message(1, MessageRole.USER, "Lên lịch Đà Nẵng 3 ngày"),
            _message(2, MessageRole.ASSISTANT, "Bạn ưu tiên biển hay văn hóa?"),
            _message(3, MessageRole.USER, "Biển"),
            _message(4, MessageRole.ASSISTANT, "Ngân sách bao nhiêu?"),
            _message(5, MessageRole.USER, "5 triệu"),
        ]
    )


def test_the_current_goal_is_the_original_request_not_the_last_answer():
    """A clarification answer is not the goal; the request that started it is.

    Setting the goal to the immediately preceding user turn made it `Biển`,
    which is an answer to a question rather than what the conversation is for.
    """
    state = _state_after_two_clarifications()

    result = UNDERSTANDING.understand("Vậy lên lịch giúp tôi", state)

    assert result.current_goal == "Lên lịch Đà Nẵng 3 ngày"
    assert result.answers_pending_clarification is True


def test_the_active_topic_follows_the_goal_not_the_last_answer():
    state = _state_after_two_clarifications()

    result = UNDERSTANDING.understand("Vậy lên lịch giúp tôi", state)

    assert result.topics == ("Lên lịch Đà Nẵng 3 ngày",)


# ---------------------------------------------------------------------------
# Position is not enough: the verb must be in an imperative frame (round 3, 1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Quên mang hộ chiếu rất phiền.",
        "Quên mang hộ chiếu làm chuyến đi rất mệt.",
        "Delete rows in SQL uses DELETE FROM.",
    ],
)
def test_a_bare_verb_at_the_start_of_a_comment_is_not_a_command(message):
    """Being first is not enough — a comment also starts with the verb.

    `Quên mang hộ chiếu rất phiền.` and `Delete rows in SQL uses DELETE FROM.`
    are statements whose subject happens to be the verb. The cue must be in an
    imperative **frame**, not merely at position zero.
    """
    result = _understand(message)

    assert result.interaction_mode not in DURABLE_ACTION_MODES


def test_a_refused_frame_reports_why_it_was_refused():
    """`MENTION_NOT_SPEECH_ACT` names a frame that was present but refused.

    A message with no frame at all has nothing to explain and stays
    `NO_EXPLICIT_SIGNAL`; the two are different diagnoses.
    """
    refused = _understand("I remember that I went to Paris.")

    assert UnderstandingReason.MENTION_NOT_SPEECH_ACT in refused.reason_codes

    no_frame = _understand("Why do people forget things?")

    assert no_frame.reason_codes == (UnderstandingReason.NO_EXPLICIT_SIGNAL,)


@pytest.mark.parametrize(
    "message",
    [
        "Quên mang hộ chiếu rất phiền.",
        "Delete rows in SQL uses DELETE FROM.",
    ],
)
def test_a_comment_never_reaches_the_gate_as_an_action(message):
    from backend.orchestration.action_router import ActionRouter
    from backend.orchestration.turn_models import RoutingDecision

    assert (
        ActionRouter().route(_understand(message))
        is not RoutingDecision.EXPLICIT_MEMORY_ACTION
    )


def test_a_statement_using_an_imperative_frame_is_still_not_a_command():
    """`I remember that …` has the frame but is still the user describing himself."""
    result = _understand("I remember that I went to Paris.")

    assert result.interaction_mode not in DURABLE_ACTION_MODES


@pytest.mark.parametrize(
    "message,expected",
    [
        ("quên chuyện cà phê đi", InteractionMode.EXPLICIT_FORGET),
        ("xóa ghi chú đó đi", InteractionMode.EXPLICIT_FORGET),
        ("forget my seat preference", InteractionMode.EXPLICIT_FORGET),
        ("forget that I said that", InteractionMode.EXPLICIT_FORGET),
    ],
)
def test_the_forget_frame_is_still_recognised(message, expected):
    """`quên … đi` and `forget that/my` are the frames; a bare verb is not."""
    assert _understand(message).interaction_mode is expected


def test_a_command_addressed_through_a_subject_is_recognised():
    """`Tôi muốn bạn nhớ là …` is a command; the assistant is the addressee."""
    result = _understand("Tôi muốn bạn nhớ là tôi thích cà phê muối")

    assert result.interaction_mode is InteractionMode.EXPLICIT_REMEMBER


# ---------------------------------------------------------------------------
# A topic change is not a clarification answer (round 3, 3)
# ---------------------------------------------------------------------------


def _state_with_an_open_question() -> DialogueState:
    return RESOLVER.resolve(
        [
            _message(1, MessageRole.USER, "Lên lịch Đà Nẵng 3 ngày"),
            _message(2, MessageRole.ASSISTANT, "Bạn muốn Đà Nẵng hay Hội An?"),
        ]
    )


def test_a_new_question_is_not_a_clarification_answer():
    """The user changing the subject is not answering the pending question.

    Treating every turn after an assistant question as an answer made the flag
    meaningless and kept a stale goal.
    """
    result = UNDERSTANDING.understand("Thời tiết Hà Nội thế nào?", _state_with_an_open_question())

    assert result.answers_pending_clarification is False


def test_a_new_request_replaces_the_goal():
    """The active goal follows the conversation, not the first request forever."""
    result = UNDERSTANDING.understand("Thời tiết Hà Nội thế nào?", _state_with_an_open_question())

    assert result.current_goal == "Thời tiết Hà Nội thế nào?"
    assert result.current_goal != "Lên lịch Đà Nẵng 3 ngày"


def test_a_short_answer_is_still_a_clarification_answer():
    """The narrowing must not lose the case it exists for."""
    result = UNDERSTANDING.understand("Hội An", _state_with_an_open_question())

    assert result.answers_pending_clarification is True
    assert result.current_goal == "Lên lịch Đà Nẵng 3 ngày"


def test_a_long_message_after_a_question_is_not_treated_as_an_answer():
    """A paragraph is a new request, not a one-word answer to a question."""
    result = UNDERSTANDING.understand(
        "Tôi đang nghĩ đến việc đổi sang một thành phố khác cho chuyến đi này",
        _state_with_an_open_question(),
    )

    assert result.answers_pending_clarification is False


# ---------------------------------------------------------------------------
# Stage 3: Normal Query Memory Key Extraction & Precedence (Plan v0.16)
# ---------------------------------------------------------------------------


def test_ordinary_query_without_personalization_requests_no_memory_keys():
    """Fail closed: ordinary queries without personalization cues never request memory."""
    for message in [
        "Hà Nội có gì đẹp?",
        "Thời tiết Đà Nẵng thế nào?",
        "Lịch trình tham quan Hội An 1 ngày",
        "What is the capital of France?",
    ]:
        result = UNDERSTANDING.understand(message, EMPTY_STATE)
        assert result.requested_memory_keys == ()
        assert result.current_memory_override_keys == ()


def test_broad_personalization_query_requests_all_governed_registry_keys():
    """Broad personalization requests all 8 canonical registry-v2 keys."""
    from backend.memory.write_pipeline.registry import registry_keys

    expected = registry_keys()
    assert len(expected) == 8

    for message in [
        "Lên kế hoạch chuyến đi theo sở thích của tôi",
        "Gợi ý lịch trình du lịch Đà Nẵng theo gu của tôi",
        "Tư vấn chuyến đi phù hợp với tôi",
        "Plan a trip according to my preferences",
    ]:
        result = UNDERSTANDING.understand(message, EMPTY_STATE)
        assert result.requested_memory_keys == expected
        assert result.interaction_mode == InteractionMode.NORMAL_QUERY


def test_domain_specific_personalization_query_requests_exact_keys():
    """Domain-specific personalization maps to exact governed registry keys."""
    hotel_res = UNDERSTANDING.understand("Gợi ý khách sạn theo sở thích của tôi", EMPTY_STATE)
    assert hotel_res.requested_memory_keys == (
        "travel.preference.hotel_atmosphere",
        "travel.preference.accommodation_type",
        "travel.constraint.budget_level",
    )

    transport_res = UNDERSTANDING.understand("Phương tiện di chuyển phù hợp với tôi", EMPTY_STATE)
    assert transport_res.requested_memory_keys == ("travel.preference.transport_mode",)

    food_res = UNDERSTANDING.understand("Gợi ý quán ăn theo gu của tôi", EMPTY_STATE)
    assert food_res.requested_memory_keys == ("travel.preference.food_style",)


def test_current_memory_override_keys_extracted_from_dimension_values():
    """When a query mentions specific dimension values, extract into current_memory_override_keys."""
    res_luxury = UNDERSTANDING.understand(
        "Chuyến đi này tôi muốn nghỉ dưỡng sang trọng cao cấp (luxury), hãy gợi ý khách sạn cho tôi",
        EMPTY_STATE,
    )
    assert "travel.constraint.budget_level" in res_luxury.current_memory_override_keys
    assert "travel.preference.hotel_atmosphere" in res_luxury.requested_memory_keys

    res_quiet = UNDERSTANDING.understand(
        "Gợi ý khách sạn theo sở thích nhưng tôi thích nơi yên tĩnh",
        EMPTY_STATE,
    )
    assert "travel.preference.hotel_atmosphere" in res_quiet.current_memory_override_keys


def test_informational_queries_omit_memory_and_remain_rag_only():
    """Verify informational queries with 'cho tôi' or 'tôi muốn' do NOT request Memory."""
    from backend.orchestration.context_planner import ContextPlanner
    from backend.orchestration.turn_models import ContextMode

    planner = ContextPlanner(enforcement_enabled=True)
    queries = [
        "Cho tôi biết Đà Nẵng có những cây cầu nổi tiếng nào?",
        "Tôi muốn biết Cầu Rồng ở đâu",
        "Cho tôi biết thời tiết Đà Nẵng thế nào?",
    ]

    for q in queries:
        u = UNDERSTANDING.understand(q, EMPTY_STATE)
        assert u.requested_memory_keys == (), f"Query {q!r} should not request Memory keys"
        assert u.interaction_mode is InteractionMode.NORMAL_QUERY
        plan = planner.plan(u)
        assert plan.proposed is ContextMode.RAG_ONLY, f"Query {q!r} should propose RAG_ONLY, got {plan.proposed}"
        assert plan.effective is ContextMode.RAG_ONLY
