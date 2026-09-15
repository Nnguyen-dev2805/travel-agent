"""Unit tests for ConversationOrchestrator Stage-3 integration.

Tests context planning, context arbiter integration, explicit inspect delivery,
and memory read/use flag gating.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from backend.generation.contracts import (
    ContextSufficiency,
    GenerationContext,
    GenerationResult,
)
from backend.memory.read_models import MemorySelection, SelectedMemory
from backend.memory.write_pipeline.models import Authority, MemoryScope
from backend.orchestration.context_arbiter import ContextArbiter
from backend.orchestration.context_planner import ContextPlanner
from backend.orchestration.conversation_orchestrator import (
    INSPECT_UNAVAILABLE_MODEL,
    INSPECT_UNAVAILABLE_REPLY,
    ConversationOrchestrator,
)
from backend.orchestration.turn_models import (
    ContextMode,
    ContextPlan,
    TurnDisposition,
    TurnUnderstandingResult,
)
from backend.rag.contracts import CitationEvidence, ContextBundle
from backend.tests.unit.test_conversation_orchestrator import (
    CONVERSATION,
    OWNER,
    FakeConversationService,
    _real_principal,
)
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FakeRAGService:
    def __init__(self) -> None:
        self.generate_answer_called = False
        self.generate_from_context_called = False
        self.last_context: Optional[GenerationContext] = None

    def generate_answer(self, message: str, top_k: int = 4) -> Dict[str, Any]:
        self.generate_answer_called = True
        return {
            "reply": "Legacy RAG reply",
            "model": "legacy-rag-model",
            "citations": [{"title": "Da Nang", "url": "https://vietnam.travel/da-nang"}],
        }

    def build_travel_context(self, message: str, top_k: int = 4) -> ContextBundle:
        return ContextBundle(
            prompt_context="Cẩm nang du lịch Đà Nẵng: bãi biển Mỹ Khê, Ngũ Hành Sơn.",
            evidence=(),
            citations=(
                CitationEvidence(
                    title="Đà Nẵng",
                    url="https://vietnam.travel/da-nang",
                    evidence_ids=("ev_1",),
                ),
            ),
            insufficient_evidence=False,
        )

    def generate_from_context(self, user_message: str, context: GenerationContext) -> GenerationResult:
        self.generate_from_context_called = True
        self.last_context = context
        return GenerationResult(
            reply=f"Generated answer with context sufficiency={context.sufficiency.value}",
            model="gpt-4o-mini",
            citations=context.citations,
        )


def test_explicit_inspect_when_read_disabled():
    """When MEMORY_READ_ENABLED=False, explicit inspect returns unavailable reply and INCOMPLETE."""
    conv_svc = FakeConversationService([])
    rag_svc = FakeRAGService()

    orchestrator = ConversationOrchestrator(
        rag_service=rag_svc,
        conversation_service_provider=lambda: conv_svc,
        memory_read_enabled=False,
    )

    outcome = orchestrator.handle_turn(
        message="Bạn nhớ gì về tôi?",
        conversation_id=CONVERSATION,
        principal=_real_principal(),
    )

    assert outcome.reply == INSPECT_UNAVAILABLE_REPLY
    assert outcome.model == INSPECT_UNAVAILABLE_MODEL
    assert outcome.citations == []
    assert outcome.disposition is TurnDisposition.INCOMPLETE


def test_explicit_inspect_when_read_enabled_and_empty():
    """When MEMORY_READ_ENABLED=True and selection is empty, returns empty message and ANSWERED."""
    conv_svc = FakeConversationService([])
    rag_svc = FakeRAGService()

    mock_read_engine = MagicMock()
    mock_read_engine.select.return_value = MemorySelection(
        selected=(),
        abstention_reason=None,
    )

    orchestrator = ConversationOrchestrator(
        rag_service=rag_svc,
        conversation_service_provider=lambda: conv_svc,
        memory_read_enabled=True,
        memory_read_engine=mock_read_engine,
    )

    outcome = orchestrator.handle_turn(
        message="Bạn nhớ gì về tôi?",
        conversation_id=CONVERSATION,
        principal=_real_principal(),
    )

    assert outcome.reply == "Hiện tại tôi chưa ghi nhớ thông tin nào về sở thích của bạn."
    assert outcome.model == "system"
    assert outcome.citations == []
    assert outcome.disposition is TurnDisposition.ANSWERED
    assert mock_read_engine.select.called


def test_explicit_inspect_when_read_enabled_and_has_memories():
    """When memories exist, explicit inspect formats safe fields with human-readable scope."""
    conv_svc = FakeConversationService([])
    rag_svc = FakeRAGService()

    now = utc_now()
    item_user = SelectedMemory(
        version_id="ver_1",
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        scope=MemoryScope.USER,
        scope_id=OWNER,
        authority=Authority.EXPLICIT_SAVE,
        valid_from=now,
    )
    item_conv = SelectedMemory(
        version_id="ver_2",
        canonical_key="travel.preference.dietary_restrictions",
        normalized_value=("vegetarian", "halal"),
        scope=MemoryScope.CONVERSATION,
        scope_id=CONVERSATION,
        authority=Authority.EXPLICIT_SAVE,
        valid_from=now,
    )

    mock_read_engine = MagicMock()
    mock_read_engine.select.return_value = MemorySelection(
        selected=(item_user, item_conv),
        abstention_reason=None,
    )

    orchestrator = ConversationOrchestrator(
        rag_service=rag_svc,
        conversation_service_provider=lambda: conv_svc,
        memory_read_enabled=True,
        memory_read_engine=mock_read_engine,
    )

    outcome = orchestrator.handle_turn(
        message="Bạn nhớ gì về tôi?",
        conversation_id=CONVERSATION,
        principal=_real_principal(),
    )

    assert "Dưới đây là các sở thích mà tôi đã ghi nhớ:" in outcome.reply
    assert "- travel.preference.hotel_atmosphere: quiet (chung cho tài khoản của bạn)" in outcome.reply
    assert "- travel.preference.dietary_restrictions: vegetarian, halal (trong đoạn hội thoại này)" in outcome.reply
    assert outcome.disposition is TurnDisposition.ANSWERED


def test_normal_query_with_enforcement_disabled_runs_legacy_rag():
    """When enforcement_enabled=False, orchestrator calls legacy generate_answer."""
    conv_svc = FakeConversationService([])
    rag_svc = FakeRAGService()

    planner = ContextPlanner(enforcement_enabled=False)
    orchestrator = ConversationOrchestrator(
        rag_service=rag_svc,
        conversation_service_provider=lambda: conv_svc,
        context_planner=planner,
    )

    outcome = orchestrator.handle_turn(
        message="Thời tiết Đà Nẵng mùa này thế nào?",
        conversation_id=CONVERSATION,
        principal=_real_principal(),
    )

    assert rag_svc.generate_answer_called is True
    assert rag_svc.generate_from_context_called is False
    assert outcome.reply == "Legacy RAG reply"


def test_normal_query_with_enforcement_enabled_and_mode_rag_only():
    """When enforcement_enabled=True and mode is RAG_ONLY, arbitrates and calls generate_from_context."""
    conv_svc = FakeConversationService([])
    rag_svc = FakeRAGService()

    class ForcedRAGOnlyPlanner(ContextPlanner):
        def __init__(self) -> None:
            super().__init__(enforcement_enabled=True)

        def plan(self, understanding: TurnUnderstandingResult) -> ContextPlan:
            return ContextPlan(proposed=ContextMode.RAG_ONLY, effective=ContextMode.RAG_ONLY)

    orchestrator = ConversationOrchestrator(
        rag_service=rag_svc,
        conversation_service_provider=lambda: conv_svc,
        context_planner=ForcedRAGOnlyPlanner(),
        context_arbiter=ContextArbiter(),
    )

    outcome = orchestrator.handle_turn(
        message="Đà Nẵng có gì chơi?",
        conversation_id=CONVERSATION,
        principal=_real_principal(),
    )

    assert rag_svc.generate_from_context_called is True
    assert rag_svc.last_context is not None
    assert rag_svc.last_context.sufficiency is ContextSufficiency.SUFFICIENT
    assert len(rag_svc.last_context.citations) == 1
    assert rag_svc.last_context.citations[0].title == "Đà Nẵng"
    assert "CẨM NANG DU LỊCH THAM KHẢO" in rag_svc.last_context.prompt_context


def test_normal_query_with_enforcement_enabled_and_mode_none():
    """When enforcement_enabled=True and mode is NONE, arbitrates to NOT_REQUIRED and empty citations."""
    conv_svc = FakeConversationService([])
    rag_svc = FakeRAGService()

    class ForcedNonePlanner(ContextPlanner):
        def __init__(self) -> None:
            super().__init__(enforcement_enabled=True)

        def plan(self, understanding: TurnUnderstandingResult) -> ContextPlan:
            return ContextPlan(proposed=ContextMode.NONE, effective=ContextMode.NONE)

    orchestrator = ConversationOrchestrator(
        rag_service=rag_svc,
        conversation_service_provider=lambda: conv_svc,
        context_planner=ForcedNonePlanner(),
        context_arbiter=ContextArbiter(),
    )

    outcome = orchestrator.handle_turn(
        message="Xin chào bạn nhé",
        conversation_id=CONVERSATION,
        principal=_real_principal(),
    )

    assert rag_svc.generate_from_context_called is True
    assert rag_svc.last_context is not None
    assert rag_svc.last_context.sufficiency is ContextSufficiency.NOT_REQUIRED
    assert rag_svc.last_context.citations == ()
    assert rag_svc.last_context.prompt_context == ""


def test_normal_query_with_enforcement_enabled_and_mode_memory_only():
    """When enforcement_enabled=True and mode is MEMORY_ONLY, arbitrates structured memory and 0 travel citations."""
    conv_svc = FakeConversationService([])
    rag_svc = FakeRAGService()

    now = utc_now()
    item = SelectedMemory(
        version_id="ver_1",
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        scope=MemoryScope.USER,
        scope_id=OWNER,
        authority=Authority.EXPLICIT_SAVE,
        valid_from=now,
    )
    mock_read_engine = MagicMock()
    mock_read_engine.select.return_value = MemorySelection(
        selected=(item,),
        abstention_reason=None,
    )

    class ForcedMemoryOnlyPlanner(ContextPlanner):
        def __init__(self) -> None:
            super().__init__(enforcement_enabled=True)

        def plan(self, understanding: TurnUnderstandingResult) -> ContextPlan:
            return ContextPlan(
                proposed=ContextMode.MEMORY_ONLY,
                effective=ContextMode.MEMORY_ONLY,
                requested_memory_keys=understanding.requested_memory_keys,
            )

    orchestrator = ConversationOrchestrator(
        rag_service=rag_svc,
        conversation_service_provider=lambda: conv_svc,
        context_planner=ForcedMemoryOnlyPlanner(),
        context_arbiter=ContextArbiter(),
        memory_read_enabled=True,
        memory_use_enabled=True,
        memory_read_engine=mock_read_engine,
    )

    outcome = orchestrator.handle_turn(
        message="Tôi muốn tìm khách sạn phù hợp với tôi",
        conversation_id=CONVERSATION,
        principal=_real_principal(),
    )

    assert rag_svc.generate_from_context_called is True
    assert rag_svc.last_context is not None
    assert rag_svc.last_context.sufficiency is ContextSufficiency.SUFFICIENT
    assert rag_svc.last_context.citations == ()
    assert "travel.preference.hotel_atmosphere" in rag_svc.last_context.prompt_context
    assert "quiet" in rag_svc.last_context.prompt_context


def test_normal_query_with_enforcement_enabled_and_mode_both():
    """When mode is BOTH, arbitrates both bounded RAG and structured memory."""
    conv_svc = FakeConversationService([])
    rag_svc = FakeRAGService()

    now = utc_now()
    item = SelectedMemory(
        version_id="ver_1",
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        scope=MemoryScope.USER,
        scope_id=OWNER,
        authority=Authority.EXPLICIT_SAVE,
        valid_from=now,
    )
    mock_read_engine = MagicMock()
    mock_read_engine.select.return_value = MemorySelection(
        selected=(item,),
        abstention_reason=None,
    )

    class ForcedBothPlanner(ContextPlanner):
        def __init__(self) -> None:
            super().__init__(enforcement_enabled=True)

        def plan(self, understanding: TurnUnderstandingResult) -> ContextPlan:
            return ContextPlan(
                proposed=ContextMode.BOTH,
                effective=ContextMode.BOTH,
                requested_memory_keys=understanding.requested_memory_keys,
            )

    orchestrator = ConversationOrchestrator(
        rag_service=rag_svc,
        conversation_service_provider=lambda: conv_svc,
        context_planner=ForcedBothPlanner(),
        context_arbiter=ContextArbiter(),
        memory_read_enabled=True,
        memory_use_enabled=True,
        memory_read_engine=mock_read_engine,
    )

    outcome = orchestrator.handle_turn(
        message="Gợi ý khách sạn tại Đà Nẵng theo gu của tôi",
        conversation_id=CONVERSATION,
        principal=_real_principal(),
    )

    assert rag_svc.generate_from_context_called is True
    assert rag_svc.last_context is not None
    assert rag_svc.last_context.sufficiency is ContextSufficiency.SUFFICIENT
    assert len(rag_svc.last_context.citations) == 1
    assert rag_svc.last_context.citations[0].title == "Đà Nẵng"
    assert "CẨM NANG DU LỊCH THAM KHẢO" in rag_svc.last_context.prompt_context
    assert "travel.preference.hotel_atmosphere" in rag_svc.last_context.prompt_context


def test_memory_use_disabled_skips_memory_in_both_mode():
    """When memory_use_enabled=False, memory is not retrieved; BOTH mode yields INSUFFICIENT."""
    conv_svc = FakeConversationService([])
    rag_svc = FakeRAGService()

    mock_read_engine = MagicMock()

    class ForcedBothPlanner(ContextPlanner):
        def __init__(self) -> None:
            super().__init__(enforcement_enabled=True)

        def plan(self, understanding: TurnUnderstandingResult) -> ContextPlan:
            return ContextPlan(
                proposed=ContextMode.BOTH,
                effective=ContextMode.BOTH,
                requested_memory_keys=understanding.requested_memory_keys,
            )

    orchestrator = ConversationOrchestrator(
        rag_service=rag_svc,
        conversation_service_provider=lambda: conv_svc,
        context_planner=ForcedBothPlanner(),
        context_arbiter=ContextArbiter(),
        memory_read_enabled=True,
        memory_use_enabled=False,
        memory_read_engine=mock_read_engine,
    )

    outcome = orchestrator.handle_turn(
        message="Gợi ý khách sạn tại Đà Nẵng theo gu của tôi",
        conversation_id=CONVERSATION,
        principal=_real_principal(),
    )

    assert rag_svc.generate_from_context_called is True
    assert mock_read_engine.select.called is False
    # In BOTH mode, missing memory yields INSUFFICIENT without silent downgrade
    assert rag_svc.last_context.sufficiency is ContextSufficiency.INSUFFICIENT


def test_production_chain_without_forced_planner_routes_to_both():
    """Real TurnUnderstanding -> ContextPlanner chain naturally routes personalization query to BOTH."""
    conv_svc = FakeConversationService([])
    rag_svc = FakeRAGService()

    now = utc_now()
    item = SelectedMemory(
        version_id="ver_1",
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        scope=MemoryScope.USER,
        scope_id=OWNER,
        authority=Authority.EXPLICIT_SAVE,
        valid_from=now,
    )
    mock_read_engine = MagicMock()
    mock_read_engine.select.return_value = MemorySelection(
        selected=(item,),
        abstention_reason=None,
    )

    orchestrator = ConversationOrchestrator(
        rag_service=rag_svc,
        conversation_service_provider=lambda: conv_svc,
        context_planner=ContextPlanner(enforcement_enabled=True),
        context_arbiter=ContextArbiter(),
        memory_read_enabled=True,
        memory_use_enabled=True,
        memory_read_engine=mock_read_engine,
    )

    outcome = orchestrator.handle_turn(
        message="Gợi ý khách sạn theo gu của tôi",
        conversation_id=CONVERSATION,
        principal=_real_principal(),
    )

    assert rag_svc.generate_from_context_called is True
    assert mock_read_engine.select.called is True
    call_req = mock_read_engine.select.call_args[0][0]
    assert call_req.requested_keys == (
        "travel.preference.hotel_atmosphere",
        "travel.preference.accommodation_type",
        "travel.constraint.budget_level",
    )
    assert rag_svc.last_context.sufficiency is ContextSufficiency.SUFFICIENT
