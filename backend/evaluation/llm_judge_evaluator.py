"""LLM-as-a-judge Evaluator for Memory Extraction Accuracy."""

import json
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
# pyrefly: ignore [missing-import]
from openai import OpenAI

from backend.app.config import settings

logger = logging.getLogger("travel_agent_evaluator")

class EvaluationResult(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0, description="Accuracy score from 0.0 to 1.0")
    reasoning: str = Field(..., description="Explanation for the score")
    missed_facts: List[str] = Field(default_factory=list, description="Facts that should have been extracted but were missed")
    hallucinated_facts: List[str] = Field(default_factory=list, description="Facts that were extracted but not present in the conversation")

class LLMJudgeEvaluator:
    """Evaluates the quality of Memory Extraction and RAG using an LLM Judge."""
    
    def __init__(self):
        self.client = None
        if settings.GOOGLE_API_KEY:
            self.client = OpenAI(
                base_url=settings.LLM_BASE_URL,
                api_key=settings.GOOGLE_API_KEY
            )

    def evaluate_memory_extraction(
        self,
        user_message: str,
        assistant_reply: str,
        extracted_facts: List[Dict[str, Any]],
        ground_truth: List[Dict[str, Any]] = None
    ) -> EvaluationResult:
        """Evaluate if the extracted facts accurately represent the conversation."""
        if not self.client:
            logger.warning("LLM client not configured for evaluation.")
            return EvaluationResult(score=0.0, reasoning="LLM client not configured.")

        # Convert facts to JSON string for prompt
        extracted_str = json.dumps(extracted_facts, ensure_ascii=False, indent=2)
        
        prompt = (
            "Bạn là một AI Judge chuyên đánh giá hệ thống Trích xuất Bộ nhớ (Memory Extraction).\n"
            "Hãy đánh giá danh sách các fact được trích xuất từ đoạn hội thoại dưới đây.\n\n"
            "=== TIÊU CHÍ ĐÁNH GIÁ ===\n"
            "1. Chính xác (Precision): Không trích xuất sai sự thật, không ảo giác (hallucination).\n"
            "2. Đầy đủ (Recall): Không bỏ sót thông tin quan trọng.\n"
            "3. Tuân thủ quy tắc: KHÔNG trích xuất PII (SĐT, email, thẻ tín dụng, v.v.), KHÔNG trích xuất thông tin chung.\n\n"
            "=== DỮ LIỆU ===\n"
            f"User: {user_message}\n"
            f"Assistant: {assistant_reply}\n\n"
            f"Extracted Facts:\n{extracted_str}\n\n"
        )
        
        if ground_truth:
            gt_str = json.dumps(ground_truth, ensure_ascii=False, indent=2)
            prompt += f"Ground Truth (Đáp án chuẩn):\n{gt_str}\n\n"
            
        prompt += (
            "=== YÊU CẦU ĐẦU RA ===\n"
            "Trả về đánh giá dưới định dạng JSON:\n"
            "{\n"
            '  "score": 0.8, // Điểm từ 0.0 đến 1.0\n'
            '  "reasoning": "Lý do chi tiết...",\n'
            '  "missed_facts": ["fact 1 bị sót", "fact 2 bị sót"], // Trống nếu không sót\n'
            '  "hallucinated_facts": ["fact 1 ảo giác"] // Trống nếu không bị ảo giác\n'
            "}\n"
        )

        try:
            completion = self.client.chat.completions.create(
                model=getattr(settings, "EVALUATION_MODEL", settings.LLM_MODEL),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            
            raw_text = completion.choices[0].message.content.strip()
            parsed = json.loads(raw_text)
            
            return EvaluationResult(**parsed)
            
        except Exception as e:
            logger.error(f"Evaluation failed: {str(e)}")
            return EvaluationResult(score=0.0, reasoning=f"Error: {str(e)}")

# CLI runner for testing
if __name__ == "__main__":
    evaluator = LLMJudgeEvaluator()
    test_user_msg = "Tôi bị dị ứng hải sản và số điện thoại của tôi là 0912345678."
    test_assistant = "Vâng tôi đã lưu thông tin dị ứng hải sản của bạn."
    test_extracted = [
        {"fact_type": "dietary", "fact_key": "allergy", "content": "Dị ứng hải sản", "confidence": 1.0}
    ]
    
    result = evaluator.evaluate_memory_extraction(
        user_message=test_user_msg,
        assistant_reply=test_assistant,
        extracted_facts=test_extracted
    )
    
    print("Evaluation Result:")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
