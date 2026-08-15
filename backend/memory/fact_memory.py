"""Long-term Memory Service: Auto-extracts user facts and preferences bound to User ID."""

import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ValidationError
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from sqlalchemy import select
# pyrefly: ignore [missing-import]
from sqlalchemy.exc import IntegrityError
# pyrefly: ignore [missing-import]
from sqlalchemy.orm.exc import StaleDataError
import time
# pyrefly: ignore [missing-import]
from openai import OpenAI

from backend.app.config import settings
from backend.app.models.memory import UserMemory, MemoryOutbox
from backend.memory.enums import FactType, MemoryStatus, ConflictAction
from backend.rag.embedding.embedder import VectorEmbedder
from backend.rag.retrieval.vector_store import ChromaVectorStore

logger = logging.getLogger("travel_agent_fact_memory")


class FactItemModel(BaseModel):
    fact_type: str = Field(...)
    fact_key: str = Field(...)
    content: str = Field(...)
    confidence: float = Field(...)

class FactExtractionResult(BaseModel):
    facts: List[FactItemModel] = Field(default_factory=list)

class ConflictDecision(BaseModel):
    action: ConflictAction = Field(..., description="Hành động giải quyết mâu thuẫn dữ liệu: skip, update, merge, deprecate.")
    reasoning: str = Field(..., description="Lý do tại sao chọn hành động này.")
    merged_content: Optional[str] = Field(None, description="CHỈ BẮT BUỘC nếu action là merge. Hãy đóng vai trò biên tập viên, viết lại một câu văn Tiếng Việt hoàn chỉnh, mượt mà bao hàm ý nghĩa của cả thông tin cũ và mới.")

