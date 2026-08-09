"""Generate retrieval benchmark cases from enriched child chunks.

This tool uses Gemini through the OpenAI-compatible API with structured outputs.
It creates query-level golden records for retrieval evaluation, not final answer
evaluation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from dotenv import load_dotenv
from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

DEFAULT_INPUT = ROOT_DIR / "data" / "processed" / "children_chunks_enriched.json"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "evaluation" / "datasets" / "retrieval_benchmark_generated.jsonl"
DEFAULT_CACHE = ROOT_DIR / "data" / "evaluation" / "cache" / "retrieval_benchmark_generation_cache.jsonl"

MODEL = os.getenv("BENCHMARK_MODEL", "gemini-3.5-flash-lite")
GEMINI_BASE_URL = os.getenv("GEMINI_OPENAI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")

ALLOWED_INTENTS = [
    "attraction",
    "cuisine",
    "culture",
    "accommodation",
    "transportation",
    "weather",
    "activities",
    "plan",
    "budget",
    "compare",
    "hotel",
    "itinerary",
]

INTENT_KEYWORDS = {
    "attraction": ["attraction", "destination", "sight", "landmark", "museum", "temple", "beach"],
    "cuisine": ["food", "cuisine", "dish", "restaurant", "street food", "eat", "coffee"],
    "culture": ["culture", "heritage", "history", "festival", "traditional", "craft", "art"],
    "accommodation": ["accommodation", "stay", "resort", "homestay", "hostel", "villa"],
    "transportation": ["transport", "airport", "bus", "train", "taxi", "flight", "transfer"],
    "weather": ["weather", "season", "rain", "sunny", "temperature", "climate"],
    "activities": ["activity", "activities", "things to do", "experience", "tour", "nightlife"],
    "plan": ["plan", "planning", "guide", "tips", "need to know"],
    "budget": ["budget", "price", "cost", "fee", "cheap", "affordable"],
    "compare": ["compare", "versus", "vs", "better than"],
    "hotel": ["hotel", "hotels"],
    "itinerary": ["itinerary", "days", "day trip", "schedule", "route"],
}

logger = logging.getLogger("retrieval_benchmark_generation")

_LAST_REQUEST_AT = 0.0


class Fact(BaseModel):
    fact_id: str = Field(description="Stable ID such as f_01, f_02.")
    fact: str = Field(description="One atomic source-supported travel fact.")


class FactExtraction(BaseModel):
    usable: bool
    facts: List[Fact]
    intents: List[str]
    locations: List[str]


class QueryCase(BaseModel):
    query: str
    language: str
    intent: List[str]
    difficulty: str
    required_fact_ids: List[str]


class GeneratedQueries(BaseModel):
    queries: List[QueryCase]


def load_json(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}.")
    return [item for item in data if isinstance(item, dict)]


def write_jsonl(path: Path, records: Iterable[Dict[str, Any]], append: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    count = 0
    with path.open(mode, encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def load_cache(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}

    cache: Dict[str, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            item = json.loads(line)
            child_id = item.get("child_id")
            if child_id:
                cache[str(child_id)] = item
    return cache


def append_cache(path: Path, item: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(item, ensure_ascii=False) + "\n")


def reset_jsonl(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def child_search_blob(child: Dict[str, Any]) -> str:
    metadata = child.get("metadata") or {}
    parts = [
        child.get("heading"),
        child.get("source_text"),
        metadata.get("title"),
        metadata.get("topic"),
        metadata.get("category"),
        metadata.get("locations"),
        metadata.get("entity_type"),
        metadata.get("content_type"),
    ]
    return " ".join(json.dumps(part, ensure_ascii=False) if isinstance(part, (list, dict)) else str(part or "") for part in parts).lower()


def infer_intents_from_child(child: Dict[str, Any]) -> Set[str]:
    blob = child_search_blob(child)
    intents: Set[str] = set()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword_matches(blob, keyword) for keyword in keywords):
            intents.add(intent)
    return intents or {"activities"}


def keyword_matches(blob: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in blob
    return bool(re.search(rf"\b{re.escape(keyword)}\b", blob))


def select_chunks(
    children: List[Dict[str, Any]],
    limit: int,
    target_intents: List[str],
    min_words: int,
) -> List[Dict[str, Any]]:
    """Select chunks while trying to cover target intents."""
    candidates = [
        child
        for child in children
        if child.get("child_id")
        and child.get("parent_id")
        and child.get("source_text")
        and int((child.get("metadata") or {}).get("word_count") or 0) >= min_words
    ]

    selected: List[Dict[str, Any]] = []
    used_ids: Set[str] = set()
    used_documents: Set[str] = set()

    for intent in target_intents:
        if len(selected) >= limit:
            break
        fallback = None
        for child in candidates:
            child_id = str(child.get("child_id"))
            if child_id in used_ids:
                continue
            if intent in infer_intents_from_child(child):
                if str(child.get("document_id")) not in used_documents:
                    selected.append(child)
                    used_ids.add(child_id)
                    used_documents.add(str(child.get("document_id")))
                    fallback = None
                    break
                if fallback is None:
                    fallback = child
        if fallback is not None and len(selected) < limit:
            child_id = str(fallback.get("child_id"))
            selected.append(fallback)
            used_ids.add(child_id)
            used_documents.add(str(fallback.get("document_id")))

    for child in candidates:
        if len(selected) >= limit:
            break
        child_id = str(child.get("child_id"))
        document_id = str(child.get("document_id"))
        if child_id not in used_ids and document_id not in used_documents:
            selected.append(child)
            used_ids.add(child_id)
            used_documents.add(document_id)

    for child in candidates:
        if len(selected) >= limit:
            break
        child_id = str(child.get("child_id"))
        if child_id not in used_ids:
            selected.append(child)
            used_ids.add(child_id)

    return selected


def get_client() -> OpenAI:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY before running this tool.")
    return OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL)


def extract_retry_seconds(error: Exception) -> Optional[float]:
    """Best-effort parsing of Gemini retry hints from OpenAI-compatible errors."""
    text = str(error)
    patterns = [
        r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)s",
        r"retry in (\d+(?:\.\d+)?)s",
        r"Please retry in (\d+(?:\.\d+)?)s",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def wait_for_rate_limit(request_delay: float) -> None:
    """Throttle outgoing model requests across fact/query generation calls."""
    global _LAST_REQUEST_AT
    if request_delay <= 0:
        return

    elapsed = time.monotonic() - _LAST_REQUEST_AT
    if elapsed < request_delay:
        sleep_for = request_delay - elapsed
        logger.info("Throttling model request for %.1fs.", sleep_for)
        time.sleep(sleep_for)


def parse_completion(
    client: OpenAI,
    model: str,
    messages: List[Dict[str, str]],
    response_format: type[BaseModel],
    request_delay: float,
    max_retries: int,
) -> BaseModel:
    """Call the model with structured output, throttling, and retry handling."""
    global _LAST_REQUEST_AT
    retryable_errors = (RateLimitError, APITimeoutError, APIConnectionError, APIError)

    for attempt in range(max_retries + 1):
        try:
            wait_for_rate_limit(request_delay)
            completion = client.beta.chat.completions.parse(
                model=model,
                messages=messages,
                response_format=response_format,
                temperature=0.2,
            )
            _LAST_REQUEST_AT = time.monotonic()
            parsed = completion.choices[0].message.parsed
            if parsed is None:
                raise RuntimeError("Model returned no parsed structured output.")
            return parsed
        except retryable_errors as error:
            _LAST_REQUEST_AT = time.monotonic()
            if attempt >= max_retries:
                raise

            retry_seconds = extract_retry_seconds(error)
            if retry_seconds is None:
                retry_seconds = min(90.0, max(request_delay, 5.0) * (2 ** attempt))
            retry_seconds += 1.0
            logger.warning(
                "Model request failed with %s. Retrying in %.1fs (%s/%s).",
                type(error).__name__,
                retry_seconds,
                attempt + 1,
                max_retries,
            )
            time.sleep(retry_seconds)

    raise RuntimeError("Model request failed after retry loop.")


def extract_facts(
    client: OpenAI,
    child: Dict[str, Any],
    model: str,
    max_facts: int,
    request_delay: float,
    max_retries: int,
) -> FactExtraction:
    system_prompt = f"""
