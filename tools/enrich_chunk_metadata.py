"""Enrich parent and child chunk metadata with locations, categories, and topics."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DEFAULT_PARENT_INPUT = ROOT_DIR / "data" / "processed" / "parent_chunks_full.json"
DEFAULT_CHILD_INPUT = ROOT_DIR / "data" / "processed" / "children_chunks_full.json"
DEFAULT_PARENT_OUTPUT = ROOT_DIR / "data" / "processed" / "parent_chunks_enriched.json"
DEFAULT_CHILD_OUTPUT = ROOT_DIR / "data" / "processed" / "children_chunks_enriched.json"

ENRICHER_VERSION = "metadata_enricher_v1"

REGION_BY_LOCATION = {
    "Ha Noi": "Northern Vietnam",
    "Hanoi": "Northern Vietnam",
    "Ninh Binh": "Northern Vietnam",
    "Ha Long": "Northern Vietnam",
    "Halong Bay": "Northern Vietnam",
    "Quang Ninh": "Northern Vietnam",
    "Sapa": "Northern Vietnam",
    "Sa Pa": "Northern Vietnam",
    "Lao Cai": "Northern Vietnam",
    "Ha Giang": "Northern Vietnam",
    "Mai Chau": "Northern Vietnam",
    "Pu Luong": "Northern Vietnam",
    "Cao Bang": "Northern Vietnam",
    "Ba Be": "Northern Vietnam",
    "Hai Phong": "Northern Vietnam",
    "Cat Ba": "Northern Vietnam",
    "Thanh Hoa": "Northern Vietnam",
    "Nghe An": "Northern Vietnam",
    "Hue": "Central Vietnam",
    "Da Nang": "Central Vietnam",
    "Danang": "Central Vietnam",
    "Hoi An": "Central Vietnam",
    "Quang Nam": "Central Vietnam",
    "My Son": "Central Vietnam",
    "Quang Binh": "Central Vietnam",
    "Phong Nha": "Central Vietnam",
    "Dong Hoi": "Central Vietnam",
    "Quang Tri": "Central Vietnam",
    "Nha Trang": "Central Vietnam",
    "Khanh Hoa": "Central Vietnam",
    "Da Lat": "Central Highlands",
    "Dalat": "Central Highlands",
    "Lam Dong": "Central Highlands",
    "Buon Ma Thuot": "Central Highlands",
    "Dak Lak": "Central Highlands",
    "Kon Tum": "Central Highlands",
    "Pleiku": "Central Highlands",
    "Gia Lai": "Central Highlands",
    "Ho Chi Minh City": "Southern Vietnam",
    "Saigon": "Southern Vietnam",
    "Can Tho": "Southern Vietnam",
    "Mekong Delta": "Southern Vietnam",
    "Phu Quoc": "Southern Vietnam",
    "Con Dao": "Southern Vietnam",
    "Vung Tau": "Southern Vietnam",
    "Mui Ne": "Southern Vietnam",
    "Phan Thiet": "Southern Vietnam",
    "Tay Ninh": "Southern Vietnam",
    "Ben Tre": "Southern Vietnam",
    "My Tho": "Southern Vietnam",
    "Chau Doc": "Southern Vietnam",
    "An Giang": "Southern Vietnam",
    "Dong Thap": "Southern Vietnam",
}

LOCATION_ALIASES = {
    "Ha Noi": ["Ha Noi", "Hanoi", "Hà Nội"],
    "Ninh Binh": ["Ninh Binh", "Ninh Bình"],
    "Ha Long": ["Ha Long", "Hạ Long"],
    "Halong Bay": ["Halong Bay", "Ha Long Bay", "Hạ Long Bay"],
    "Quang Ninh": ["Quang Ninh", "Quảng Ninh"],
    "Sapa": ["Sapa", "Sa Pa"],
    "Lao Cai": ["Lao Cai", "Lào Cai"],
    "Ha Giang": ["Ha Giang", "Hà Giang"],
    "Mai Chau": ["Mai Chau", "Mai Châu"],
    "Pu Luong": ["Pu Luong", "Pù Luông"],
    "Cao Bang": ["Cao Bang", "Cao Bằng"],
    "Ba Be": ["Ba Be", "Ba Bể"],
    "Hai Phong": ["Hai Phong", "Hải Phòng"],
    "Cat Ba": ["Cat Ba", "Cát Bà"],
    "Thanh Hoa": ["Thanh Hoa", "Thanh Hóa"],
    "Nghe An": ["Nghe An", "Nghệ An"],
    "Hue": ["Hue", "Huế", "Thua Thien Hue", "Thừa Thiên Huế"],
    "Da Nang": ["Da Nang", "Danang", "Đà Nẵng"],
    "Hoi An": ["Hoi An", "Hội An"],
    "Quang Nam": ["Quang Nam", "Quảng Nam"],
    "My Son": ["My Son", "Mỹ Sơn"],
    "Quang Binh": ["Quang Binh", "Quảng Bình"],
    "Phong Nha": ["Phong Nha", "Phong Nha-Ke Bang", "Phong Nha Kẻ Bàng"],
    "Dong Hoi": ["Dong Hoi", "Đồng Hới"],
    "Quang Tri": ["Quang Tri", "Quảng Trị"],
    "Nha Trang": ["Nha Trang"],
    "Khanh Hoa": ["Khanh Hoa", "Khánh Hòa"],
    "Da Lat": ["Da Lat", "Dalat", "Đà Lạt"],
    "Lam Dong": ["Lam Dong", "Lâm Đồng"],
    "Buon Ma Thuot": ["Buon Ma Thuot", "Buôn Ma Thuột"],
    "Dak Lak": ["Dak Lak", "Đắk Lắk"],
    "Kon Tum": ["Kon Tum"],
    "Pleiku": ["Pleiku", "Plei Ku"],
    "Gia Lai": ["Gia Lai"],
    "Ho Chi Minh City": ["Ho Chi Minh City", "HCMC", "Ho Chi Minh", "Hồ Chí Minh"],
    "Saigon": ["Saigon", "Sài Gòn"],
    "Can Tho": ["Can Tho", "Cần Thơ"],
    "Mekong Delta": ["Mekong Delta", "Mekong", "Đồng bằng sông Cửu Long"],
    "Phu Quoc": ["Phu Quoc", "Phú Quốc"],
    "Con Dao": ["Con Dao", "Côn Đảo"],
    "Vung Tau": ["Vung Tau", "Vũng Tàu"],
    "Mui Ne": ["Mui Ne", "Mũi Né"],
    "Phan Thiet": ["Phan Thiet", "Phan Thiết"],
    "Tay Ninh": ["Tay Ninh", "Tây Ninh"],
    "Ben Tre": ["Ben Tre", "Bến Tre"],
    "My Tho": ["My Tho", "Mỹ Tho"],
    "Chau Doc": ["Chau Doc", "Châu Đốc"],
    "An Giang": ["An Giang"],
    "Dong Thap": ["Dong Thap", "Đồng Tháp"],
}

CATEGORY_KEYWORDS = {
    "food": [
        "food", "dish", "dishes", "cuisine", "restaurant", "street food", "coffee",
        "pho", "phở", "banh mi", "bánh mì", "bun bo", "bún bò", "cao lau", "cơm",
        "seafood", "beer", "wine", "eat", "dining", "meal", "market food",
    ],
    "culture": [
        "culture", "cultural", "heritage", "history", "historic", "museum", "temple",
        "pagoda", "citadel", "imperial", "old town", "traditional", "craft", "village",
        "unesco", "architecture", "art", "gallery",
    ],
    "nature": [
        "nature", "mountain", "cave", "forest", "park", "waterfall", "lake", "river",
        "bay", "island", "national park", "countryside", "landscape", "trek", "hike",
    ],
    "beach": ["beach", "coast", "coastal", "sand", "sea", "ocean", "snorkel", "dive"],
    "nightlife": [
        "nightlife", "bar", "rooftop", "skybar", "cocktail", "club", "party",
        "after-dinner", "sundowner", "drink", "happy hour",
    ],
    "itinerary": [
        "itinerary", "day 1", "day 2", "day 3", "arrival", "departure", "route",
        "trip", "travel plan", "recommended trip", "days", "weekend",
    ],
    "shopping": [
        "shopping", "market", "souvenir", "collectible", "buy", "shop", "boutique",
        "night market", "tailor",
    ],
    "wellness": ["spa", "wellness", "massage", "relax", "yoga", "retreat", "hot spring"],
    "adventure": [
        "adventure", "motorbike", "cycling", "kayak", "zipline", "rafting", "climb",
        "trekking", "diving", "surfing",
    ],
    "family": ["family", "families", "kids", "children", "child-friendly"],
    "festival": ["festival", "event", "celebration", "lunar", "tet", "fireworks"],
    "transportation": ["transport", "flight", "train", "bus", "taxi", "airport", "transfer"],
    "accommodation": ["hotel", "resort", "homestay", "stay", "villa", "hostel"],
    "destination": ["destination", "city", "province", "places to go", "where to go"],
    "news": ["news", "tourism promotion", "campaign", "announcement", "2025"],
}

ENTITY_HINTS = {
    "food": "dish",
    "nightlife": "bar",
    "culture": "attraction",
    "nature": "natural_attraction",
    "beach": "beach",
    "shopping": "market",
    "itinerary": "itinerary",
    "festival": "event",
    "accommodation": "hotel",
    "transportation": "transportation",
    "destination": "destination",
}

GENERIC_TOPICS = {
    "overview",
    "introduction",
    "day 1",
    "day 2",
    "day 3",
    "day 4",
    "day 5",
    "day 6",
    "day 7",
    "day 8",
    "day 9",
    "day 10",
    "day 11",
    "day 12",
    "day 13",
    "day 14",
}


def strip_accents(value: str) -> str:
    """Return a lowercase ASCII-ish text for fuzzy matching."""
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return text.lower()


def normalized_text(value: Any) -> str:
    """Normalize whitespace without dropping accents."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalized_match_text(value: Any) -> str:
    """Normalize text for regex-like token matching."""
    text = strip_accents(normalized_text(value))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    compact_text = re.sub(r"\s+", " ", text).strip()
    return f" {compact_text} "


