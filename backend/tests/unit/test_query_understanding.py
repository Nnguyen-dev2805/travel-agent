"""Unit tests for query parsing metadata filters and bonus ranking."""

from backend.rag.query_understanding import (
    QwenQueryParser,
    apply_metadata_bonus,
    build_query_filters,
    expand_location_filters,
)
from backend.rag.query_understanding.query_parser import CITY_ALIASES, normalize_parsed_query


class FakeMessage:
    content = """
    {
      "language": null,
      "locations": ["Da Nang"],
      "regions": [],
      "category": ["nightlife"],
      "topic": "rooftop bar",
      "entity_type": ["bar"],
      "content_type": "travel_guide",
      "content_type_required": false,
      "confidence": 0.91
    }
    """


class FakeChoice:
    message = FakeMessage()


class FakeCompletion:
    choices = [FakeChoice()]


class FakeCompletions:
    def create(self, **kwargs):
        assert kwargs["model"] == "Qwen/Qwen2.5-14B-Instruct"
        assert kwargs["temperature"] == 0
        return FakeCompletion()


class FakeChat:
    completions = FakeCompletions()


class FakeClient:
    chat = FakeChat()


def test_qwen_query_parser_normalizes_json_response():
    parser = QwenQueryParser(
        base_url="http://vllm.test/v1",
        api_key="EMPTY",
        model="Qwen/Qwen2.5-14B-Instruct",
        client=FakeClient(),
    )

    parsed = parser.parse("rooftop bar in Da Nang")

    assert parsed.language is None
    assert parsed.locations == ["Da Nang"]
    assert parsed.expanded_locations == ["Da Nang"]
    assert parsed.category == ["nightlife"]
    assert parsed.topic == "rooftop bar"
    assert parsed.entity_type == ["bar"]
    assert parsed.content_type is None
    assert parsed.content_type_required is False
    assert parsed.confidence == 0.91


def test_build_query_filters_adds_location_only_pre_filter():
    parser = QwenQueryParser(
        base_url="http://vllm.test/v1",
        api_key="EMPTY",
        model="Qwen/Qwen2.5-14B-Instruct",
        client=FakeClient(),
    )
    parsed = parser.parse("rooftop bar in Da Nang")

    filters = build_query_filters(parsed, default_language="en")

    assert filters.exact_filters == {}
    assert filters.chroma_where() == {
        "$or": [
            {"primary_location": "Da Nang"},
            {"location_1": "Da Nang"},
            {"location_2": "Da Nang"},
            {"location_3": "Da Nang"},
            {"location_4": "Da Nang"},
            {"location_5": "Da Nang"},
            {"location_6": "Da Nang"},
            {"location_7": "Da Nang"},
            {"location_8": "Da Nang"},
        ]
    }
    assert filters.elasticsearch_filters() == {"__locations_any": ["Da Nang"]}


def test_build_query_filters_skips_prefilter_without_explicit_location_or_region():
    parser = QwenQueryParser(
        base_url="http://vllm.test/v1",
        api_key="EMPTY",
        model="Qwen/Qwen2.5-14B-Instruct",
        client=FakeClient(),
    )
    parsed = parser.parse("find beautiful rooftop bars")

    assert parsed.locations == []
    assert parsed.regions == []
    filters = build_query_filters(parsed, default_language="en")

    assert filters.chroma_where() is None
    assert filters.elasticsearch_filters() == {}


def test_location_filter_keeps_only_explicit_locations():
    assert expand_location_filters(["Cam Ranh"]) == ["Cam Ranh"]
    assert expand_location_filters(["Mekong River Delta"]) == ["Mekong River Delta"]


def test_mekong_river_delta_alias_survives_explicit_guard():
    parsed = normalize_parsed_query(
        "What are things to do in the Mekong River Delta?",
        {
            "hard_filters": {
                "locations": ["Mekong Delta"],
                "regions": [],
                "content_type": None,
                "content_type_required": False,
            },
            "soft_signals": {"category": ["experience"], "topic": "things to do", "entity_type": []},
            "confidence": 0.9,
        },
    )

    filters = build_query_filters(parsed, default_language="en")

    assert parsed.locations == ["Mekong Delta"]
    assert filters.location_cities == ["Mekong Delta"]


def test_city_aliases_cover_current_corpus_location_variants():
    expected_aliases = {
        "an giang": "An Giang",
        "ba be": "Ba Be",
        "ben tre": "Ben Tre",
        "buon ma thuot": "Buon Ma Thuot",
        "chau doc": "Chau Doc",
        "dak lak": "Dak Lak",
        "dong hoi": "Dong Hoi",
        "dong thap": "Dong Thap",
        "gia lai": "Gia Lai",
        "hai phong": "Hai Phong",
        "kon tum": "Kon Tum",
        "lam dong": "Lam Dong",
        "lao cai": "Lao Cai",
        "mai chau": "Mai Chau",
        "my tho": "My Tho",
        "nghe an": "Nghe An",
        "phan thiet": "Phan Thiet",
        "pu luong": "Pu Luong",
        "quang nam": "Quang Nam",
        "quang ninh": "Quang Ninh",
        "quang tri": "Quang Tri",
        "tay ninh": "Tay Ninh",
        "thanh hoa": "Thanh Hoa",
    }

    for alias, canonical in expected_aliases.items():
        assert CITY_ALIASES[alias] == canonical


