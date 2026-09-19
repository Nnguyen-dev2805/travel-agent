"""Unit tests for MemoryContextComposer.

Governed by Plan v0.15, Spec v0.7, and ADR 0039:
- MemoryContextComposer emits only governed structured key/value/scope/influence data.
- Never injects raw source or evidence text.
- Formats structured preferences safely.
- Deterministic output.
- Empty selection returns empty string.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.memory.read_models import MemorySelection, SelectedMemory
from backend.memory.write_pipeline.models import Authority, MemoryScope


def _sample_memory(
    key: str = "travel.preference.hotel_atmosphere",
    value: str | tuple[str, ...] = "quiet",
    scope: MemoryScope = MemoryScope.USER,
) -> SelectedMemory:
    return SelectedMemory(
        version_id="ver-123",
        canonical_key=key,
        normalized_value=value,
        scope=scope,
        scope_id="user-1",
        authority=Authority.EXPLICIT_SAVE,
        valid_from=datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_empty_selection_composes_empty_string():
    from backend.memory.context import MemoryContextComposer

    composer = MemoryContextComposer()
    empty_sel = MemorySelection(selected=())
    assert composer.compose(empty_sel) == ""


def test_single_preference_composition():
    from backend.memory.context import MemoryContextComposer

    composer = MemoryContextComposer()
    mem = _sample_memory(
        key="travel.preference.hotel_atmosphere",
        value="quiet",
        scope=MemoryScope.USER,
    )
    sel = MemorySelection(selected=(mem,))
    output = composer.compose(sel)

    assert "travel.preference.hotel_atmosphere" in output
    assert "quiet" in output
    assert "soft_preference" in output
    assert "user" in output
    # Must not contain raw evidence artifacts
    assert "evidence_id" not in output
    assert "raw_text" not in output


def test_set_valued_preference_composition():
    from backend.memory.context import MemoryContextComposer

    composer = MemoryContextComposer()
    mem = _sample_memory(
        key="travel.preference.activity_style",
        value=("culture", "nature"),
        scope=MemoryScope.CONVERSATION,
    )
    sel = MemorySelection(selected=(mem,))
    output = composer.compose(sel)

    assert "travel.preference.activity_style" in output
    assert "culture" in output
    assert "nature" in output
    assert "conversation" in output


def test_composition_is_deterministic_and_structured_json():
    from backend.memory.context import MemoryContextComposer

    composer = MemoryContextComposer()
    mem1 = _sample_memory(
        key="travel.preference.hotel_atmosphere",
        value="quiet",
        scope=MemoryScope.USER,
    )
    mem2 = _sample_memory(
        key="travel.preference.budget_level",
        value="luxury",
        scope=MemoryScope.USER,
    )
    sel = MemorySelection(selected=(mem1, mem2))

    out1 = composer.compose(sel)
    out2 = composer.compose(sel)
    assert out1 == out2

    # Verify structured JSON is embedded and valid
    lines = out1.strip().split("\n")
    # Find JSON payload
    json_start = next(i for i, line in enumerate(lines) if line.strip().startswith("{"))
    json_str = "\n".join(lines[json_start:])
    parsed = json.loads(json_str)

    assert "preferences" in parsed
    prefs = parsed["preferences"]
    assert len(prefs) == 2
    assert prefs[0]["key"] == "travel.preference.hotel_atmosphere"
    assert prefs[0]["value"] == "quiet"
    assert prefs[0]["influence"] == "soft_preference"
    assert prefs[1]["key"] == "travel.preference.budget_level"
    assert prefs[1]["value"] == "luxury"