def slug_text(url: str) -> str:
    """Convert URL path into searchable text."""
    path = re.sub(r"https?://[^/]+", "", str(url or ""))
    return path.replace("-", " ").replace("/", " ")


def ordered_unique(values: list[str]) -> list[str]:
    """Deduplicate strings while preserving order."""
    seen = set()
    result = []
    for value in values:
        item = normalized_text(value)
        key = strip_accents(item)
        if not item or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def has_phrase(text: str, phrase: str) -> bool:
    """Return true when phrase appears as token-aware normalized text."""
    key = normalized_match_text(phrase).strip()
    return bool(key and f" {key} " in text)


def score_locations(fields: list[tuple[str, str, int]]) -> Counter[str]:
    """Score locations from weighted text fields."""
    scores: Counter[str] = Counter()
    for _, value, weight in fields:
        haystack = normalized_match_text(value)
        if not haystack.strip():
            continue
        for canonical, aliases in LOCATION_ALIASES.items():
            for alias in aliases:
                if has_phrase(haystack, alias):
                    scores[canonical] += weight + min(len(alias.split()), 3)
                    break
    return scores


def score_categories(url: str, fields: list[tuple[str, str, int]]) -> Counter[str]:
    """Score categories from URL and weighted text fields."""
    scores: Counter[str] = Counter()
    url_lower = str(url or "").lower()
    if "things-to-do" in url_lower:
        scores["experience"] += 3
    if "places-to-go" in url_lower:
        scores["destination"] += 8
    if "plan-your-trip" in url_lower or "recommended-trip" in url_lower:
        scores["itinerary"] += 8
    if "2025.vietnam.travel" in url_lower:
        scores["news"] += 8

    for _, value, weight in fields:
        haystack = normalized_match_text(value)
        if not haystack.strip():
            continue
        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if has_phrase(haystack, keyword):
                    scores[category] += weight
    return scores


