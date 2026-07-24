"""Sinh bộ query tiếng Anh từ traveler_need_queries_500.jsonl.

Script này không dịch word-by-word. Nó rewrite query dựa trên metadata
category/location/profile/time để tạo English retrieval queries nhất quán.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


INPUT_PATH = Path("data/evaluation/traveler_need_queries_500.jsonl")
OUTPUT_PATH = Path("data/evaluation/traveler_need_queries_500_en.jsonl")


LOCATION_MAP = {
    "Huế": "Hue",
    "Phong Nha": "Phong Nha",
    "Hội An": "Hoi An",
    "Đà Lạt": "Da Lat",
    "Ninh Bình": "Ninh Binh",
    "Phú Yên": "Phu Yen",
    "Mekong Delta": "Mekong Delta",
    "Phú Quốc": "Phu Quoc",
    "Cát Bà": "Cat Ba",
    "Đà Nẵng": "Da Nang",
    "Hà Nội": "Hanoi",
    "TP. Hồ Chí Minh": "Ho Chi Minh City",
    "TP Hồ Chí Minh": "Ho Chi Minh City",
    "Hạ Long": "Ha Long",
    "Nha Trang": "Nha Trang",
    "Sa Pa": "Sa Pa",
    "Sapa": "Sa Pa",
    "Cần Thơ": "Can Tho",
}

PROFILE_MAP = {
    "đi công tác kết hợp du lịch": "for a business trip combined with leisure travel",
    "muốn tiết kiệm chi phí": "for a budget-conscious traveler",
    "đi cặp đôi": "for a couple",
    "đi cùng người lớn tuổi": "for a trip with older adults",
    "thích trải nghiệm địa phương": "for someone who likes local experiences",
    "đi cùng gia đình có trẻ nhỏ": "for a family with young children",
    "đi một mình": "for a solo traveler",
    "muốn đi chậm và nghỉ dưỡng": "for a slow-paced relaxing trip",
    "lần đầu đến Việt Nam": "for a first-time visitor to Vietnam",
    "đi nhóm bạn": "for a group of friends",
}

TIME_MAP = {
    "buổi tối": "in the evening",
    "mùa mưa": "during the rainy season",
    "mùa hè": "in summer",
    "dịp lễ": "during a public holiday",
    "4 ngày 3 đêm": "for 4 days and 3 nights",
    "một ngày": "for one day",
    "cuối tuần": "for a weekend trip",
    "3 ngày 2 đêm": "for 3 days and 2 nights",
    "2 ngày 1 đêm": "for 2 days and 1 night",
    "buổi sáng": "in the morning",
}

ENTITY_HINT_MAP = {
    "street food": "street food",
    "phố cổ": "old town",
    "biển": "beaches",
    "bãi biển": "beaches",
    "đền chùa": "temples and pagodas",
    "chợ địa phương": "local markets",
    "ẩm thực": "food experiences",
    "bảo tàng": "museums",
    "khu di sản": "heritage sites",
    "tour trong ngày": "day tours",
    "homestay": "homestays",
    "văn hóa": "culture",
    "điểm ngắm hoàng hôn": "sunset viewpoints",
    "cà phê Việt Nam": "Vietnamese coffee",
    "khách sạn gần phố cổ": "hotels near the old town",
    "khu gần chợ đêm": "areas near the night market",
    "làng nghề": "craft villages",
    "nghỉ dưỡng": "resorts and relaxation",
    "điểm miễn phí": "free attractions",
    "chợ đêm": "night markets",
    "hang động": "caves",
    "resort ven biển": "beachfront resorts",
    "di chuyển": "transportation",
    "điểm ngắm cảnh": "viewpoints",
    "leo núi": "hiking",
    "show văn hóa": "cultural shows",
    "ẩm thực truyền thống": "traditional food",
    "rooftop bar": "rooftop bars",
    "ẩm thực đường phố": "street food",
    "nơi lưu trú": "places to stay",
    "điểm nổi bật": "highlights",
    "sân bay": "airport transfer",
    "quán địa phương": "local eateries",
    "đi lại": "getting around",
    "phố đi bộ": "walking streets",
    "khu trung tâm": "central areas",
    "quà lưu niệm": "souvenirs",
    "đi biển": "beach activities",
    "món đặc sản": "local specialties",
    "tin tức điểm đến": "destination updates",
    "lễ hội địa phương": "local festivals",
    "trung tâm thành phố": "city center",
    "xe máy": "motorbike travel",
    "đi bộ phố cổ": "walking around the old town",
    "lịch trình": "itinerary",
    "công viên": "parks",
    "sự kiện du lịch": "travel events",
    "khu nghỉ dưỡng": "resort areas",
    "taxi": "taxi",
    "quán bar": "bars",
    "các điểm tham quan": "attractions",
    "lụa": "silk",
    "tour tự túc": "self-guided tours",
    "tham quan ngoài trời": "outdoor sightseeing",
    "chi phí": "travel costs",
    "đồ thủ công": "handicrafts",
    "điểm ít phải đi bộ": "places with less walking",
    "lễ hội": "festivals",
    "phương tiện công cộng": "public transportation",
    "chụp ảnh": "photo spots",
    "tàu hoặc xe bus": "train or bus",
    "tour nhẹ nhàng": "easy tours",
    "ngắm cảnh đêm": "night views",
    "hoạt động theo mùa": "seasonal activities",
    "di sản UNESCO": "UNESCO heritage",
    "cà phê": "coffee",
    "chợ truyền thống": "traditional markets",
    "đặc sản địa phương": "local specialties",
}

CATEGORY_CRITERIA_EN = {
    "accommodation": "Relevant context should mention where to stay, hotels, resorts, homestays, neighborhoods, or criteria for choosing accommodation.",
    "attraction": "Relevant context should mention attractions, notable places, reasons to visit, or practical information about the destination.",
    "itinerary": "Relevant context should include itinerary ideas, activity order, time suggestions, places to visit, or trip planning guidance.",
    "food": "Relevant context should mention food, local dishes, restaurants, street food, markets, or dining experiences.",
    "culture": "Relevant context should mention culture, heritage, history, craft villages, museums, traditions, or local experiences.",
    "weather": "Relevant context should mention seasons, weather, best time to visit, rainy season, or timing advice.",
    "comparison": "Relevant context should provide information useful for comparing destinations, activities, timing, crowd levels, or traveler fit.",
    "nightlife": "Relevant context should mention nightlife, evening activities, bars, night markets, walking streets, or night views.",
    "transport": "Relevant context should mention transportation, airport transfer, routes, getting around, taxi, motorbike, bus, train, or walking.",
    "shopping": "Relevant context should mention shopping, souvenirs, markets, local products, craft goods, or shopping tips.",
    "budget": "Relevant context should mention costs, budget-friendly options, free attractions, value-for-money experiences, or money-saving tips.",
    "family": "Relevant context should mention family-friendly activities, children, older adults, easy access, safety, or relaxed pacing.",
    "event": "Relevant context should mention festivals, local events, seasonal events, cultural activities, or travel events.",
    "general": "Relevant context should provide general destination guidance, overview, highlights, practical tips, or important things to know.",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Đọc file JSONL."""

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def to_en_location(location: str | None) -> str:
    """Chuẩn hóa địa danh sang dạng tiếng Anh phổ biến."""

    if not location:
        return "Vietnam"
    return LOCATION_MAP.get(location, location)