You are building a retrieval benchmark for a Vietnam travel RAG system.

Extract only facts explicitly supported by the supplied child chunk.

Rules:
- Never use external knowledge.
- Never infer unstated information.
- Each fact must be atomic.
- Preserve named entities exactly as written.
- Extract only facts useful for realistic travel questions.
- Use fact IDs f_01, f_02, ...
- Return at most {max_facts} facts.
- intents must use only these labels: {", ".join(ALLOWED_INTENTS)}.
- Mark usable=false if the chunk lacks useful factual travel content.
""".strip()

    user_prompt = f"""
HEADING:
{child.get("heading")}

TEXT:
{child.get("source_text")}

METADATA:
{json.dumps(child.get("metadata") or {}, ensure_ascii=False)}
""".strip()

    parsed = parse_completion(
        client,
        model,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        FactExtraction,
        request_delay=request_delay,
        max_retries=max_retries,
    )
    return parsed  # type: ignore[return-value]


def generate_queries(
    client: OpenAI,
    child: Dict[str, Any],
    facts: FactExtraction,
    model: str,
    queries_per_chunk: int,
    request_delay: float,
    max_retries: int,
) -> GeneratedQueries:
    system_prompt = f"""
Generate realistic travel queries for retrieval evaluation.

Rules:
- Every query must be answerable using the supplied facts.
- Never use external knowledge.
- Do not copy source wording verbatim.
- Queries should sound like real travelers.
- Generate lexical and semantic diversity.
- Use Vietnamese or English depending on the likely user need.
- Assign only fact IDs actually needed to answer each query.
- intent must use only these labels: {", ".join(ALLOWED_INTENTS)}.
- difficulty must be one of: easy, medium, hard.
""".strip()

    user_prompt = f"""