def top_scored(counter: Counter[str], min_score: int = 1, limit: int | None = None) -> list[str]:
    """Return ordered labels from score counter."""
    labels = [label for label, score in counter.most_common() if score >= min_score]
    return labels[:limit] if limit else labels


def choose_primary_location(
    scores: Counter[str],
    high_confidence_scores: Counter[str] | None = None,
) -> str:
    """Choose a primary location only when confidence is strong enough."""
    if not scores:
        return ""

    high_confidence_scores = high_confidence_scores or Counter()
    high_confidence_locations = top_scored(high_confidence_scores, min_score=4)
    if high_confidence_locations:
        return high_confidence_locations[0]

    ranked = scores.most_common()
    if not ranked:
        return ""
    top_location, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if top_score >= 8 and (not second_score or top_score >= second_score * 1.6):
        return top_location
    return ""


def infer_region(locations: list[str]) -> str:
    """Infer region when known locations point to a single region."""
    regions = []
    for location in locations:
        region = REGION_BY_LOCATION.get(location)
        if region:
            regions.append(region)
    regions = ordered_unique(regions)
    return regions[0] if len(regions) == 1 else ""


def select_categories(counter: Counter[str], existing: list[str] | None = None, limit: int = 4) -> list[str]:
    """Select strong categories while preserving useful existing labels."""
    existing = [str(item) for item in (existing or []) if str(item).strip()]
    ranked = counter.most_common()
    if not ranked:
        return ordered_unique(existing)[:limit]
    top_score = ranked[0][1]
    min_score = max(2, int(top_score * 0.25))
    selected = [label for label, score in ranked if score >= min_score]
    return ordered_unique(selected + existing)[:limit]


