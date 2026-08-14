"""Unit tests for Fact Extraction and Conflict Resolution LLM logic."""

import pytest
from unittest.mock import MagicMock, patch
from backend.memory.fact_memory import FactMemoryService
from backend.memory.enums import ConflictAction
import json


@pytest.fixture
def memory_service():
    """Returns an instance of FactMemoryService."""
    return FactMemoryService()


# ---------------------------------------------------------
# Tests for extract_facts_from_text
# ---------------------------------------------------------

@patch("backend.memory.fact_memory.OpenAI")
def test_extract_facts_success(mock_openai_class, memory_service):
    """Test successful extraction of facts from valid LLM JSON response."""
    # Setup mock LLM response
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_completion = MagicMock()
    
    mock_json = {
        "facts": [
            {
                "fact_type": "dietary",
                "fact_key": "food_allergy",
                "content": "Dị ứng hải sản",
                "confidence": 0.95
            }
        ]
    }
    mock_completion.choices[0].message.content = json.dumps(mock_json)
    mock_client.chat.completions.create.return_value = mock_completion
    
    # Inject mock client directly to avoid settings dependency
    memory_service._client = mock_client

    facts = memory_service.extract_facts_from_text(
        user_message="Tôi bị dị ứng hải sản nhé",
        assistant_reply="Vâng, tôi đã ghi nhận."
    )

    assert len(facts) == 1
    assert facts[0]["fact_key"] == "food_allergy"
    assert facts[0]["content"] == "Dị ứng hải sản"
    assert facts[0]["confidence"] == 0.95


@patch("backend.memory.fact_memory.OpenAI")
def test_extract_facts_empty(mock_openai_class, memory_service):
    """Test extraction when no new personal info is provided (empty facts array)."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_completion = MagicMock()
    
    mock_json = {"facts": []}
    mock_completion.choices[0].message.content = json.dumps(mock_json)
    mock_client.chat.completions.create.return_value = mock_completion
    
    memory_service._client = mock_client

    facts = memory_service.extract_facts_from_text(
        user_message="Hà Nội có chỗ nào đẹp?",
        assistant_reply="Hà Nội có Hồ Gươm..."
    )

    assert len(facts) == 0
    assert isinstance(facts, list)


@patch("backend.memory.fact_memory.OpenAI")
def test_extract_facts_invalid_json(mock_openai_class, memory_service):
    """Test extraction handles LLM returning malformed/invalid JSON gracefully."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_completion = MagicMock()
    
    # Not a JSON string
    mock_completion.choices[0].message.content = "Xin lỗi, tôi không thể trích xuất."
    mock_client.chat.completions.create.return_value = mock_completion
    
    memory_service._client = mock_client

    facts = memory_service.extract_facts_from_text(
        user_message="Tôi thích ăn mặn",
        assistant_reply="Ok"
    )

    assert len(facts) == 0


@patch("backend.memory.fact_memory.OpenAI")
def test_extract_facts_validation_error(mock_openai_class, memory_service):
    """Test extraction handles missing required keys (Pydantic validation error) and skips invalid items."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_completion = MagicMock()
    
    mock_json = {
        "facts": [
            {
                "fact_type": "dietary",
                # "fact_key" is intentionally missing to cause ValidationError
                "content": "Thiếu key",
                "confidence": 0.9
            },
            {
                "fact_type": "preference",
                "fact_key": "valid_fact",
                "content": "Valid content",
                "confidence": 0.8
            }
        ]
    }
    mock_completion.choices[0].message.content = json.dumps(mock_json)
    mock_client.chat.completions.create.return_value = mock_completion
    
    memory_service._client = mock_client

    facts = memory_service.extract_facts_from_text(
        user_message="Test validation",
        assistant_reply="Ok"
    )

    # Should only return the 1 valid fact
    assert len(facts) == 1
    assert facts[0]["fact_key"] == "valid_fact"


# ---------------------------------------------------------
# Tests for resolve_conflict
# ---------------------------------------------------------

@patch("backend.memory.fact_memory.OpenAI")
def test_resolve_conflict_skip(mock_openai_class, memory_service):
    """Test resolve_conflict parses SKIP correctly."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_completion = MagicMock()
    
    mock_completion.choices[0].message.content = "SKIP"
    mock_client.chat.completions.create.return_value = mock_completion
    memory_service._client = mock_client

    action = memory_service.resolve_conflict("Thích bún bò", "Tôi rất thích bún bò")
    assert action == ConflictAction.SKIP


@patch("backend.memory.fact_memory.OpenAI")
def test_resolve_conflict_update(mock_openai_class, memory_service):
    """Test resolve_conflict parses UPDATE correctly."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_completion = MagicMock()
    
    mock_completion.choices[0].message.content = "UPDATE"
    mock_client.chat.completions.create.return_value = mock_completion
    memory_service._client = mock_client

    action = memory_service.resolve_conflict("Ngân sách 5 triệu", "Ngân sách 10 triệu")
    assert action == ConflictAction.UPDATE


@patch("backend.memory.fact_memory.OpenAI")
def test_resolve_conflict_merge(mock_openai_class, memory_service):
    """Test resolve_conflict parses MERGE correctly."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_completion = MagicMock()
    
    mock_completion.choices[0].message.content = "MERGE"
    mock_client.chat.completions.create.return_value = mock_completion
    memory_service._client = mock_client

    action = memory_service.resolve_conflict("Đi với vợ", "Đi cùng con nhỏ 5 tuổi")
    assert action == ConflictAction.MERGE


@patch("backend.memory.fact_memory.OpenAI")
def test_resolve_conflict_deprecate(mock_openai_class, memory_service):
    """Test resolve_conflict parses DEPRECATE correctly."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_completion = MagicMock()
    
    mock_completion.choices[0].message.content = "DEPRECATE"
    mock_client.chat.completions.create.return_value = mock_completion
    memory_service._client = mock_client

    action = memory_service.resolve_conflict("Ghét đi Đà Lạt", "Bây giờ tôi lại thích Đà Lạt")
    assert action == ConflictAction.DEPRECATE_AND_CREATE


@patch("backend.memory.fact_memory.OpenAI")
def test_resolve_conflict_fallback(mock_openai_class, memory_service):
    """Test resolve_conflict falls back to UPDATE on unknown output."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_completion = MagicMock()
    
    # Garbage output from LLM
    mock_completion.choices[0].message.content = "Tôi không hiểu rõ ý bạn."
    mock_client.chat.completions.create.return_value = mock_completion
    memory_service._client = mock_client

    action = memory_service.resolve_conflict("A", "B")
    # Default fallback is UPDATE
    assert action == ConflictAction.UPDATE
