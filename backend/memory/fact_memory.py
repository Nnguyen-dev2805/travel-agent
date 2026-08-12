"""Long-term Memory Service: Auto-extracts user facts and preferences bound to User ID."""

import json
import logging
from typing import Any, Dict, List, Optional
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from sqlalchemy import select
# pyrefly: ignore [missing-import]
from openai import OpenAI

from backend.app.config import settings
from backend.app.models.memory import UserMemory, MemoryOutbox
from backend.memory.enums import FactType, MemoryStatus, ConflictAction
from backend.rag.embedding.embedder import VectorEmbedder
from backend.rag.retrieval.vector_store import ChromaVectorStore

logger = logging.getLogger("travel_agent_fact_memory")


class FactMemoryService:
    """Manages long-term user facts and preference extraction."""

    def _get_llm_client(self) -> Optional[OpenAI]:
        """Get configured OpenAI client for LLM fact extraction."""
        if not settings.GOOGLE_API_KEY:
            logger.warning("API key missing; skipping LLM fact extraction.")
            return None
        try:
            return OpenAI(
                base_url=settings.LLM_BASE_URL,
                api_key=settings.GOOGLE_API_KEY,
            )
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client for Fact Extraction: {str(e)}")
            return None

    def extract_facts_from_text(
        self, user_message: str, assistant_reply: str
    ) -> List[Dict[str, Any]]:
        """Call LLM to extract structured facts from a conversation turn."""
        client = self._get_llm_client()
        if not client:
            return []

        extraction_prompt = (
            "Bạn là một AI Memory Extractor chuyên nghiệp cho ứng dụng du lịch Việt Nam.\n"
            "Hãy phân tích đoạn hội thoại mới nhất bên dưới giữa User và Assistant để trích xuất các THÔNG TIN CÁ NHÂN "
            "của User (sở thích ăn uống, phong cách du lịch, địa điểm đã từng đi, hạn chế chế độ ăn, ngân sách...).\n\n"
            "=== ĐOẠN HỘI THOẠI ===\n"
            f"User: {user_message}\n"
            f"Assistant: {assistant_reply}\n\n"
            "=== YÊU CẦU ĐẦU RA ===\n"
            "Trả về DUY NHẤT một JSON array chứa danh sách các fact được tìm thấy.\n"
            "Mỗi item trong array có dạng đúng JSON schema sau:\n"
            "[\n"
            "  {\n"
            '    "fact_type": "preference | identity | visited_place | budget | travel_style | dietary | behavior",\n'
            '    "fact_key": "Mã định danh tiếng Anh viết thường (VD: food_allergy, transport_mode)",\n'
            '    "content": "Mô tả chi tiết bằng Tiếng Việt (VD: Dị ứng nặng với hải sản)",\n'
            '    "confidence": 0.9\n'
            "  }\n"
            "]\n"
            "Nếu không có thông tin cá nhân mới nào được đề cập, trả về [] (JSON array rỗng). "
            "Chỉ trả về JSON hợp lệ, không kèm bất kỳ câu dẫn hay markdown fence nào khác."
        )

        try:
            completion = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0.1,
                max_tokens=500,
            )
            raw_text = completion.choices[0].message.content.strip()

            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            extracted_items = json.loads(raw_text)
            if isinstance(extracted_items, list):
                return extracted_items

        except Exception as e:
            logger.warning(f"Fact extraction parsing notice: {str(e)}")

        return []

    def resolve_conflict(self, old_content: str, new_content: str) -> ConflictAction:
        """Use LLM to determine the ConflictAction when fact_key collides."""
        client = self._get_llm_client()
        if not client:
            return ConflictAction.UPDATE  # Fallback

        prompt = (
            "Bạn là AI phân xử mâu thuẫn bộ nhớ (Memory Conflict Resolver).\n"
            "Người dùng vừa cung cấp một thông tin mới có cùng Chủ đề (fact_key) với thông tin cũ trong database.\n"
            "Nhiệm vụ của bạn là so sánh 2 thông tin và quyết định HÀNH ĐỘNG xử lý phù hợp nhất.\n\n"
            f"- Cũ: {old_content}\n"
            f"- Mới: {new_content}\n\n"
            "Chọn MỘT trong các hành động sau (chỉ trả về TÊN HÀNH ĐỘNG, không giải thích):\n"
            "SKIP: Thông tin mới giống hệt hoặc không mang thêm giá trị.\n"
            "UPDATE: Thông tin mới là bản cập nhật chi tiết hơn (VD: ngân sách tăng lên).\n"
            "MERGE: Hai thông tin bổ sung cho nhau, cần gộp lại.\n"
            "DEPRECATE: Thông tin mới mâu thuẫn hoàn toàn (đổi sở thích), cái cũ không còn đúng.\n"
        )
        try:
            completion = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=20,
            )
            action_str = completion.choices[0].message.content.strip().upper()

            if "SKIP" in action_str:
                return ConflictAction.SKIP
            if "UPDATE" in action_str:
                return ConflictAction.UPDATE
            if "MERGE" in action_str:
                return ConflictAction.MERGE
            if "DEPRECATE" in action_str:
                return ConflictAction.DEPRECATE_AND_CREATE

        except Exception as e:
            logger.warning(f"Conflict resolution failed: {str(e)}")

        return ConflictAction.UPDATE  # Default fallback

    def extract_facts(
        self,
        db: Session,
        user_id: int,
        user_message: str,
        assistant_reply: str,
        session_id: Optional[str] = None
    ) -> List[UserMemory]:
        """Extract user facts from conversation turn and upsert into database with Deduplication and Conflict Resolution."""
        extracted_data = self.extract_facts_from_text(user_message, assistant_reply)
        if not extracted_data:
            return []

        saved_memories: List[UserMemory] = []
        valid_fact_types = {e.value for e in FactType}

        for item in extracted_data:
            # 1. Validation
            fact_type = str(item.get("fact_type", "")).strip().lower()
            fact_key = str(item.get("fact_key", "")).strip().lower()
            content = str(item.get("content", "")).strip()
            confidence = float(item.get("confidence", 0.0))

            if not content or not fact_key:
                continue
            if fact_type not in valid_fact_types:
                fact_type = FactType.PREFERENCE.value
            if confidence < 0.7:
                logger.info(f"Ignored fact '{fact_key}' due to low confidence ({confidence}).")
                continue

            # 2. Deduplication (Find existing ACTIVE memory with same fact_key)
            stmt = select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.fact_key == fact_key,
                UserMemory.status == MemoryStatus.ACTIVE.value
            )
            existing = db.scalars(stmt).first()

            if not existing:
                # CREATE NEW
                new_mem = UserMemory(
                    user_id=user_id,
                    fact_type=fact_type,
                    fact_key=fact_key,
                    content=content,
                    confidence=confidence,
                    status=MemoryStatus.ACTIVE.value,
                    source_session_id=session_id
                )
                db.add(new_mem)
                saved_memories.append(new_mem)
                logger.info(f"Created new Fact '{fact_key}' for UserID={user_id}")
            else:
                # 3. Conflict Resolution
                action = self.resolve_conflict(existing.content, content)
                logger.info(f"Conflict detected for '{fact_key}'. Action decided: {action.value}")

                if action == ConflictAction.SKIP:
                    existing.confirmation_count += 1
                    saved_memories.append(existing)

                elif action == ConflictAction.UPDATE:
                    existing.content = content
                    existing.confidence = max(existing.confidence, confidence)
                    existing.version += 1
                    saved_memories.append(existing)

                elif action == ConflictAction.MERGE:
                    existing.content = f"{existing.content} | {content}"
                    existing.version += 1
                    saved_memories.append(existing)

                elif action == ConflictAction.DEPRECATE_AND_CREATE:
                    existing.status = MemoryStatus.DEPRECATED.value

                    new_mem = UserMemory(
                        user_id=user_id,
                        fact_type=fact_type,
                        fact_key=fact_key,
                        content=content,
                        confidence=confidence,
                        status=MemoryStatus.ACTIVE.value,
                        source_session_id=session_id
                    )
                    db.add(new_mem)
                    db.flush()  # Get ID for superseded_by

                    existing.superseded_by = new_mem.memory_id
                    saved_memories.append(new_mem)
                    saved_memories.append(existing) # Also return the deprecated one if needed, or omit it.

        # 4. Persistence (Commit once at the end)
        if saved_memories:
            try:
                # Remove duplicates if same object added twice to list
                unique_memories = list({id(m): m for m in saved_memories}.values())
                
                # Need to flush to get memory_id generated for new objects
                db.flush() 

                # Insert Outbox events in the same transaction
                for m in unique_memories:
                    # Decide action based on status
                    action = "DELETE" if m.status == MemoryStatus.DEPRECATED.value else "UPSERT"
                    
                    # Create Outbox record
                    outbox_entry = MemoryOutbox(
                        memory_id=m.memory_id,
                        action=action,
                        status="PENDING"
                    )
                    db.add(outbox_entry)

                db.commit()

                for m in unique_memories:
                    db.refresh(m)
                saved_memories = unique_memories
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to commit extracted facts: {e}")
                return []

        return [m for m in saved_memories if m.status == MemoryStatus.ACTIVE.value]

    def get_user_facts(self, db: Session, user_id: int) -> List[UserMemory]:
        """Retrieve all active long-term facts belonging to user_id."""
        stmt = (
            select(UserMemory)
            .where(
                UserMemory.user_id == user_id,
                UserMemory.status.in_([MemoryStatus.ACTIVE.value, MemoryStatus.REINFORCED.value])
            )
            .order_by(UserMemory.updated_at.desc())
        )
        return list(db.scalars(stmt).all())

    def retrieve_relevant_facts(self, user_id: int, query: str, top_k: int = 5) -> str:
        """Retrieve relevant user facts using Semantic Vector Search from ChromaDB (Phase 4)."""
        if not query or not query.strip():
            return ""

        # Initialize Embedder and Store (lazy load)
        embedder = VectorEmbedder()
        vector_store = ChromaVectorStore(collection_name="user_memory")

        # 1. Embed query
        query_embedding = embedder.embed_query(query)

        # 2. Search ChromaDB with Metadata Filter for Security
        results = vector_store.search_similar(
            query_embedding=query_embedding,
            top_k=top_k,
            where={"user_id": user_id}
        )

        if not results:
            return ""

        # 3. Format to string
        # Filter active only in case the outbox didn't delete deprecated ones properly
        lines = []
        for res in results:
            meta = res.get("metadata", {})
            if meta.get("status") in [MemoryStatus.ACTIVE.value, MemoryStatus.REINFORCED.value]:
                fact_type = meta.get("fact_type", "fact").upper()
                content = res.get("text", "")
                lines.append(f"• [{fact_type}] {content}")

        return "\n".join(lines)

    def delete_fact(self, db: Session, user_id: int, fact_id: int) -> bool:
        """Delete a fact ensuring strict User ID isolation (Soft Delete)."""
        stmt = select(UserMemory).where(
            UserMemory.id == fact_id,
            UserMemory.user_id == user_id,
        )
        fact = db.scalars(stmt).first()
        if fact:
            fact.status = MemoryStatus.DELETED.value
            
            outbox_entry = MemoryOutbox(
                memory_id=fact.memory_id,
                action="DELETE",
                status="PENDING"
            )
            db.add(outbox_entry)
            
            db.commit()
            logger.info(f"Deleted (Soft) UserMemory ID={fact_id} for UserID={user_id}")
            return True
        return False