def remove_weak_destination(categories: list[str], url: str) -> list[str]:
    """Keep destination only when URL route or category evidence is explicit."""
    url_lower = str(url or "").lower()
    if "places-to-go" in url_lower:
        return categories
    if "destination" in categories and len(categories) > 1:
        return [category for category in categories if category != "destination"]
    return categories


def clean_topic(heading: str, title: str, source_text: str = "") -> str:
    """Derive a compact child topic from heading/title/source."""
    topic = normalized_text(heading)
    topic = re.sub(r"^\s*best for [^:]{1,80}:\s*", "", topic, flags=re.I)
    topic = re.sub(r"^\s*(day\s+\d+)\s*[:\-–]\s*", "", topic, flags=re.I)
    topic = re.sub(r"\s*\|\s*Vietnam Tourism\s*$", "", topic, flags=re.I)

    for aliases in LOCATION_ALIASES.values():
        for alias in aliases:
            topic = re.sub(rf"\b{re.escape(alias)}\b", "", topic, flags=re.I)
    topic = re.sub(r"[,:\-–]+", " ", topic)
    topic = normalized_text(topic).lower()

    if not topic or topic in GENERIC_TOPICS or len(topic) < 3:
        title_topic = re.sub(r"\s*\|\s*Vietnam Tourism\s*$", "", normalized_text(title), flags=re.I)
        topic = title_topic.lower()

    if not topic and source_text:
        topic = normalized_text(source_text).split(".")[0].lower()

    return topic[:120].strip()


def infer_entity_types(categories: list[str], text: str) -> list[str]:
    """Infer broad entity types from categories and local keywords."""
    entity_types = []
    for category in categories:
        hint = ENTITY_HINTS.get(category)
        if hint:
            entity_types.append(hint)

    haystack = normalized_match_text(text)
    if any(has_phrase(haystack, key) for key in ["pho", "banh mi", "bun bo", "cao lau", "coffee"]):
        entity_types.append("dish")
    if any(has_phrase(haystack, key) for key in ["bar", "skybar", "rooftop"]):
        entity_types.append("bar")
    if any(has_phrase(haystack, key) for key in ["hotel", "resort"]):
        entity_types.append("hotel")
    if any(has_phrase(haystack, key) for key in ["market", "night market"]):
        entity_types.append("market")

    return ordered_unique(entity_types)


def rebuild_retrieval_text(child: dict[str, Any]) -> str:
    """Rebuild retrieval_text after metadata enrichment."""
    metadata = child.get("metadata", {})
    lines = [
        f"Article: {metadata.get('title') or ''}",
        f"Section: {child.get('heading') or ''}",
    ]
    heading_path = child.get("heading_path") or []
    if heading_path:
        lines.append(f"Heading path: {' > '.join(heading_path)}")
    if metadata.get("primary_location"):
        lines.append(f"Location: {metadata['primary_location']}")
    if metadata.get("category"):
        lines.append(f"Category: {', '.join(metadata['category'])}")
    if metadata.get("language"):
        lines.append(f"Language: {metadata['language']}")
    lines.extend(["", child.get("source_text") or ""])
    return "\n".join(lines).strip()