def test_sublocation_alias_survives_explicit_guard_for_corpus_location():
    parsed = normalize_parsed_query(
        "Đêm khai mạc ở Đồ Sơn diễn ra lúc mấy giờ?",
        {
            "hard_filters": {
                "locations": ["Hai Phong"],
                "regions": [],
                "content_type": None,
                "content_type_required": False,
            },
            "soft_signals": {"category": ["culture"], "topic": "đêm khai mạc", "entity_type": []},
            "confidence": 0.9,
        },
    )

    assert parsed.locations == ["Hai Phong"]


def test_fuzzy_raw_location_mention_accepts_typo_for_hard_filter():
    parsed = normalize_parsed_query(
        "Nhung dieu thu vi tai daaanang",
        {
            "hard_filters": {
                "raw_location_mentions": ["daaanang"],
                "locations": ["Da Nang"],
                "regions": [],
                "content_type": None,
                "content_type_required": False,
            },
            "soft_signals": {"category": ["experience"], "topic": "dieu thu vi", "entity_type": []},
            "confidence": 0.4,
        },
    )

    filters = build_query_filters(parsed, default_language="en")

    assert parsed.raw_location_mentions == ["daaanang"]
    assert parsed.locations == ["Da Nang"]
    assert parsed.location_match_type == "fuzzy"
    assert parsed.location_match_score >= 0.86
    assert parsed.confidence >= parsed.location_match_score
    assert filters.location_cities == ["Da Nang"]


def test_llm_only_location_without_raw_mention_is_not_hard_filtered():
    parsed = normalize_parsed_query(
        "Nhung bai bien dep o Viet Nam",
        {
            "hard_filters": {
                "raw_location_mentions": [],
                "locations": ["Da Nang"],
                "regions": [],
                "content_type": None,
                "content_type_required": False,
            },
            "soft_signals": {"category": ["beach"], "topic": "bai bien dep", "entity_type": ["beach"]},
            "confidence": 0.9,
        },
    )

    filters = build_query_filters(parsed, default_language="en")

    assert parsed.locations == []
    assert parsed.location_match_type is None
    assert filters.location_cities == []


def test_normalize_parsed_query_accepts_hard_filters_and_soft_signals_schema():
    parsed = normalize_parsed_query(
        "Find rooftop bars in Da Nang",
        {
            "hard_filters": {
                "language": None,
                "locations": ["Da Nang"],
                "expanded_locations": ["Da Nang", "Hoi An"],
                "regions": [],
                "content_type": "travel_guide",
                "content_type_required": False,
            },
            "soft_signals": {
                "category": ["nightlife"],
                "topic": "rooftop bars",
                "entity_type": ["bar"],
            },
            "confidence": 0.95,
        },
    )

    assert parsed.locations == ["Da Nang"]
    assert parsed.expanded_locations == ["Da Nang"]
    assert parsed.category == ["nightlife"]
    assert parsed.topic == "rooftop bars"
    assert parsed.entity_type == ["bar"]
    assert parsed.content_type is None
    assert parsed.content_type_required is False
    assert parsed.confidence == 0.95


def test_build_query_filters_ignores_inferred_parser_expanded_locations():
    parsed = normalize_parsed_query(
        "Can I get free yoga classes when staying at Fusion Cam Ranh?",
        {
            "hard_filters": {
                "locations": ["Cam Ranh"],
                "expanded_locations": ["Cam Ranh", "Nha Trang", "Khanh Hoa"],
                "regions": [],
                "content_type": None,
                "content_type_required": False,
            },
            "soft_signals": {"category": ["wellness"], "topic": "yoga classes", "entity_type": ["hotel"]},
            "confidence": 0.94,
        },
    )

    filters = build_query_filters(parsed, default_language="en")

    assert parsed.locations == ["Cam Ranh"]
    assert parsed.expanded_locations == ["Cam Ranh"]
    assert filters.location_cities == ["Cam Ranh"]


def test_apply_metadata_bonus_uses_cross_encoder_and_metadata_scores():
    parser = QwenQueryParser(
        base_url="http://vllm.test/v1",
        api_key="EMPTY",
        model="Qwen/Qwen2.5-14B-Instruct",
        client=FakeClient(),
    )
    parsed = parser.parse("rooftop bar in Da Nang")
    results = [
        {
            "chunk_id": "generic",
            "rerank_score": 0.8,
            "score": 0.8,
            "metadata": {
                "locations": "Ha Noi",
                "topic": "museum",
                "entity_type": "museum",
                "content_type": "travel_guide",
            },
        },
        {
            "chunk_id": "metadata_match",
            "rerank_score": 0.76,
            "score": 0.76,
            "metadata": {
                "locations": "Nha Trang, Da Nang",
                "topic": "rooftop bar",
                "entity_type": "bar, hotel",
                "content_type": "travel_guide",
            },
        },
    ]

    reranked = apply_metadata_bonus(results, parsed, top_k=2)

    assert [item["chunk_id"] for item in reranked] == ["metadata_match", "generic"]
    assert reranked[0]["metadata_score"] == 1.0
    assert reranked[0]["final_score"] == 0.808