def get_locations_from_query(row: dict[str, Any]) -> list[str]:
    """Lấy địa danh từ metadata và scan query để không mất điểm đến so sánh."""

    original_query = str(row.get("query") or "")
    found: list[str] = []
    for location in row.get("locations") or []:
        found.append(to_en_location(location))
    for vi_location, en_location in LOCATION_MAP.items():
        if re.search(re.escape(vi_location), original_query, flags=re.IGNORECASE):
            found.append(en_location)
    deduped: list[str] = []
    for item in found:
        if item not in deduped:
            deduped.append(item)
    return deduped or ["Vietnam"]


def get_profile(row: dict[str, Any]) -> str:
    """Dịch traveler profile."""

    profile = row.get("traveler_profile")
    return PROFILE_MAP.get(profile, "for a traveler")


def get_time(row: dict[str, Any]) -> str:
    """Dịch time context."""

    time_context = row.get("time_context")
    return TIME_MAP.get(time_context, "for this trip")


def get_hint(row: dict[str, Any]) -> str:
    """Dịch entity hint."""

    hint = row.get("entity_hint")
    return ENTITY_HINT_MAP.get(hint, str(hint or "travel experiences"))


def extract_constraints(query_vi: str) -> list[str]:
    """Rút các ràng buộc thường gặp từ câu tiếng Việt."""

    constraints: list[str] = []
    checks = [
        (r"không quá chung chung|thực tế", "practical and not too generic"),
        (r"dễ đi|người lần đầu|người mới", "easy for first-time visitors"),
        (r"tránh nơi quá đông|quá đông", "avoid overly crowded places if possible"),
        (r"đáng tiền", "good value for money"),
        (r"thư giãn", "include relaxing options"),
        (r"cần tránh|lưu ý", "include things to avoid or practical cautions"),
        (r"tiết kiệm|chi phí", "budget-friendly"),
        (r"trẻ nhỏ|gia đình", "suitable for families with children"),
        (r"người lớn tuổi", "suitable for older adults"),
        (r"ít phải đi bộ", "with less walking if possible"),
        (r"tự túc", "suitable for independent travel"),
        (r"đi chậm|nghỉ dưỡng", "slow-paced and relaxing"),
        (r"chụp ảnh", "good for photography"),
    ]
    for pattern, phrase in checks:
        if re.search(pattern, query_vi, flags=re.IGNORECASE):
            constraints.append(phrase)
    return constraints


