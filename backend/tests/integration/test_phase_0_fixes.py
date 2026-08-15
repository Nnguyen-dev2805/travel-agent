import sys
from pathlib import Path
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from backend.app.database import SessionLocal, Base, engine
from backend.app.models.memory import UserMemory, MemoryOutbox
from backend.memory.fact_memory import FactMemoryService
from sqlalchemy import delete

@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    # Clean test data
    db.execute(delete(UserMemory).where(UserMemory.memory_id.like("p0_%")))
    db.execute(delete(MemoryOutbox).where(MemoryOutbox.memory_id.like("p0_%")))
    db.commit()
    
    yield db
    
    db.execute(delete(UserMemory).where(UserMemory.memory_id.like("p0_%")))
    db.execute(delete(MemoryOutbox).where(MemoryOutbox.memory_id.like("p0_%")))
    db.commit()
    db.close()

def test_memory_type_isolation(db_session):
    """Test 1 & 2 & 3: memory_type filtering, min_score, and last_accessed_at update."""
    
    # Insert a Semantic Fact and an Episodic Summary into SQL
    mem_semantic = UserMemory(
        memory_id="p0_sem_1", user_id=999, memory_type="semantic_fact", 
        fact_type="preference", fact_key="food", content="Thích ăn phở", status="active"
    )
    mem_episodic = UserMemory(
        memory_id="p0_epi_1", user_id=999, memory_type="episodic_summary", 
        fact_type="summary", fact_key="sess_1", content="Đã nói về phở", status="active"
    )
    mem_low_score = UserMemory(
        memory_id="p0_low_1", user_id=999, memory_type="semantic_fact", 
        fact_type="preference", fact_key="drink", content="Uống trà đá", status="active"
    )
    db_session.add_all([mem_semantic, mem_episodic, mem_low_score])
    db_session.commit()
    
    assert mem_semantic.last_accessed_at is None

    # Mock VectorStore to return fake results
    mock_embedder = MagicMock()
    mock_vector_store = MagicMock()
    
    # We pretend the vector store returns the episodic memory (which shouldn't happen if filtered, but we mock search_similar directly)
    # Actually, retrieve_relevant_facts passes 'where' to search_similar. Let's assert the where clause.
    def fake_search_similar(query_embedding, top_k, where):
        # Assert isolation is passed
        assert where.get("memory_type") == "semantic_fact"
        assert where.get("user_id") == 999
        
        return [
            {"id": "p0_sem_1", "score": 0.8, "text": "Thích ăn phở", "metadata": {"status": "active", "fact_type": "preference"}},
            {"id": "p0_low_1", "score": 0.4, "text": "Uống trà đá", "metadata": {"status": "active", "fact_type": "preference"}},
        ]
        
    mock_vector_store.search_similar.side_effect = fake_search_similar
    
    service = FactMemoryService(llm_client=None, embedder=mock_embedder, vector_store=mock_vector_store)
    
    results_text = service.retrieve_relevant_facts(db=db_session, user_id=999, query="Ăn phở không?")
    
    # Test 2: min_score filtering
    assert "Thích ăn phở" in results_text
    assert "Uống trà đá" not in results_text
    
    db_session.refresh(mem_semantic)
    db_session.refresh(mem_low_score)
    
    # Test 3: last_accessed_at update
    assert mem_semantic.last_accessed_at is not None
    assert mem_low_score.last_accessed_at is None

def test_conflict_audit_trail_saved(db_session):
    """Test 4: Conflict action and reasoning are saved to DB."""
    # Clean just in case
    db_session.execute(delete(UserMemory).where(UserMemory.user_id == 9999))
    db_session.commit()
    
    mem = UserMemory(
        memory_id="p0_conflict_1", user_id=9999, memory_type="semantic_fact", 
        fact_type="budget", fact_key="budget", content="Ngân sách 5 triệu", status="active"
    )
    db_session.add(mem)
    db_session.commit()
    
    # Mock LLM Client
    class DummyMessage:
        class Parsed:
            from backend.memory.enums import ConflictAction
            action = ConflictAction.UPDATE
            reasoning = "Cập nhật ngân sách mới nhất từ người dùng"
            merged_content = None
        parsed = Parsed()
    
    class DummyChoice:
        message = DummyMessage()
        
    class DummyCompletion:
        choices = [DummyChoice()]

    mock_client = MagicMock()
    json_resp = '{"facts": [{"fact_type": "budget", "fact_key": "budget", "content": "Ngân sách 10 triệu", "confidence": 0.9}]}'
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json_resp))]
    )
    mock_client.beta.chat.completions.parse.return_value = DummyCompletion()
    
    service = FactMemoryService(llm_client=mock_client, embedder=MagicMock(), vector_store=MagicMock())
    
    # Trigger extract facts which will detect conflict on 'budget' key
    service.extract_facts(db=db_session, user_id=9999, user_message="Tôi tăng ngân sách lên 10 triệu", assistant_reply="Vâng")
    
    db_session.refresh(mem)
    
    # Verify Audit Trail
    assert mem.content == "Ngân sách 10 triệu"
    assert mem.last_conflict_action == "update"
    assert mem.last_conflict_reasoning == "Cập nhật ngân sách mới nhất từ người dùng"
