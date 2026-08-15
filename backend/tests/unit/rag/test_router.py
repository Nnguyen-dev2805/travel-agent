# pyrefly: ignore [missing-import]
import pytest
from unittest.mock import MagicMock, patch

from backend.rag.routing.router import ContextRouter, RouteType, RouteDecision

def test_greeting_fast_path():
    router = ContextRouter(llm_client=MagicMock())
    decision = router.determine_route("Xin chào bạn")
    assert decision.route == RouteType.DIRECT_ANSWER
    assert decision.needs_rag is False
    assert decision.confidence == 1.0

def test_greeting_llm_fallback():
    router = ContextRouter(llm_client=MagicMock())
    # Mock LLM to avoid real API calls
    mock_llm = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"route": "direct_answer", "needs_rag": false, "needs_memory_read": false, "should_write_memory": false, "confidence": 0.9, "rewritten_query": "hế lô", "reason": "greeting"}'
    mock_llm.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    router.client = mock_llm

    decision = router.determine_route("Hế lô bạn ơi") # Misses regex fast path
    assert decision.route == RouteType.DIRECT_ANSWER

def test_memory_write_fast_path():
    router = ContextRouter(llm_client=MagicMock())
    decision = router.determine_route("Tôi bị dị ứng hải sản nhé")
    assert decision.route == RouteType.MEMORY_WRITE
    assert decision.should_write_memory is True

def test_rag_only_route():
    router = ContextRouter(llm_client=MagicMock())
    mock_llm = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"route": "rag_only", "needs_rag": true, "needs_memory_read": false, "should_write_memory": false, "confidence": 0.95, "rewritten_query": "địa điểm du lịch Đà Lạt", "reason": "asking for travel info"}'
    mock_llm.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    router.client = mock_llm

    decision = router.determine_route("Đà Lạt có gì chơi?")
    assert decision.route == RouteType.RAG_ONLY
    assert decision.needs_rag is True

def test_json_error_fallback():
    router = ContextRouter(llm_client=MagicMock())
    mock_llm = MagicMock()
    mock_choice = MagicMock()
    # Return invalid JSON
    mock_choice.message.content = 'I think it should be direct answer'
    mock_llm.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    router.client = mock_llm

    decision = router.determine_route("Lịch trình Đà Nẵng")
    # Should fallback to rag_and_memory
    assert decision.route == RouteType.RAG_AND_MEMORY
    assert decision.needs_rag is True
    assert decision.confidence == 0.0

def test_vague_query_clarify():
    router = ContextRouter(llm_client=MagicMock())
    mock_llm = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"route": "clarify", "needs_rag": false, "needs_memory_read": false, "should_write_memory": false, "confidence": 0.85, "rewritten_query": "", "reason": "Too vague"}'
    mock_llm.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    router.client = mock_llm

    decision = router.determine_route("Chỗ nào nữa?")
    assert decision.route == RouteType.CLARIFY
