"""Semantic interpretation of the current message against structural state.

Stage-1 responsibility split (`plan v0.7:431-435`, `spec:265-292`):
`DialogueStateResolver` assembles structure — which turns were delivered, in what
order — and this module reads meaning out of the current message **against** that
structure. Topic, referent, current goal, clarification need, and speech-act
recognition all live here, and none of them is pre-computed by the resolver.

Resolution is deterministic-first, following the approved order
(`spec:319-327`):

```text
deterministic safety checks          -> quoting, then negation
-> high-precision explicit rules     -> closed cue vocabularies, one pass
-> bounded structured model call     -> NOT ENABLED in Stage 1
-> closed-schema validation          -> the result type is the closed schema
-> deterministic escalation          -> ambiguity or clarification, never a guess
```

**No model call is made.** The optional bounded parser described by
`plan v0.7:468-472` is not enabled in Stage 1: enabling it would put a provider
call on every turn's hot path, and `UnderstandingReason.PARSER_FAILED_CLOSED`
exists so the failure mode is representable when that parser is added. Until
then nothing here can emit it.

Nothing in this module authorizes a durable mutation, selects SQL or a storage
operation, or widens the context plan. Understanding proposes; `ExplicitIntentGate`
authorizes (`ADR 0036:34-41`).
"""

from __future__ import annotations

from backend.orchestration.dialogue_state import DialogueState
from backend.orchestration.turn_models import (
    InteractionMode,
    TurnUnderstandingResult,
    UnderstandingReason,
)

#: Token separators stripped from the edges of a word. Vietnamese and English
#: cues are space-delimited, so token-sequence matching is enough and avoids a
#: substring rule such as `nhớ` matching inside an unrelated word.
_EDGE_PUNCTUATION = ".,!?;:\"'()[]{}…—–-"

#: Openers paired with the closer that ends their span.
_QUOTE_PAIRS = {'"': '"', "'": "'", "“": "”", "«": "»"}

#: Speech acts that would propose a durable Memory mutation. Two different
#: families in one message is a conflict, not a preference.
#:
#: The remember cues are **declarative or imperative forms**, not the bare verb
#: `nhớ`. A bare verb also appears in questions — `bạn có nhớ tôi không?` — and
#: treating an interrogative as a command would authorize a durable write from a
#: question, which is the precision failure this layer exists to prevent
#: (`spec:389-391`).
_REMEMBER_CUES = ("nhớ là", "nhớ rằng", "ghi nhớ", "lưu lại", "remember", "note that")
_CORRECT_CUES = ("sửa lại", "đính chính", "không phải", "chứ không phải", "actually", "i meant")
_FORGET_CUES = ("quên", "xóa", "xoá", "forget", "delete")

#: Cues that negate the speech act itself — `đừng nhớ` is not a remember.
#: `không phải` is deliberately absent: in `sửa lại … không phải X mà là Y` it
#: marks a correction, and treating it as negation would misread a correction.
_NEGATION_CUES = ("đừng", "chớ", "không cần", "don't", "do not", "never")

#: Inspect is a question about Memory. These cues are matched before the durable
#: families because they are more specific: `bạn nhớ gì` contains a memory verb,
#: so a durable-first order would read the question as a command.
_INSPECT_CUES = (
    "bạn nhớ gì",
    "bạn có nhớ",
    "nhớ gì",
    "xem ký ức",
    "xem ghi nhớ",
    "what do you remember",
    "do you remember",
    "inspect memory",
)

#: Context-dependent cues. These carry no meaning on their own; they name a
#: dependency on what was already said, which is what makes them the proof that
#: interpretation lives here rather than in the resolver.
_CONTINUATION_CUES = ("tiếp tục đi", "tiếp tục", "tiếp đi", "continue", "go on")
_FIRST_REFERENT_CUES = ("cái đầu tiên", "cái thứ nhất", "the first one")
_OVERRIDE_CUES = ("giữ cái đó", "giữ lại cái đó", "keep that")

#: The dimension a change request names, used to record an override.
_CHANGE_CUES = ("đổi", "thay", "change")


def _tokens(message: str) -> list[str]:
    """Lowercased word tokens with edge punctuation removed."""
    tokens = []
    for raw in message.lower().split():
        token = raw.strip(_EDGE_PUNCTUATION)
        if token:
            tokens.append(token)
    return tokens


def _cue_index(tokens: list[str], cue: str) -> int:
    """Index where `cue`'s token sequence starts, or -1.

    Whole-token matching, not substring matching: `nhớ` must not match inside a
    longer word, and a multi-word cue must be contiguous.
    """
    cue_tokens = cue.split()
    span = len(cue_tokens)
    for start in range(len(tokens) - span + 1):
        if tokens[start : start + span] == cue_tokens:
            return start
    return -1


def _first_cue(tokens: list[str], cues: tuple[str, ...]) -> int:
    """Index of the earliest matching cue, or -1."""
    found = [_cue_index(tokens, cue) for cue in cues]
    present = [index for index in found if index >= 0]
    return min(present) if present else -1