SOURCE:
{child.get("source_text")}

CHUNK_METADATA:
{json.dumps(child.get("metadata") or {}, ensure_ascii=False)}

FACTS:
{facts.model_dump_json()}

Generate up to {queries_per_chunk} useful queries.
""".strip()

    parsed = parse_completion(
        client,
        model,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        GeneratedQueries,
        request_delay=request_delay,
        max_retries=max_retries,
    )
    return parsed  # type: ignore[return-value]


def normalize_intents(values: List[str]) -> List[str]:
    normalized = []
    for value in values:
        intent = str(value).strip().lower().replace(" ", "_")
        if intent in ALLOWED_INTENTS and intent not in normalized:
            normalized.append(intent)
    return normalized


def province_from_child(child: Dict[str, Any], extracted: Optional[FactExtraction] = None) -> str:
    metadata = child.get("metadata") or {}
    primary = metadata.get("primary_location")
    if primary:
        return str(primary)
    locations = metadata.get("locations") or []
    if isinstance(locations, list) and locations:
        return str(locations[0])
    if extracted and extracted.locations:
        return str(extracted.locations[0])
    return ""


def build_test_cases(
    child: Dict[str, Any],
    extracted: FactExtraction,
    generated: GeneratedQueries,
    model: str,
) -> List[Dict[str, Any]]:
    fact_map = {fact.fact_id: fact.fact for fact in extracted.facts}
    metadata = child.get("metadata") or {}
    child_id = str(child["child_id"])
    parent_id = str(child["parent_id"])
    document_id = str(child.get("document_id") or metadata.get("document_id") or "")

    records = []
    for index, case in enumerate(generated.queries):
        required_fact_ids = [fact_id for fact_id in case.required_fact_ids if fact_id in fact_map]
        if not required_fact_ids:
            continue

        records.append(
            {
                "query_id": f"{child_id}:q:{index:02d}",
                "query": case.query.strip(),
                "language": case.language.strip().lower() or "vi",
                "intent": normalize_intents(case.intent),
                "province": province_from_child(child, extracted),
                "difficulty": case.difficulty.strip().lower(),
                "answerable": True,
                "relevant_document_ids": [document_id] if document_id else [],
                "relevant_parent_ids": [parent_id],
                "relevant_chunk_ids": [child_id],
                "relevant_child_ids": [child_id],
                "source_chunk_id": child_id,
                "source_parent_id": parent_id,
                "source_document_id": document_id,
                "source_title": metadata.get("title", ""),
                "source_url": metadata.get("url", ""),
                "gold_facts": [fact_map[fact_id] for fact_id in required_fact_ids],
                "required_fact_ids": required_fact_ids,
                "source": "llm_synthetic",
                "generation_model": model,
            }
        )

    return records


def process_child(
    client: OpenAI,
    child: Dict[str, Any],
    model: str,
    max_facts: int,
    queries_per_chunk: int,
    request_delay: float,
    max_retries: int,
) -> Dict[str, Any]:
    extracted = extract_facts(
        client,
        child,
        model=model,
        max_facts=max_facts,
        request_delay=request_delay,
        max_retries=max_retries,
    )
    if not extracted.usable or not extracted.facts:
        return {
            "child_id": child.get("child_id"),
            "usable": False,
            "facts": extracted.model_dump(),
            "queries": {"queries": []},
            "records": [],
        }

    generated = generate_queries(
        client,
        child,
        extracted,
        model=model,
        queries_per_chunk=queries_per_chunk,
        request_delay=request_delay,
        max_retries=max_retries,
    )
    records = build_test_cases(child, extracted, generated, model=model)
    return {
        "child_id": child.get("child_id"),
        "usable": True,
        "facts": extracted.model_dump(),
        "queries": generated.model_dump(),
        "records": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate retrieval benchmark JSONL from enriched child chunks.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--queries-per-chunk", type=int, default=3)
    parser.add_argument("--max-facts", type=int, default=8)
    parser.add_argument("--min-words", type=int, default=35)
    parser.add_argument(
        "--request-delay",
        type=float,
        default=4.5,
        help="Minimum seconds between model requests. Gemini free tier is commonly 15 RPM, so 4.5 is conservative.",
    )
    parser.add_argument("--max-retries", type=int, default=8, help="Retries per model request after 429/timeout/API errors.")
    parser.add_argument("--append", action="store_true", help="Append records to output instead of replacing it.")
    parser.add_argument("--no-cache", action="store_true", help="Ignore and do not write the generation cache.")
    parser.add_argument("--dry-run", action="store_true", help="Select chunks and print IDs without calling the model.")
    parser.add_argument(
        "--target-intents",
        default=",".join(ALLOWED_INTENTS),
        help="Comma-separated intent labels used for balanced chunk selection.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    args = parse_args()

    target_intents = [
        item.strip().lower()
        for item in args.target_intents.split(",")
        if item.strip().lower() in ALLOWED_INTENTS
    ] or ALLOWED_INTENTS

    children = load_json(args.input)
    selected = select_chunks(children, limit=args.limit, target_intents=target_intents, min_words=args.min_words)
    logger.info("Selected %s chunks from %s.", len(selected), args.input)

    for child in selected:
        logger.info(
            "Selected child=%s inferred_intents=%s title=%s",
            child.get("child_id"),
            sorted(infer_intents_from_child(child)),
            (child.get("metadata") or {}).get("title"),
        )

    if args.dry_run:
        return

    cache = {} if args.no_cache else load_cache(args.cache)
    client = get_client()

    if not args.append:
        reset_jsonl(args.output)

    total_written = 0
    for position, child in enumerate(selected, start=1):
        child_id = str(child.get("child_id"))
        if child_id in cache:
            logger.info("[%s/%s] Using cached generation for %s.", position, len(selected), child_id)
            cached_records = cache[child_id].get("records") or []
            total_written += write_jsonl(args.output, cached_records, append=True)
            continue

        logger.info("[%s/%s] Generating benchmark records for %s.", position, len(selected), child_id)
        item = process_child(
            client,
            child,
            model=args.model,
            max_facts=args.max_facts,
            queries_per_chunk=args.queries_per_chunk,
            request_delay=args.request_delay,
            max_retries=args.max_retries,
        )
        if not args.no_cache:
            append_cache(args.cache, item)
        total_written += write_jsonl(args.output, item.get("records") or [], append=True)

    logger.info("Wrote %s benchmark records to %s.", total_written, args.output)


if __name__ == "__main__":
    main()