class FactMemoryService:
    """Manages long-term user facts and preference extraction."""

    def __init__(
        self,
        llm_client: OpenAI,
        embedder: VectorEmbedder,
        vector_store: ChromaVectorStore,
    ):
        self._client = llm_client
        self._embedder = embedder
        self._vector_store = vector_store

    def extract_facts_from_text(
        self, user_message: str, assistant_reply: str
    ) -> List[Dict[str, Any]]:
        """Call LLM to extract structured facts from a conversation turn."""
        client = self._client
        if not client:
            return []

        extraction_prompt = (
            "Bạn là một AI Memory Extractor chuyên nghiệp cho ứng dụng du lịch Việt Nam.\n"
            "Hãy phân tích đoạn hội thoại mới nhất bên dưới giữa User và Assistant để trích xuất các THÔNG TIN CÁ NHÂN "
            "của User (sở thích ăn uống, phong cách du lịch, địa điểm đã từng đi, hạn chế chế độ ăn, ngân sách...).\n\n"
            "=== CHÍNH SÁCH TRÍCH XUẤT (QUAN TRỌNG) ===\n"
            "1. CHỈ trích xuất thông tin từ câu nói của USER. KHÔNG trích xuất thông tin mà Assistant đề xuất.\n"
            "2. KHÔNG trích xuất thông tin chung về địa điểm du lịch (VD: 'Đà Lạt lạnh' -> KHÔNG phải thông tin cá nhân).\n"
            "3. TUYỆT ĐỐI KHÔNG trích xuất thông tin nhạy cảm PII (số điện thoại, email, địa chỉ nhà, CCCD, thẻ tín dụng/ngân hàng).\n"
            "4. CẤM trích xuất các câu cảm thán ngắn, hoặc thông tin do user lặp lại câu hỏi của Assistant.\n"
            "5. Nếu User nói KHÔNG thích hoặc phủ định (VD: 'Tôi không ăn cay'), hãy ghi rõ sự phủ định trong phần 'content' hoặc dùng fact_key dạng 'dislike_...'.\n\n"
            "=== ĐOẠN HỘI THOẠI ===\n"
            f"User: {user_message}\n"
            f"Assistant: {assistant_reply}\n\n"
            "=== EXAMPLES ===\n"
            "- User: 'Tôi dị ứng hải sản nhé' -> {\"facts\": [{\"fact_type\": \"dietary\", \"fact_key\": \"seafood_allergy\", \"content\": \"Dị ứng hải sản\", \"confidence\": 0.99}]}\n"
            "- User: 'Nóng quá' -> {\"facts\": []} (Không phải sở thích)\n"
            "- Assistant: 'Bạn thích ăn lẩu không?'. User: 'Cũng được' -> {\"facts\": []} (Thiếu thông tin cụ thể)\n\n"
            "=== YÊU CẦU ĐẦU RA ===\n"
            "Trả về kết quả dưới dạng JSON object, bắt buộc phải có key 'facts' chứa danh sách các fact tìm thấy.\n"
            "Mỗi item trong mảng 'facts' có dạng đúng JSON schema sau:\n"
            "{\n"
            '  "fact_type": "preference | identity | visited_place | budget | travel_style | dietary | behavior",\n'
            '  "fact_key": "Mã định danh tiếng Anh viết thường (VD: food_allergy, transport_mode)",\n'
            '  "content": "Mô tả chi tiết bằng Tiếng Việt (VD: Dị ứng nặng với hải sản)",\n'
            '  "confidence": 0.9\n'
            "}\n"
            "Nếu không có thông tin cá nhân mới nào, trả về JSON rỗng: {\"facts\": []}. "
            "BẮT BUỘC bọc chuỗi JSON trả về trong cặp dấu ```json và ```."
        )

        logger.info(f"\n{'='*20} FACT EXTRACTOR PROMPT {'='*20}\n{extraction_prompt}\n{'='*63}")

        try:
            completion = client.chat.completions.create(
                model=settings.MEMORY_EXTRACTION_MODEL,
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0.1,
                max_tokens=2000,
            )
            raw_text = completion.choices[0].message.content.strip()
            logger.info(f"\n{'='*20} FACT EXTRACTOR OUTPUT {'='*20}\n{raw_text}\n{'='*63}")

            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].rsplit("```", 1)[0].strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            parsed_json = json.loads(raw_text)
            extracted_items = parsed_json.get("facts", [])
            
            validated_items = []
            if isinstance(extracted_items, list):
                for item in extracted_items:
                    try:
                        validated_item = FactItemModel.model_validate(item)
                        validated_items.append(validated_item.model_dump())
                    except ValidationError as ve:
                        logger.warning(f"FactItem validation error: {ve}")
                return validated_items

        except json.JSONDecodeError as jde:
            logger.warning(f"JSON decode error in fact extraction: {str(jde)}")
        except Exception as e:
            logger.warning(f"Fact extraction failed: {str(e)}")

        return []

    def resolve_conflict(self, old_content: str, new_content: str) -> ConflictDecision:
        """Use LLM to determine the ConflictAction when fact_key collides."""
        client = self._client
        if not client:
            return ConflictDecision(action=ConflictAction.UPDATE, reasoning="Fallback to update", merged_content=None)

        prompt = (
            "Bạn là AI phân xử mâu thuẫn bộ nhớ (Memory Conflict Resolver).\n"
            "Người dùng vừa cung cấp một thông tin mới có cùng Chủ đề (fact_key) với thông tin cũ trong database.\n"
            "Nhiệm vụ của bạn là so sánh 2 thông tin và quyết định HÀNH ĐỘNG xử lý phù hợp nhất.\n\n"
            f"- Cũ: {old_content}\n"
            f"- Mới: {new_content}\n\n"
            "=== EXAMPLES ===\n"
            "- Cũ: 'Thích ăn hải sản', Mới: 'Dị ứng hải sản' -> action: 'deprecate' (Mâu thuẫn hoàn toàn)\n"
            "- Cũ: 'Đi Sapa', Mới: 'Đi Sapa tháng 10' -> action: 'update' (Chi tiết hơn)\n"
            "- Cũ: 'Thích đi biển', Mới: 'Thích đi núi' -> action: 'merge', merged_content: 'Thích đi cả biển và núi' (Bổ sung cho nhau)\n"
            "- Cũ: 'Không ăn cay', Mới: 'Không ăn cay' -> action: 'skip' (Giống hệt)\n"
        )
        try:
            completion = client.beta.chat.completions.parse(
                model=settings.CONFLICT_RESOLUTION_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format=ConflictDecision,
                temperature=0.0,
            )
            return completion.choices[0].message.parsed
        except Exception as e:
            logger.warning(f"Conflict resolution failed: {str(e)}")

        return ConflictDecision(action=ConflictAction.UPDATE, reasoning="Exception fallback", merged_content=None)

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

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # 2. Deduplication (Find existing ACTIVE memory with same fact_key)
                    # We do not use FOR UPDATE to avoid blocking the DB during slow LLM calls.
                    stmt = select(UserMemory).where(
                        UserMemory.user_id == user_id,
                        UserMemory.fact_key == fact_key,
                        UserMemory.status == MemoryStatus.ACTIVE.value
                    )
                    existing = db.scalars(stmt).first()

                    # Pre-fetch content in case we need to pass it to LLM outside transaction
                    existing_content = existing.content if existing else None
                    
                    # Ensure we have no pending locks from read before slow LLM call
                    db.commit()

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
                        db.flush()
                        
                        outbox_entry = MemoryOutbox(
                            memory_id=new_mem.memory_id,
                            action="UPSERT",
                            status="PENDING"
                        )
                        db.add(outbox_entry)
                        
                        db.commit()
                        db.refresh(new_mem)
                        saved_memories.append(new_mem)
                        logger.info(f"Created new Fact '{fact_key}' for UserID={user_id}")
                        break # Break retry loop
                        
                    else:
                        # 3. Conflict Resolution (Slow I/O)
                        # We are not holding any row locks here!
                        decision = self.resolve_conflict(existing_content, content)
                        action = decision.action
                        logger.info(f"Conflict detected for '{fact_key}'. Action decided: {action.value}. Reason: {decision.reasoning}")

                        # Re-attach existing to the session if needed (commit expired it)
                        existing = db.merge(existing)

                        if action == ConflictAction.SKIP:
                            existing.confirmation_count += 1
                            outbox_action = "UPSERT"

                        elif action == ConflictAction.UPDATE:
                            existing.content = content
                            existing.confidence = max(existing.confidence, confidence)
                            outbox_action = "UPSERT"

                        elif action == ConflictAction.MERGE:
                            if decision.merged_content:
                                existing.content = decision.merged_content
                            else:
                                existing.content = f"{existing_content} | {content}"
                            outbox_action = "UPSERT"

                        elif action == ConflictAction.DEPRECATE_AND_CREATE:
                            existing.status = MemoryStatus.DEPRECATED.value
                            outbox_entry_del = MemoryOutbox(
                                memory_id=existing.memory_id,
                                action="DELETE",
                                status="PENDING"
                            )
                            db.add(outbox_entry_del)

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
                            db.flush()  # Get ID
                            existing.superseded_by = new_mem.memory_id
                            
                            outbox_entry_new = MemoryOutbox(
                                memory_id=new_mem.memory_id,
                                action="UPSERT",
                                status="PENDING"
                            )
                            db.add(outbox_entry_new)
                            
                            db.commit()
                            db.refresh(new_mem)
                            db.refresh(existing)
                            saved_memories.append(new_mem)
                            saved_memories.append(existing)
                            break # Break retry loop

                        if action != ConflictAction.DEPRECATE_AND_CREATE:
                            outbox_entry = MemoryOutbox(
                                memory_id=existing.memory_id,
                                action=outbox_action,
                                status="PENDING"
                            )
                            db.add(outbox_entry)
                            db.commit()
                            db.refresh(existing)
                            saved_memories.append(existing)
                            break # Break retry loop

                except (StaleDataError, IntegrityError) as e:
                    db.rollback()
                    logger.warning(f"TOCTOU race condition intercepted for '{fact_key}'. Retrying ({attempt+1}/{max_retries})... Error: {e}")
                    if attempt == max_retries - 1:
                        logger.error(f"Failed to process fact '{fact_key}' after {max_retries} attempts due to concurrency.")
                    time.sleep(0.5)
                except Exception as e:
                    db.rollback()
                    logger.error(f"Failed to commit extracted fact '{fact_key}': {e}")
                    break

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

    def retrieve_relevant_facts(self, user_id: int, query: str, top_k: int = 5, min_score: float = 0.55) -> str:
        """Retrieve relevant user facts using Semantic Vector Search from ChromaDB (Phase 4)."""
        if not query or not query.strip():
            return ""

        # 1. Embed query
        query_embedding = self._embedder.embed_query(query)

        # 2. Search ChromaDB with Metadata Filter for Security
        results = self._vector_store.search_similar(
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
            if res.get("score", 0.0) < min_score:
                continue
                
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