def join_constraints(constraints: list[str]) -> str:
    """Ghép constraints vào cuối query."""

    if not constraints:
        return ""
    return ". Please make it " + ", ".join(constraints) + "."


def build_english_query(row: dict[str, Any]) -> str:
    """Sinh query tiếng Anh từ metadata."""

    category = str(row.get("category") or row.get("user_intent") or "general")
    locations = get_locations_from_query(row)
    place = locations[0]
    profile = get_profile(row)
    time_context = get_time(row)
    hint = get_hint(row)
    constraints = join_constraints(extract_constraints(str(row.get("query") or "")))

    if category == "comparison" and len(locations) >= 2:
        base = f"Should I choose {locations[0]} or {locations[1]} {time_context} {profile}? Compare them for travel fit, activities, crowds, and practical tips."
    elif category == "comparison":
        base = f"How does {place} compare with other Vietnam destinations {time_context} {profile}? Include travel fit, activities, crowds, and practical tips."
    elif category == "accommodation":
        base = f"Where should I stay in {place} {time_context} {profile}? Recommend convenient areas for sightseeing, food, and accommodation options."
    elif category == "attraction":
        base = f"What are the best attractions or places to visit in {place} {time_context} {profile}, especially around {hint}?"
    elif category == "itinerary":
        base = f"Can you suggest a practical itinerary for {place} {time_context} {profile}, with priority activities and places to visit?"
    elif category == "food":
        base = f"What should I eat in {place} {time_context} {profile}? Recommend local dishes, food experiences, and places related to {hint}."
    elif category == "culture":
        base = f"Where can I experience local culture, heritage, or history in {place} {time_context} {profile}, especially around {hint}?"
    elif category == "weather":
        base = f"When is the best time to visit {place} {profile}? Explain weather, seasons, and timing advice for {time_context}."
    elif category == "nightlife":
        base = f"What should I do in {place} at night {profile}? Recommend evening activities, nightlife, night markets, or viewpoints around {hint}."
    elif category == "transport":
        base = f"How should I get around {place} {time_context} {profile}? Include transportation options, routes, and practical travel tips related to {hint}."
    elif category == "shopping":
        base = f"What should I buy or avoid when shopping in {place} {time_context} {profile}? Include markets, souvenirs, local products, and practical tips."
    elif category == "budget":
        base = f"How can I travel in {place} on a budget {time_context} {profile}? Recommend free or good-value activities, food, and practical cost-saving tips."
    elif category == "family":
        base = f"What are family-friendly things to do in {place} {time_context} {profile}? Include easy activities, suitable places, and practical cautions."
    elif category == "event":
        base = f"Are there festivals, local events, or traditional activities in {place} {time_context} {profile}? Include what is worth experiencing."
    else:
        base = f"What should I know before traveling to {place} {time_context} {profile}? Include highlights, practical tips, food, attractions, and things to avoid."

    return base.rstrip(".?") + constraints if constraints else base


def build_output_row(row: dict[str, Any]) -> dict[str, Any]:
    """Tạo row output tiếng Anh, giữ metadata gốc."""

    query_vi = str(row.get("query") or "")
    query_en = build_english_query(row)
    output = dict(row)
    output["query_vi"] = query_vi
    output["query"] = query_en
    output["query_en"] = query_en
    output["locations_en"] = get_locations_from_query(row)
    output["judge_relevance_criteria_vi"] = row.get("judge_relevance_criteria")
    output["judge_relevance_criteria_en"] = CATEGORY_CRITERIA_EN.get(
        str(row.get("category") or row.get("user_intent") or "general"),
        CATEGORY_CRITERIA_EN["general"],
    )
    output["language"] = "en"
    output["source_language"] = "vi"
    output["translation_method"] = "metadata_template_rewrite_v1"
    return output


def main() -> int:
    """Entry point."""

    rows = load_jsonl(INPUT_PATH)
    outputs = [build_output_row(row) for row in rows]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in outputs) + "\n",
        encoding="utf-8",
    )
    print(f"Đã sinh {len(outputs)} English traveler queries.")
    print(f"Output: {OUTPUT_PATH}")
    print(json.dumps(outputs[0], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
