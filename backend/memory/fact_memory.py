"""Long-term Memory Service: Auto-extracts user facts and preferences bound to User ID."""

import json
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from openai import OpenAI

from backend.app.config import settings
from backend.app.models.memory import UserMemory

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
            '    "fact_type": "preference | visited_place | budget | travel_style | dietary",\n'
            '    "fact_key": "Mã định danh tiếng Anh viết thường (VD: food_allergy, visited_cities, transport_mode)",\n'
            '    "fact_value": "Mô tả ngắn gọn bằng Tiếng Việt (VD: Dị ứng hải sản)",\n'
            '    "confidence": 1.0\n'
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

            # Clean JSON markdown fences if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            extracted_items = json.loads(raw_text)
            if isinstance(extracted_items, list):
                return extracted_items

        except Exception as e:
            logger.warning(f"Fact extraction parsing notice: {str(e)}")

        return []

    def extract_facts(
        self,
        db: Session,
        user_id: int,
        user_message: str,
        assistant_reply: str,
    ) -> List[UserMemory]:
        """Extract user facts from conversation turn and upsert into database."""
        extracted_data = self.extract_facts_from_text(user_message, assistant_reply)
        if not extracted_data:
            return []

        saved_memories: List[UserMemory] = []

        for item in extracted_data:
            fact_type = str(item.get("fact_type", "preference")).strip().lower()
            fact_key = str(item.get("fact_key", "general_fact")).strip().lower()
            fact_value = str(item.get("fact_value", "")).strip()
            confidence = float(item.get("confidence", 1.0))

            if not fact_value or not fact_key:
                continue

            # Upsert logic: Update if user_id & fact_key exists, else insert new
            stmt = select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.fact_key == fact_key,
            )
            existing = db.scalars(stmt).first()

            if existing:
                existing.fact_value = fact_value
                existing.fact_type = fact_type
                existing.confidence = confidence
                db.commit()
                db.refresh(existing)
                saved_memories.append(existing)
                logger.info(f"Updated UserMemory ID={existing.id} for UserID={user_id}, Key='{fact_key}'")
            else:
                new_mem = UserMemory(
                    user_id=user_id,
                    fact_type=fact_type,
                    fact_key=fact_key,
                    fact_value=fact_value,
                    confidence=confidence,
                )
                db.add(new_mem)
                db.commit()
                db.refresh(new_mem)
                saved_memories.append(new_mem)
                logger.info(f"Created new UserMemory ID={new_mem.id} for UserID={user_id}, Key='{fact_key}'")

        return saved_memories

    def get_user_facts(self, db: Session, user_id: int) -> List[UserMemory]:
        """Retrieve all long-term facts belonging strictly to user_id."""
        stmt = (
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .order_by(UserMemory.updated_at.desc())
        )
        return list(db.scalars(stmt).all())

    def format_facts_for_prompt(self, db: Session, user_id: int) -> str:
        """Format user long-term facts into a bulleted string for LLM system prompt."""
        facts = self.get_user_facts(db, user_id)
        if not facts:
            return ""

        lines = [f"• [{fact.fact_type.upper()}] {fact.fact_value}" for fact in facts]
        return "\n".join(lines)

    def delete_fact(self, db: Session, user_id: int, fact_id: int) -> bool:
        """Delete a fact ensuring strict User ID isolation."""
        stmt = select(UserMemory).where(
            UserMemory.id == fact_id,
            UserMemory.user_id == user_id,
        )
        fact = db.scalars(stmt).first()
        if fact:
            db.delete(fact)
            db.commit()
            logger.info(f"Deleted UserMemory ID={fact_id} for UserID={user_id}")
            return True
        return False