#: Frames that make a message a **question or a definition request** rather than
#: a speech act. A memory verb inside one of these is a mention of the word, not
#: the user issuing a command: `Should I remember to bring a passport?` and
#: `xóa nghĩa là gì?` must never authorize anything. The question mark is
#: checked as a character as well, because a question does not always carry one
#: of these phrases.
_INTERROGATIVE_MARKERS = (
    "should i",
    "can you",
    "could you",
    "do you",
    "did you",
    "would you",
    "what",
    "why",
    "how",
    "when",
    "who",
    "which",
    "is there",
    "are there",
    "tại sao",
    "vì sao",
    "thế nào",
    "làm sao",
    "làm thế nào",
    "nghĩa là",
    "là gì",
    "có nên",
    "khi nào",
    "bao giờ",
    "ở đâu",
)


def _is_question(message: str, tokens: list[str]) -> bool:
    """Whether the message asks something rather than issuing a speech act.

    Over-matching is the safe direction: a real command that reads like a
    question is refused rather than authorized, and refusing proposes no
    mutation.
    """
    if "?" in message:
        return True
    return _first_cue(tokens, _INTERROGATIVE_MARKERS) >= 0


def _without_quoted_spans(message: str) -> str:
    """The message with every quoted span removed.

    Used for the quoting check: if a cue appears in the message but not in the
    text outside its quotes, the only speech act present was quoted, and a
    quotation is not something the user said.

    An **unterminated** opener is treated as quoting everything after it. The
    alternative — ignoring an unpaired quote and scanning the rest as the user's
    own words — fails open: `"nhớ là tôi thích cà phê` would authorize a durable
    write from text the user may have been quoting.
    """
    kept: list[str] = []
    index = 0
    while index < len(message):
        char = message[index]
        closer = _QUOTE_PAIRS.get(char)
        if closer is not None:
            end = message.find(closer, index + 1)
            if end == -1:
                break
            index = end + 1
            continue
        kept.append(char)
        index += 1
    return "".join(kept)


def _has_any_cue(message: str) -> bool:
    tokens = _tokens(message)
    families = (
        _REMEMBER_CUES,
        _CORRECT_CUES,
        _FORGET_CUES,
        _NEGATION_CUES,
        _INSPECT_CUES,
        _CONTINUATION_CUES,
        _FIRST_REFERENT_CUES,
        _OVERRIDE_CUES,
    )
    return any(_first_cue(tokens, family) >= 0 for family in families)


def _tail_after(tokens: list[str], index: int, span: int) -> str:
    """The text following a matched cue, used to record what was asserted."""
    return " ".join(tokens[index + span :]).strip()


