"""LLM-backed query parsing for metadata-aware retrieval."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger("travel_agent_query_parser")


CITY_ALIASES = {
    "da nang": "Da Nang",
    "danang": "Da Nang",
    "đa nang": "Da Nang",
    "đà nẵng": "Da Nang",
    "nha trang": "Nha Trang",
    "ho chi minh city": "Ho Chi Minh City",
    "hcmc": "Ho Chi Minh City",
    "saigon": "Ho Chi Minh City",
    "sai gon": "Ho Chi Minh City",
    "sài gòn": "Ho Chi Minh City",
    "ha noi": "Ha Noi",
    "hanoi": "Ha Noi",
    "hà nội": "Ha Noi",
    "hue": "Hue",
    "huế": "Hue",
    "hoi an": "Hoi An",
    "hội an": "Hoi An",
    "phong nha": "Phong Nha",
    "phu quoc": "Phu Quoc",
    "phú quốc": "Phu Quoc",
    "can tho": "Can Tho",
    "cần thơ": "Can Tho",
    "ha long": "Ha Long",
    "hạ long": "Ha Long",
    "sapa": "Sa Pa",
    "sa pa": "Sa Pa",
}

REGION_ALIASES = {
    "central vietnam": "Central Vietnam",
    "mien trung": "Central Vietnam",
    "miền trung": "Central Vietnam",
    "north vietnam": "Northern Vietnam",
    "northern vietnam": "Northern Vietnam",
    "mien bac": "Northern Vietnam",
    "miền bắc": "Northern Vietnam",
    "south vietnam": "Southern Vietnam",
    "southern vietnam": "Southern Vietnam",
    "mien nam": "Southern Vietnam",
    "miền nam": "Southern Vietnam",
}

CITY_ALIASES.update(
    {
        # Corpus-backed canonical locations from data/processed/children_chunks_enriched.json.
        "an giang": "An Giang",
        "angiang": "An Giang",
        "ba be": "Ba Be",
        "ba be lake": "Ba Be",
        "babe": "Ba Be",
        "ben tre": "Ben Tre",
        "bentre": "Ben Tre",
        "buon ma thuot": "Buon Ma Thuot",
        "buonmathuot": "Buon Ma Thuot",
        "bmt": "Buon Ma Thuot",
        "chau doc": "Chau Doc",
        "chaudoc": "Chau Doc",
        "dak lak": "Dak Lak",
        "daklak": "Dak Lak",
        "dong hoi": "Dong Hoi",
        "donghoi": "Dong Hoi",
        "dong thap": "Dong Thap",
        "dongthap": "Dong Thap",
        "gia lai": "Gia Lai",
        "gialai": "Gia Lai",
        "hai phong": "Hai Phong",
        "haiphong": "Hai Phong",
        "do son": "Hai Phong",
        "doson": "Hai Phong",
        "kon tum": "Kon Tum",
        "kontum": "Kon Tum",
        "lam dong": "Lam Dong",
        "lamdong": "Lam Dong",
        "lao cai": "Lao Cai",
        "laocai": "Lao Cai",
        "mai chau": "Mai Chau",
        "maichau": "Mai Chau",
        "my tho": "My Tho",
        "mytho": "My Tho",
        "nghe an": "Nghe An",
        "nghean": "Nghe An",
        "phan thiet": "Phan Thiet",
        "phanthiet": "Phan Thiet",
        "pleiku": "Pleiku",
        "pu luong": "Pu Luong",
        "puluong": "Pu Luong",
        "quang nam": "Quang Nam",
        "quangnam": "Quang Nam",
        "quang ninh": "Quang Ninh",
        "quangninh": "Quang Ninh",
        "quang tri": "Quang Tri",
        "quangtri": "Quang Tri",
        "tay ninh": "Tay Ninh",
        "tayninh": "Tay Ninh",
        "thanh hoa": "Thanh Hoa",
        "thanhhoa": "Thanh Hoa",
        "hcm": "Ho Chi Minh City",
        "ha long bay": "Halong Bay",
        "halong": "Halong Bay",
        "halong bay": "Halong Bay",
        "vinh ha long": "Halong Bay",
        "sapa": "Sapa",
        "sa pa": "Sapa",
        "ninh binh": "Ninh Binh",
        "da lat": "Da Lat",
        "dalat": "Da Lat",
        "mekong delta": "Mekong Delta",
        "mekong river delta": "Mekong Delta",
        "dong bang song cuu long": "Mekong Delta",
        "cuu long": "Mekong Delta",
        "cam ranh": "Cam Ranh",
        "cam ranh bay": "Cam Ranh",
        "khanh hoa": "Khanh Hoa",
        "mui ne": "Mui Ne",
        "vung tau": "Vung Tau",
        "cat ba": "Cat Ba",
        "con dao": "Con Dao",
        "my son": "My Son",
        "myson": "My Son",
        "cao bang": "Cao Bang",
        "caobang": "Cao Bang",
        "ha giang": "Ha Giang",
        "hagiang": "Ha Giang",
        "quang binh": "Quang Binh",
        "quangbinh": "Quang Binh",
    }
)

REGION_ALIASES.update(
    {
        "central highlands": "Central Highlands",
        "tay nguyen": "Central Highlands",
    }
)

CATEGORY_KEYWORDS = {
    "nightlife": ["nightlife", "bar", "club", "rooftop", "pub", "night market"],
    "experience": ["experience", "things to do", "activity", "activities", "trai nghiem", "choi gi"],
    "food": ["food", "cuisine", "restaurant", "eat", "dish", "mon an", "an gi", "am thuc"],
    "beach": ["beach", "bien"],
    "accommodation": ["hotel", "resort", "homestay", "stay", "accommodation", "o dau", "khach san"],
    "destination": ["destination", "place", "visit", "attraction", "dia diem", "tham quan"],
    "culture": ["culture", "heritage", "temple", "museum", "van hoa", "di san"],
    "nature": ["nature", "park", "mountain", "cave", "waterfall", "thien nhien", "hang"],
    "transport": ["transport", "bus", "train", "flight", "transfer", "di chuyen"],
    "shopping": ["shopping", "market", "shop", "mua sam", "cho"],
    "wellness": ["spa", "wellness", "massage", "yoga"],
}

ENTITY_KEYWORDS = {
    "bar": ["bar", "rooftop", "pub", "club"],
    "hotel": ["hotel", "resort", "homestay", "khach san"],
    "restaurant": ["restaurant", "eatery", "quan an", "nha hang"],
    "beach": ["beach", "bien"],
    "museum": ["museum", "bao tang"],
    "market": ["market", "cho"],
    "tour": ["tour"],
    "attraction": ["attraction", "sight", "place", "dia diem"],
    "temple": ["temple", "pagoda", "chua", "den"],
}

CONTENT_TYPE_KEYWORDS = {
    "travel_guide": ["travel guide", "guide", "cam nang", "huong dan"],
    "policy": ["policy", "chinh sach", "quy dinh"],
    "faq": ["faq", "frequently asked", "hoi dap"],
    "itinerary": ["itinerary", "plan", "lich trinh", "hanh trinh"],
    "review": ["review", "danh gia"],
}

TOPIC_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "can",
    "for",
    "from",
    "in",
    "is",
    "of",
    "the",
    "to",
    "what",
    "where",
    "which",
}

LOCATION_FUZZY_THRESHOLD = 0.86
SHORT_LOCATION_FUZZY_THRESHOLD = 0.93


@dataclass
class ParsedQuery:
    """Structured query metadata extracted from a user message."""

    raw_query: str
    language: Optional[str] = None
    raw_location_mentions: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    expanded_locations: List[str] = field(default_factory=list)
    regions: List[str] = field(default_factory=list)
    category: List[str] = field(default_factory=list)
    topic: Optional[str] = None
    entity_type: List[str] = field(default_factory=list)
    content_type: Optional[str] = None
    content_type_required: bool = False
    location_match_type: Optional[str] = None
    location_match_score: float = 0.0
    confidence: float = 0.0
    parser: str = "disabled"

    @property
    def has_city_location(self) -> bool:
        """Cho biết query có địa điểm dạng city/location hay không."""
        return bool(self.locations)

    @property
    def has_region_location(self) -> bool:
        """Cho biết query có vùng du lịch như Central/Northern/Southern Vietnam hay không."""
        return bool(self.regions)

    def to_dict(self) -> Dict[str, Any]:
        """Chuyển ParsedQuery thành dict để log/debug hoặc trả về API."""
        return asdict(self)


def _strip_accents(value: str) -> str:
    """Bỏ dấu tiếng Việt và vá một số ký tự bị lỗi mã hóa phổ biến."""
    value = value.replace("Đ", "D").replace("đ", "d")
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _normalize_text(value: Any) -> str:
    """Chuẩn hóa text thô: ép về chuỗi, trim và gộp nhiều khoảng trắng."""
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _norm_key(value: Any) -> str:
    """Tạo khóa so khớp ổn định: lowercase, bỏ dấu và bỏ ký tự đặc biệt."""
    text = _strip_accents(_normalize_text(value).lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _as_list(value: Any) -> List[str]:
    """Ép các kiểu input khác nhau từ LLM về list string sạch."""
    if value in (None, ""):
        return []
    if isinstance(value, str):
        if not value.strip():
            return []
        if "," in value:
            return [_normalize_text(item) for item in value.split(",") if _normalize_text(item)]
        return [_normalize_text(value)]
    if isinstance(value, (list, tuple, set)):
        return [_normalize_text(item) for item in value if _normalize_text(item)]
    return [_normalize_text(value)]


def _unique(values: List[str]) -> List[str]:
    """Loại trùng theo khóa đã normalize nhưng vẫn giữ thứ tự và text gốc."""
    seen = set()
    unique_values = []
    for value in values:
        key = _norm_key(value)
        if key and key not in seen:
            seen.add(key)
            unique_values.append(value)
    return unique_values


def _normalize_cities(values: Any) -> List[str]:
    """Chuẩn hóa danh sách địa điểm về tên canonical bằng CITY_ALIASES."""
    normalized = []
    for value in _as_list(values):
        key = _norm_key(value)
        normalized.append(CITY_ALIASES.get(key, value))
    return _unique(normalized)


def _normalize_regions(values: Any) -> List[str]:
    """Chuẩn hóa danh sách vùng về tên canonical bằng REGION_ALIASES."""
    normalized = []
    for value in _as_list(values):
        key = _norm_key(value)
        normalized.append(REGION_ALIASES.get(key, value))
    return _unique(normalized)


def _contains_phrase(text_key: str, phrase_key: str) -> bool:
    """Kiểm tra một phrase có xuất hiện như một cụm riêng trong text hay không."""
    if not phrase_key:
        return False
    return f" {phrase_key} " in f" {text_key} "


def _explicit_aliases(canonical_value: str, alias_map: Dict[str, str]) -> List[str]:
    """Lấy các alias có thể chứng minh một giá trị canonical được nhắc trong query."""
    canonical_key = _norm_key(canonical_value)
    aliases = {canonical_key}
    for alias, target in alias_map.items():
        if _norm_key(target) == canonical_key:
            aliases.add(_norm_key(alias))
    return [alias for alias in aliases if alias]


def _compact_key(value: str) -> str:
    """Tao key khong co khoang trang de bat cac bien the viet lien nhu danang."""
    return re.sub(r"\s+", "", _norm_key(value))


def _squash_repeated_chars(value: str) -> str:
    """Nen cac ky tu lap lien tiep de bat typo nhu daaanang -> danang."""
    return re.sub(r"(.)\1+", r"\1", value)


def _similarity(left: str, right: str) -> float:
    """Tinh do giong nhau giua hai chuoi da normalize trong khoang 0..1."""
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _location_fuzzy_threshold(alias_key: str, mention_key: str) -> float:
    """Dat nguong cao hon cho dia danh ngan de giam match nham."""
    shortest = min(len(_compact_key(alias_key)), len(_compact_key(mention_key)))
    return SHORT_LOCATION_FUZZY_THRESHOLD if shortest <= 4 else LOCATION_FUZZY_THRESHOLD


def _best_location_alias_match(raw_mention: str, canonical_location: str) -> Dict[str, Any]:
    """So raw mention voi cac alias cua canonical location bang exact/fuzzy matching."""
    mention_key = _norm_key(raw_mention)
    mention_compact = _compact_key(raw_mention)
    mention_squashed = _squash_repeated_chars(mention_compact)
    best = {"match_type": None, "score": 0.0, "alias": None}

    for alias in _explicit_aliases(canonical_location, CITY_ALIASES):
        alias_key = _norm_key(alias)
        alias_compact = _compact_key(alias)
        alias_squashed = _squash_repeated_chars(alias_compact)
        if mention_key == alias_key or mention_compact == alias_compact:
            return {"match_type": "exact", "score": 1.0, "alias": alias}
        if mention_squashed == alias_compact or mention_squashed == alias_squashed:
            return {"match_type": "fuzzy", "score": 0.95, "alias": alias}

        score = max(
            _similarity(mention_key, alias_key),
            _similarity(mention_compact, alias_compact),
            _similarity(mention_squashed, alias_compact),
        )
        if score > float(best["score"]):
            best = {"match_type": "fuzzy", "score": score, "alias": alias}

    threshold = _location_fuzzy_threshold(str(best.get("alias") or ""), raw_mention)
    if float(best["score"]) >= threshold:
        return best
    return {"match_type": None, "score": float(best["score"]), "alias": best.get("alias")}


def _validate_locations_with_mentions(
    raw_query: str,
    raw_mentions: List[str],
    canonical_locations: List[str],
) -> Dict[str, Any]:
    """Validate location bang raw mention cua LLM; fallback ve exact query guard khi thieu mention."""
    accepted = []
    match_types = []
    best_score = 0.0
    mentions = _unique(raw_mentions)

    for location in canonical_locations:
        location_best = {"match_type": None, "score": 0.0, "alias": None}

        for mention in mentions:
            match = _best_location_alias_match(mention, location)
            if float(match["score"]) > float(location_best["score"]):
                location_best = match

        if location_best["match_type"] is None and not mentions:
            query_key = _norm_key(raw_query)
            if any(_contains_phrase(query_key, alias) for alias in _explicit_aliases(location, CITY_ALIASES)):
                location_best = {"match_type": "exact", "score": 1.0, "alias": location}

        if location_best["match_type"]:
            accepted.append(location)
            match_types.append(str(location_best["match_type"]))
            best_score = max(best_score, float(location_best["score"]))

    match_type = None
    if match_types:
        match_type = "exact" if all(item == "exact" for item in match_types) else "fuzzy"

    return {
        "locations": _unique(accepted),
        "raw_location_mentions": mentions,
        "location_match_type": match_type,
        "location_match_score": round(best_score, 6),
    }


def _keep_explicit_metadata_values(raw_query: str, values: List[str], alias_map: Dict[str, str]) -> List[str]:
    """Chỉ giữ metadata value nếu query có nhắc trực tiếp value đó hoặc alias của nó."""
    query_key = _norm_key(raw_query)
    explicit_values = []
    for value in values:
        if any(_contains_phrase(query_key, alias) for alias in _explicit_aliases(value, alias_map)):
            explicit_values.append(value)
    return _unique(explicit_values)


def _keep_keyword_backed_values(raw_query: str, values: List[str], keyword_map: Dict[str, List[str]]) -> List[str]:
    """Chỉ giữ category/entity_type nếu query có keyword hỗ trợ rõ ràng."""
    query_key = _norm_key(raw_query)
    explicit_values = []
    for value in values:
        value_key = _norm_key(value)
        keywords = keyword_map.get(value_key, [value_key])
        if any(_contains_phrase(query_key, _norm_key(keyword)) for keyword in keywords):
            explicit_values.append(value_key)
    return _unique(explicit_values)


def _content_type_is_explicit(raw_query: str, content_type: Optional[str]) -> bool:
    """Kiểm tra user có thật sự yêu cầu loại nội dung như guide, FAQ hoặc itinerary không."""
    if not content_type:
        return False
    query_key = _norm_key(raw_query)
    keywords = CONTENT_TYPE_KEYWORDS.get(_norm_key(content_type), [_norm_key(content_type)])
    return any(_contains_phrase(query_key, _norm_key(keyword)) for keyword in keywords)


def _supported_topic(raw_query: str, topic: Optional[str]) -> Optional[str]:
    """Giữ topic do LLM trả về chỉ khi topic có đủ token trùng với query gốc."""
    normalized_topic = _normalize_text(topic)
    if not normalized_topic:
        return None

    query_tokens = set(_norm_key(raw_query).split())
    topic_tokens = {
        token
        for token in _norm_key(normalized_topic).split()
        if token not in TOPIC_STOPWORDS and len(token) > 2
    }
    if not topic_tokens:
        return None
    overlap = len(topic_tokens & query_tokens) / len(topic_tokens)
    return normalized_topic if overlap >= 0.5 else None


def _normalize_language(value: Any) -> Optional[str]:
    """Chuẩn hóa language filter về mã ngắn như vi/en, hoặc None nếu không có."""
    language = _norm_key(value)
    if not language:
        return None
    if language in {"vietnamese", "tieng viet", "vi"}:
        return "vi"
    if language in {"english", "en"}:
        return "en"
    return language[:8]


def normalize_parsed_query(raw_query: str, payload: Dict[str, Any], parser: str = "qwen_vllm") -> ParsedQuery:
    """Chuẩn hóa JSON lỏng từ LLM về ParsedQuery để retrieval dùng an toàn."""
    hard_filters = payload.get("hard_filters") if isinstance(payload.get("hard_filters"), dict) else {}
    soft_signals = payload.get("soft_signals") if isinstance(payload.get("soft_signals"), dict) else {}
    location_payload = payload.get("location_intent") if isinstance(payload.get("location_intent"), dict) else {}
    locations = hard_filters.get("locations", payload.get("locations", location_payload.get("cities")))
    raw_location_mentions = hard_filters.get(
        "raw_location_mentions",
        payload.get(
            "raw_location_mentions",
            location_payload.get("raw_mentions", location_payload.get("mentions")),
        ),
    )
    expanded_locations = hard_filters.get(
        "expanded_locations",
        hard_filters.get("nearby_locations", payload.get("expanded_locations")),
    )
    regions = hard_filters.get("regions", payload.get("regions", location_payload.get("regions")))

    normalized_content_type = _normalize_text(hard_filters.get("content_type", payload.get("content_type"))) or None
    content_type_required = bool(
        hard_filters.get("content_type_required")
        or payload.get("content_type_required")
        or payload.get("requires_content_type")
        or payload.get("content_type_filter_required")
    ) and _content_type_is_explicit(raw_query, normalized_content_type)
    location_validation = _validate_locations_with_mentions(
        raw_query,
        _as_list(raw_location_mentions),
        _normalize_cities(locations),
    )
    normalized_locations = location_validation["locations"]
    normalized_expanded_locations = _unique(
        normalized_locations
        + _validate_locations_with_mentions(
            raw_query,
            _as_list(raw_location_mentions),
            _normalize_cities(expanded_locations),
        )["locations"]
    )
    normalized_regions = _keep_explicit_metadata_values(
        raw_query,
        _normalize_regions(regions),
        REGION_ALIASES,
    )
    normalized_category = _keep_keyword_backed_values(
        raw_query,
        _unique([item.lower() for item in _as_list(soft_signals.get("category", payload.get("category")))]),
        CATEGORY_KEYWORDS,
    )
    normalized_entity_type = _keep_keyword_backed_values(
        raw_query,
        _unique([item.lower() for item in _as_list(soft_signals.get("entity_type", payload.get("entity_type")))]),
        ENTITY_KEYWORDS,
    )

    confidence = payload.get("confidence", 0.0)
    try:
        confidence_value = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence_value = 0.0
    if normalized_locations and location_validation["location_match_type"] == "fuzzy":
        confidence_value = max(confidence_value, float(location_validation["location_match_score"]))

    return ParsedQuery(
        raw_query=raw_query,
        language=_normalize_language(hard_filters.get("language", payload.get("language"))),
        raw_location_mentions=location_validation["raw_location_mentions"],
        locations=normalized_locations,
        expanded_locations=normalized_expanded_locations,
        regions=normalized_regions,
        category=normalized_category,
        topic=_supported_topic(raw_query, soft_signals.get("topic", payload.get("topic"))),
        entity_type=normalized_entity_type,
        content_type=normalized_content_type if content_type_required else None,
        content_type_required=content_type_required,
        location_match_type=location_validation["location_match_type"],
        location_match_score=float(location_validation["location_match_score"]),
        confidence=confidence_value,
        parser=parser,
    )


def extract_json_object(text: str) -> Dict[str, Any]:
    """Trích JSON object đầu tiên từ response của model."""
    content = str(text or "").strip()
    if not content:
        return {}
    try:
        value = json.loads(content)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(content[start : end + 1])
    return {}


class QwenQueryParser:
    """Parse user travel queries with a Qwen instruct model served by vLLM."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30,
        client: Optional[OpenAI] = None,
    ) -> None:
        """Khởi tạo OpenAI-compatible client để gọi Qwen đang serve qua vLLM."""
        self.model = model
        self.client = client or OpenAI(
            base_url=base_url,
            api_key=api_key or "EMPTY",
            timeout=timeout_seconds,
        )

    @staticmethod
    def system_prompt() -> str:
        """Tạo system prompt buộc LLM parse query thành JSON theo schema retrieval."""
        return (
            "You parse user queries for a Vietnam travel RAG system. "
            "Return only valid JSON. Extract retrieval metadata and search signals, not the final answer. "
            "Be conservative with HARD constraints. "
            "Only place a value in hard_filters when the user explicitly states it and the value must be satisfied. "
            "Hard filters exclude documents, so prefer leaving them empty when uncertain. "
            "Use soft_signals for semantic hints that may improve ranking but must not exclude documents. "
            "The language field is the requested document/content language, not the "
            "language of the user's message. Use null when the user does not explicitly "
            "ask for Vietnamese or English source content. "
            "Extract raw_location_mentions as the exact location-like text spans written by the user, "
            "including typos or misspellings such as daaanang. "
            "Extract locations as your best canonical location inference for those raw mentions. "
            "Do not infer Vietnam, cities, or regions from context. "
            "Use canonical English location names, for example Da Nang, Nha Trang, "
            "Ho Chi Minh City, Ha Noi, Hue, Hoi An, Phu Quoc, Ninh Binh, Halong Bay. "
            "If multiple location mentions appear, include all raw mentions and all canonical locations. "
            "Do not expand locations to nearby hubs, provinces, or parent destinations. "
            "Leave expanded_locations empty unless the query explicitly mentions multiple location labels "
            "for the same travel scope. "
            "Use regions like Central Vietnam, Northern Vietnam, Southern Vietnam. "
            "Category, topic, and entity_type are soft retrieval signals only. "
            "Do not invent them when unsupported by the query. "
            "If uncertain, return empty arrays or null. "
            "Set content_type_required=true only when the user explicitly asks for a "
            "specific document/content type such as travel guide, policy, FAQ, itinerary, or review. "
            "If content_type_required=false, set content_type=null. "
            "Schema: {"
            "\"hard_filters\":{"
            "\"language\":\"vi|en|null\","
            "\"raw_location_mentions\":[\"exact_user_location_text\"],"
            "\"locations\":[\"city\"],"
            "\"expanded_locations\":[\"city_or_nearby_scope\"],"
            "\"regions\":[\"region\"],"
            "\"content_type\":\"travel_guide|policy|faq|itinerary|review|null\","
            "\"content_type_required\":false"
            "},"
            "\"soft_signals\":{"
            "\"category\":[\"nightlife|experience|food|beach|accommodation|destination|culture|nature|transport|shopping|wellness\"],"
            "\"topic\":\"short topic or null\","
            "\"entity_type\":[\"bar|hotel|restaurant|beach|museum|market|tour|attraction|temple\"]"
            "},"
            "\"confidence\":0.0"
            "}."
        )

    def parse(self, query: str) -> ParsedQuery:
        """Gọi LLM để parse query, rồi normalize và validate kết quả trước khi trả về."""
        query_text = query.strip()
        if not query_text:
            raise ValueError("Query cannot be empty.")

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt()},
                {"role": "user", "content": query_text},
            ],
            temperature=0,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content or "{}"
        try:
            payload = extract_json_object(content)
        except json.JSONDecodeError as err:
            logger.warning("Qwen query parser returned invalid JSON: %s", err)
            payload = {}
        return normalize_parsed_query(query_text, payload, parser=f"qwen_vllm:{self.model}")
