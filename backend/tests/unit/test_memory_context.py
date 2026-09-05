"""Unit tests for R6 memory prompt section composition.

The composer turns selected memories into one controlled prompt section. It
never fabricates citations and never reaches beyond the selections it is
given, so travel citations and source messages cannot leak through it.

No test here touches a database, a model provider, Chroma, or the network.
"""

from backend.memory.models import (
    MemoryRecordScope,
    MemoryRecordType,
    MemorySelection,
    MemorySelectionReason,
    generate_memory_record_id,
)
from backend.orchestration.memory_context import compose_memory_section


def _selection(**overrides) -> MemorySelection:
    payload = {
        "memory_id": generate_memory_record_id(),
        "scope": MemoryRecordScope.USER,
        "memory_type": MemoryRecordType.PREFERENCE,
        "reason": MemorySelectionReason.LEXICAL_MATCH,
        "score": 1.0,
        "text": "Người dùng ăn chay trường.",
    }
    payload.update(overrides)
    return MemorySelection(**payload)


def test_empty_selection_composes_no_section():
    assert compose_memory_section(()) == ""


def test_single_selection_formatting_is_exact():
    assert compose_memory_section([_selection()]) == (
        "[Bộ nhớ liên quan]\n"
        "- Người dùng ăn chay trường. (loại: preference, phạm vi: user)"
    )


def test_multiple_selections_keep_rank_order():
    first = _selection()
    second = _selection(
        memory_id=generate_memory_record_id(),
        scope=MemoryRecordScope.WORKSPACE,
        memory_type=MemoryRecordType.CONSTRAINT,
        reason=MemorySelectionReason.ACTIVE_CORRECTION,
        score=0.5,
        text="Ngân sách tối đa 20 triệu.",
    )
    assert compose_memory_section([first, second]) == (
        "[Bộ nhớ liên quan]\n"
        "- Người dùng ăn chay trường. (loại: preference, phạm vi: user)\n"
        "- Ngân sách tối đa 20 triệu. (loại: constraint, phạm vi: workspace)"
    )


def test_section_carries_no_citations_or_sources():
    section = compose_memory_section([_selection()])
    assert "http" not in section
    assert "Nguồn" not in section
    assert "ms_" not in section
    assert "cv_" not in section