class TurnUnderstanding:
    """Read the current message against one conversation's structural state."""

    def understand(self, message: str, state: DialogueState) -> TurnUnderstandingResult:
        """Return the governed reading of `message` given `state`.

        Deterministic and side-effect free. Ambiguity is an outcome, not a
        failure: a message that cannot be resolved by a closed rule escalates to
        `AMBIGUOUS` or to `needs_clarification` rather than being guessed into an
        action (`spec:319-327`).
        """
        # Quoted text is not the user's own words, so it is removed before any
        # rule reads the message. A cue that survives only inside quotes is not a
        # speech act at all; a cue quoted alongside a real one must not count
        # toward the conflict check either.
        unquoted = _without_quoted_spans(message)

        # 1. Safety check: a cue that only appears inside a quotation is not the
        #    user's own speech act, so it can never authorize anything.
        if _has_any_cue(message) and not _has_any_cue(unquoted):
            return TurnUnderstandingResult(
                interaction_mode=InteractionMode.NORMAL_QUERY,
                reason_codes=(UnderstandingReason.QUOTED_SPEECH_ACT,),
            )

        tokens = _tokens(unquoted)

        # 2. Inspect runs before the durable families on purpose. Its cues are
        #    more specific — `bạn nhớ gì` is a question about Memory, but it also
        #    contains the bare remember cue `nhớ`, so a durable-first order would
        #    classify the question as a remember command and propose a write.
        #    Recognized now, delivered in Stage 3 (`spec:397-401`).
        if _first_cue(tokens, _INSPECT_CUES) >= 0:
            return TurnUnderstandingResult(
                interaction_mode=InteractionMode.EXPLICIT_INSPECT,
                reason_codes=(
                    UnderstandingReason.DETERMINISTIC_MATCH,
                    UnderstandingReason.INSPECT_CAPABILITY_UNAVAILABLE,
                ),
            )

        # 3. A cue inside a question or a definition request is a mention of the
        #    word, not the user issuing a command. This runs after inspect — a
        #    memory question is exactly what inspect is for — and before the
        #    durable families, because a command must never be inferred from a
        #    cue word's presence alone.
        #
        #    The reason is only reported when a durable cue was actually present:
        #    an ordinary question with no memory cue has nothing to explain and
        #    stays `NO_EXPLICIT_SIGNAL`.
        durable_cue_present = any(
            _first_cue(tokens, cues) >= 0
            for cues in (_REMEMBER_CUES, _CORRECT_CUES, _FORGET_CUES)
        )
        if durable_cue_present and _is_question(message, tokens):
            return TurnUnderstandingResult(
                interaction_mode=InteractionMode.NORMAL_QUERY,
                reason_codes=(UnderstandingReason.MENTION_NOT_SPEECH_ACT,),
            )

        # 4. High-precision explicit rules, one pass over the closed vocabularies.
        durable: list[tuple[InteractionMode, int, str]] = []
        for mode, cues in (
            (InteractionMode.EXPLICIT_REMEMBER, _REMEMBER_CUES),
            (InteractionMode.EXPLICIT_CORRECT, _CORRECT_CUES),
            (InteractionMode.EXPLICIT_FORGET, _FORGET_CUES),
        ):
            index = _first_cue(tokens, cues)
            if index >= 0:
                matched = next(cue for cue in cues if _cue_index(tokens, cue) == index)
                durable.append((mode, index, matched))

        if len(durable) > 1:
            return TurnUnderstandingResult(
                interaction_mode=InteractionMode.AMBIGUOUS,
                needs_clarification=True,
                reason_codes=(UnderstandingReason.AMBIGUOUS_SPEECH_ACT,),
            )

        if durable:
            mode, index, matched = durable[0]
            if _first_cue(tokens, _NEGATION_CUES) >= 0:
                return TurnUnderstandingResult(
                    interaction_mode=InteractionMode.AMBIGUOUS,
                    needs_clarification=True,
                    reason_codes=(UnderstandingReason.NEGATED_SPEECH_ACT,),
                )
            assertion = _tail_after(tokens, index, len(matched.split()))
            return TurnUnderstandingResult(
                interaction_mode=mode,
                current_assertions=(assertion,) if assertion else (),
                reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
            )

        # 5. Context-dependent cues: meaningless without something to point at,
        #    which is why the resolver cannot own them.
        if (
            _first_cue(tokens, _CONTINUATION_CUES) >= 0
            or _first_cue(tokens, _FIRST_REFERENT_CUES) >= 0
            or _first_cue(tokens, _OVERRIDE_CUES) >= 0
        ):
            return self._resolve_against_state(tokens, state)

        # 6. A reply to a question the assistant asked is context-dependent even
        #    when it contains no cue phrase at all. Deriving the pending question
        #    from the structural state is what makes clarification and goal
        #    semantics general rather than three hard-coded phrases.
        if state.latest_assistant_turn is not None and _is_question(
            state.latest_assistant_turn.content,
            _tokens(state.latest_assistant_turn.content),
        ):
            return self._resolve_against_state(tokens, state)

        # 7. Deterministic escalation: an ordinary query claims nothing.
        return TurnUnderstandingResult(
            interaction_mode=InteractionMode.NORMAL_QUERY,
            reason_codes=(UnderstandingReason.NO_EXPLICIT_SIGNAL,),
        )

    def _resolve_against_state(
        self, tokens: list[str], state: DialogueState
    ) -> TurnUnderstandingResult:
        """Resolve a context-dependent cue against the delivered turns.

        With nothing delivered yet the cue has no referent, so the reading is a
        controlled clarification rather than an invented one. Once an exchange
        exists, the cue resolves against it: the prior user turn supplies the
        topic, the prior answer supplies the referent, and a change request
        records the dimension it changes.
        """
        prior_user = state.latest_user_turn
        prior_answer = state.latest_assistant_turn

        if prior_answer is None or prior_user is None:
            return TurnUnderstandingResult(
                interaction_mode=InteractionMode.AMBIGUOUS,
                needs_clarification=True,
                reason_codes=(UnderstandingReason.CONTEXT_MISSING,),
            )

        topics = (prior_user.content,)
        entities: tuple[str, ...] = ()
        overrides: tuple[str, ...] = ()
        temporal_context: str | None = None

        if _first_cue(tokens, _FIRST_REFERENT_CUES) >= 0:
            # The first enumerated item of the previous answer is what "the first
            # one" points at.
            first_item = prior_answer.content.split(".")[0].strip()
            entities = (first_item,) if first_item else ()

        if _first_cue(tokens, _OVERRIDE_CUES) >= 0:
            change_index = _first_cue(tokens, _CHANGE_CUES)
            dimension = (
                tokens[change_index + 1]
                if 0 <= change_index < len(tokens) - 1
                else ""
            )
            if dimension:
                overrides = (dimension,)
                temporal_context = dimension

        # A question left open by the assistant is the pending clarification this
        # message may be answering, and the last user turn is the active goal of
        # the conversation. Both are read out of structure; neither is a field the
        # resolver owns.
        answers_pending_clarification = _is_question(
            prior_answer.content, _tokens(prior_answer.content)
        )

        return TurnUnderstandingResult(
            interaction_mode=InteractionMode.NORMAL_QUERY,
            topics=topics,
            entities=entities,
            current_overrides=overrides,
            temporal_context=temporal_context,
            current_goal=prior_user.content,
            answers_pending_clarification=answers_pending_clarification,
            reason_codes=(UnderstandingReason.CONTEXT_REQUIRED,),
        )
