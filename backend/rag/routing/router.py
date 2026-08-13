"""Context Router for determining the appropriate RAG and Memory flow."""

import re
import json
import logging
from enum import Enum
from typing import Optional, Dict, Any, List
# pyrefly: ignore [missing-import]
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from backend.app.config import settings

logger = logging.getLogger("travel_agent_router")


class RouteType(str, Enum):
    DIRECT_ANSWER = "direct_answer"
    RAG_ONLY = "rag_only"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    RAG_AND_MEMORY = "rag_and_memory"
    CLARIFY = "clarify"


class RouteDecision(BaseModel):
    route: RouteType = Field(..., description="The routing decision.")
    needs_rag: bool = Field(..., description="Whether to query ChromaDB for travel guides.")
    needs_memory_read: bool = Field(..., description="Whether to query ChromaDB for user facts.")
    should_write_memory: bool = Field(..., description="Whether this query likely introduces new user facts.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this decision.")
    rewritten_query: str = Field(..., description="Optimized query for vector search, or original if unchanged.")
    reason: str = Field(..., description="Explanation for this route decision.")


class ContextRouter:
    """Intelligent Router to decide the context requirements of a user query."""

    def __init__(self) -> None:
        self.client = self._get_llm_client()
        self.model_name = settings.ROUTER_MODEL
        self.confidence_threshold = 0.80

        # Fast path regex patterns
        self.greetings_pattern = re.compile(
            r"^(xin chào|chào|hello|hi|bye|tạm biệt|cảm ơn|thanks)( bạn| nhé| bot)?\s*[\.\!]*$",
            re.IGNORECASE
        )
        self.memory_write_pattern = re.compile(
            r"(nhớ là|lưu giúp|tôi thích|tôi bị dị ứng|note lại|hãy nhớ)",
            re.IGNORECASE
        )
        self.memory_read_pattern = re.compile(
            r"(bạn nhớ gì về tôi|tôi thích gì|tôi đã nói gì|sở thích của tôi)",
            re.IGNORECASE
        )

    def _get_llm_client(self) -> Optional[OpenAI]:
        """Get OpenAI client."""
        if not settings.GOOGLE_API_KEY:
            logger.warning("Google API Key missing. Router will fallback to default.")
            return None
        try:
            return OpenAI(
                base_url=settings.LLM_BASE_URL,
                api_key=settings.GOOGLE_API_KEY,
            )
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client for Router: {str(e)}")
            return None

    def determine_route(self, user_query: str, history: Optional[List[Dict[str, str]]] = None) -> RouteDecision:
        """Determine the route using fast paths first, then LLM classifier."""
        user_query = user_query.strip()
        
        # 1. Fast Path
        decision = self._check_fast_path(user_query)
        if decision:
            logger.info(f"Router Fast Path applied: {decision.route.value}")
            return decision

        # 2. LLM Classifier
        if not self.client:
            logger.warning("No LLM client available. Falling back to rag_and_memory.")
            return self._fallback_decision(user_query, "No LLM Client")

        decision = self._classify_with_llm(user_query, history)
        logger.info(
            f"Router LLM Classifier: Route={decision.route.value}, "
            f"Confidence={decision.confidence:.2f}, Reason='{decision.reason}'"
        )

        # 3. Fallback on low confidence
        if decision.confidence < self.confidence_threshold:
            logger.warning(f"Low confidence ({decision.confidence}). Falling back to rag_and_memory.")
            return self._fallback_decision(user_query, f"Low confidence: {decision.confidence}")

        return decision

    def _check_fast_path(self, user_query: str) -> Optional[RouteDecision]:
        """Use regex rules to quickly route simple queries."""
        # Cleaned query for exact matching
        clean_q = user_query.strip().lower()
        
        if self.greetings_pattern.match(clean_q):
            return RouteDecision(
                route=RouteType.DIRECT_ANSWER,
                needs_rag=False,
                needs_memory_read=False,
                should_write_memory=False,
                confidence=1.0,
                rewritten_query=user_query,
                reason="Matched greeting/farewell fast path."
            )
            
        if self.memory_read_pattern.search(clean_q):
            return RouteDecision(
                route=RouteType.MEMORY_READ,
                needs_rag=False,
                needs_memory_read=True,
                should_write_memory=False,
                confidence=0.95,
                rewritten_query=user_query,
                reason="Matched memory read fast path."
            )

        if self.memory_write_pattern.search(clean_q):
            # Still might need RAG if they say "Tôi thích ăn cay, gợi ý quán ở Đà Lạt"
            # But if it's just "Tôi thích ăn cay, nhớ nhé", it's purely write.
            # A safe fast-path here is assuming it's a write + acknowledge.
            # However, since they might ask for a recommendation in the same breath, 
            # we let LLM handle complex cases unless it's very short.
            if len(clean_q.split()) < 15:
                return RouteDecision(
                    route=RouteType.MEMORY_WRITE,
                    needs_rag=False,
                    needs_memory_read=False,
                    should_write_memory=True,
                    confidence=0.90,
                    rewritten_query=user_query,
                    reason="Matched memory write fast path for short query."
                )
                
        return None

    def _classify_with_llm(self, user_query: str, history: Optional[List[Dict[str, str]]] = None, retries: int = 1) -> RouteDecision:
        """Call LLM to classify the intent into a JSON object."""
        system_prompt = (
            "You are an intelligent Context Router for a Vietnam Travel AI Assistant.\n"
            "Your task is to analyze the user's latest query (and history if needed) to decide "
            "which backend services are required to answer it.\n\n"
            "Routes:\n"
            "1. 'direct_answer': Greetings, thank yous, or generic chat requiring NO travel knowledge or personal memory.\n"
            "2. 'rag_only': User asks about travel destinations, food, itineraries, etc. Needs Travel Knowledge.\n"
            "3. 'memory_read': User asks what you remember about them (e.g., 'What are my preferences?').\n"
            "4. 'memory_write': User explicitly states a preference or personal fact (e.g., 'I am allergic to seafood') without asking for a travel recommendation.\n"
            "5. 'rag_and_memory': User asks for a personalized travel recommendation based on their facts.\n"
            "6. 'clarify': The query is too ambiguous to answer.\n\n"
            "You MUST output a raw JSON object exactly matching this schema:\n"
            "{\n"
            "  \"route\": \"direct_answer\" | \"rag_only\" | \"memory_read\" | \"memory_write\" | \"rag_and_memory\" | \"clarify\",\n"
            "  \"needs_rag\": boolean,\n"
            "  \"needs_memory_read\": boolean,\n"
            "  \"should_write_memory\": boolean,\n"
            "  \"confidence\": float between 0.0 and 1.0,\n"
            "  \"rewritten_query\": \"A better search query for RAG, or the original if fine\",\n"
            "  \"reason\": \"Why you chose this route\"\n"
            "}\n"
        )

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            # Only include the last 4 turns to save tokens
            messages.extend(history[-4:])
        messages.append({"role": "user", "content": user_query})

        error_msg = ""
        for attempt in range(retries + 1):
            if error_msg:
                messages.append({"role": "user", "content": f"Your previous JSON failed validation: {error_msg}. Please fix it and output ONLY valid JSON."})
                
            try:
                completion = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=0.0, # Deterministic
                    response_format={"type": "json_object"}
                )
                
                raw_json = completion.choices[0].message.content
                if not raw_json:
                    raise ValueError("LLM returned empty content")
                    
                # Parse and validate
                decision = RouteDecision.model_validate_json(raw_json)
                return decision
                
            except (ValidationError, json.JSONDecodeError, ValueError) as e:
                logger.error(f"LLM Routing failed validation on attempt {attempt+1}: {str(e)}")
                error_msg = str(e)
            except Exception as e:
                logger.error(f"Unexpected error during LLM routing: {str(e)}")
                break
                
        # If all retries fail, return safe fallback
        logger.warning("All routing retries failed. Returning safe fallback.")
        return self._fallback_decision(user_query, "JSON Validation Failed multiple times")

    def _fallback_decision(self, user_query: str, reason: str) -> RouteDecision:
        """Safe fallback route (assuming it needs RAG and Memory to be safe)."""
        return RouteDecision(
            route=RouteType.RAG_AND_MEMORY,
            needs_rag=True,
            needs_memory_read=True,
            should_write_memory=True,
            confidence=0.0,
            rewritten_query=user_query,
            reason=f"Fallback triggered due to: {reason}"
        )