def enrich_child(child: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
    """Enrich one child chunk while preserving the target child schema."""
    enriched = deepcopy(child)
    metadata = enriched.setdefault("metadata", {})
    parent_meta = (parent or {}).get("metadata", {})
    title = metadata.get("title") or (parent or {}).get("clean_title") or ""
    url = metadata.get("url") or (parent or {}).get("url") or ""
    heading = enriched.get("heading") or ""
    heading_path_text = " ".join(enriched.get("heading_path") or [])
    source_text = enriched.get("source_text") or ""
    parent_summary = (parent or {}).get("context_summary") or ""

    location_fields = [
        ("heading", heading, 9),
        ("heading_path", heading_path_text, 6),
        ("title", title, 5),
        ("url", slug_text(url), 5),
        ("source_text", source_text, 2),
        ("parent_summary", parent_summary, 3),
    ]
    location_scores = score_locations(location_fields)
    high_confidence_location_scores = score_locations(location_fields[:4])
    child_locations = top_scored(location_scores, min_score=2)
    parent_locations = parent_meta.get("locations") or []
    locations = ordered_unique(child_locations + parent_locations)
    primary_location = choose_primary_location(location_scores, high_confidence_location_scores)
    if not primary_location:
        primary_location = parent_meta.get("primary_location") or ""
    region = (
        REGION_BY_LOCATION.get(primary_location)
        or infer_region([primary_location] + locations)
        or parent_meta.get("region")
        or ""
    )

    category_fields = [
        ("heading", heading, 8),
        ("heading_path", heading_path_text, 5),
        ("title", title, 4),
        ("url", slug_text(url), 5),
        ("source_text", source_text, 2),
        ("parent_summary", parent_summary, 2),
    ]
    category_scores = score_categories(url, category_fields)
    existing_categories = metadata.get("category") or parent_meta.get("categories") or []
    for category in existing_categories:
        category_scores[str(category)] += 1
    categories = select_categories(category_scores, list(existing_categories), limit=4)
    categories = remove_weak_destination(categories, url)

    local_text = " ".join([heading, heading_path_text, source_text])
    topic = clean_topic(heading, title, source_text)
    entity_types = ordered_unique(
        list(metadata.get("entity_type") or []) + infer_entity_types(categories, local_text)
    )

    metadata.update(
        {
            "title": title,
            "url": url,
            "language": metadata.get("language") or (parent or {}).get("language") or "en",
            "source_domain": metadata.get("source_domain") or (parent or {}).get("source_domain") or "vietnam.travel",
            "primary_location": primary_location,
            "locations": locations,
            "region": region,
            "category": categories,
            "topic": topic,
            "entity_type": entity_types,
            "content_type": metadata.get("content_type") or parent_meta.get("article_type") or "travel_guide",
            "word_count": metadata.get("word_count") or len(source_text.split()),
            "char_length": metadata.get("char_length") or len(source_text),
            "chunker_version": metadata.get("chunker_version") or "parent_child_v1",
            "metadata_enricher_version": ENRICHER_VERSION,
        }
    )
    metadata["metadata_quality"] = {
        "location_score": int(location_scores.get(primary_location, 0)) if primary_location else 0,
        "category_scores": dict(category_scores),
        "location_source": "child_gazetteer" if primary_location and child_locations else ("parent_inheritance" if primary_location else "missing"),
        "category_source": "url_keyword_taxonomy",
    }

    enriched["retrieval_text"] = rebuild_retrieval_text(enriched)
    return enriched


def enrich_parent(parent: dict[str, Any], child_chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Enrich one parent from its own text plus aggregated child metadata."""
    enriched = deepcopy(parent)
    metadata = enriched.setdefault("metadata", {})
    title = enriched.get("clean_title") or enriched.get("title") or ""
    url = enriched.get("url") or ""
    summary = enriched.get("context_summary") or ""
    child_locations = []
    child_categories = []
    for child in child_chunks:
        child_meta = child.get("metadata", {})
        if child_meta.get("primary_location"):
            child_locations.append(child_meta["primary_location"])
        child_categories.extend(child_meta.get("category") or [])

    parent_location_fields = [
        ("title", title, 7),
        ("url", slug_text(url), 6),
        ("summary", summary, 3),
    ]
    location_scores = score_locations(parent_location_fields)
    high_confidence_location_scores = score_locations(parent_location_fields[:2])
    for location in child_locations:
        location_scores[location] += 4
    locations = top_scored(location_scores, min_score=2)
    primary_location = choose_primary_location(location_scores, high_confidence_location_scores)
    region = REGION_BY_LOCATION.get(primary_location) or infer_region([primary_location] + locations)

    category_scores = score_categories(
        url,
        [
            ("title", title, 6),
            ("url", slug_text(url), 6),
            ("summary", summary, 3),
        ],
    )
    for category in child_categories:
        category_scores[category] += 2
    for category in metadata.get("categories") or []:
        category_scores[str(category)] += 1
    categories = select_categories(category_scores, list(metadata.get("categories") or []), limit=5)
    categories = remove_weak_destination(categories, url)

    metadata.update(
        {
            "primary_location": primary_location,
            "locations": locations,
            "region": region,
            "categories": categories,
            "article_type": metadata.get("article_type") or "travel_guide",
            "total_children": metadata.get("total_children") or len(enriched.get("child_ids") or []),
            "chunker_version": metadata.get("chunker_version") or "parent_child_v1",
            "metadata_enricher_version": ENRICHER_VERSION,
            "metadata_quality": {
                "location_score": int(location_scores.get(primary_location, 0)) if primary_location else 0,
                "category_scores": dict(category_scores),
                "location_source": "parent_and_child_gazetteer" if primary_location else "missing",
                "category_source": "url_keyword_child_aggregation",
            },
        }
    )
    return enriched


def load_json(path: Path) -> list[dict[str, Any]]:
    """Load a JSON array file."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write UTF-8 JSON array."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def enrich_files(
    parent_input: Path,
    child_input: Path,
    parent_output: Path,
    child_output: Path,
) -> dict[str, Any]:
    """Enrich parent/child chunk JSON files."""
    parents = load_json(parent_input)
    children = load_json(child_input)
    parent_by_id = {parent["parent_id"]: parent for parent in parents}

    enriched_children = [
        enrich_child(child, parent_by_id.get(child.get("parent_id")))
        for child in children
    ]
    children_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for child in enriched_children:
        children_by_parent[child.get("parent_id")].append(child)

    enriched_parents = [
        enrich_parent(parent, children_by_parent.get(parent.get("parent_id"), []))
        for parent in parents
    ]

    write_json(parent_output, enriched_parents)
    write_json(child_output, enriched_children)

    parent_with_location = sum(1 for parent in enriched_parents if parent.get("metadata", {}).get("primary_location"))
    child_with_location = sum(1 for child in enriched_children if child.get("metadata", {}).get("primary_location"))
    parent_with_category = sum(1 for parent in enriched_parents if parent.get("metadata", {}).get("categories"))
    child_with_category = sum(1 for child in enriched_children if child.get("metadata", {}).get("category"))

    return {
        "parent_input": str(parent_input),
        "child_input": str(child_input),
        "parent_output": str(parent_output),
        "child_output": str(child_output),
        "parent_count": len(enriched_parents),
        "child_count": len(enriched_children),
        "parent_with_location": parent_with_location,
        "child_with_location": child_with_location,
        "parent_with_category": parent_with_category,
        "child_with_category": child_with_category,
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(description="Enrich chunk metadata for parent-child RAG.")
    parser.add_argument("--parents", default=str(DEFAULT_PARENT_INPUT), help="Input parent chunks JSON.")
    parser.add_argument("--children", default=str(DEFAULT_CHILD_INPUT), help="Input children chunks JSON.")
    parser.add_argument("--parents-output", default=str(DEFAULT_PARENT_OUTPUT), help="Output enriched parent JSON.")
    parser.add_argument("--children-output", default=str(DEFAULT_CHILD_OUTPUT), help="Output enriched child JSON.")
    return parser.parse_args()


def main() -> int:
    """Run metadata enrichment."""
    args = parse_args()
    report = enrich_files(
        parent_input=Path(args.parents),
        child_input=Path(args.children),
        parent_output=Path(args.parents_output),
        child_output=Path(args.children_output),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
