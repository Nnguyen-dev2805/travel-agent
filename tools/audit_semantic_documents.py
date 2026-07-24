import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

"""Audit dữ liệu document đã clean để chuẩn bị semantic Parent-Child chunking.

Script này đọc `documents.jsonl`, thống kê chất lượng section/heading, tìm các lỗi
boundary/hierarchy thường gặp, rồi sinh ra:

- `semantic_data_audit.md`: report đọc thủ công cho T01.
- `semantic_structure_gold.jsonl`: sample regression cho các task T03/T04/T05.
"""


NOISE_PATTERNS = [
    r"click the image",
    r"360-degree",
    r"360 degree",
    r"photo by",
    r"photos? courtesy",
    r"credit",
    r"read more",
    r"learn more",
    r"for more information",
    r"visit:",
    r"book now",
    r"share this",
    r"subscribe",
    r"follow us",
    r"copyright",
    r"located at",
    r"tel:",
    r"email:",
    r"website:",
]

FACET_TERMS = {
    "best time",
    "how to get there",
    "getting there",
    "tips",
    "travel tips",
    "entrance fee",
    "opening hours",
    "where to stay",
    "where to eat",
    "what to eat",
    "things to do",
    "when to go",
    "transportation",
    "accommodation",
    "location",
    "price",
    "prices",
    "ticket",
    "tickets",
    "overview",
    "getting around",
    "food",
    "activities",
    "highlights",
    "itinerary",
    "day 1",
    "day 2",
    "day 3",
    "day one",
    "day two",
    "day three",
}

NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.I)
ENTITY_HINT_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,5}|[A-Z][a-z]+,\s*[A-Z][a-z]+)\b"
)
PARAGRAPH_LIKE_RE = re.compile(
    r"[.!?]\s+[A-Z]|,\s+\w+\s+|\b(and|or|but|while|where|which|that|because)\b",
    re.I,
)


def percentile(values, p):
    """Tính percentile cho một list số.

    Dùng trong report để mô tả phân phối word/document, section/document và
    word/section. Hàm này tự sort dữ liệu và nội suy tuyến tính khi vị trí
    percentile nằm giữa hai điểm dữ liệu.
    """
    if not values:
        return 0
    ordered = sorted(values)
    k = (len(ordered) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def load_jsonl(path):
    """Đọc file JSONL và tách record hợp lệ với dòng bị lỗi.

    Mỗi dòng hợp lệ được parse thành dict và gắn thêm `_line_no` để truy vết
    ngược về vị trí trong file nguồn. Dòng lỗi không làm dừng audit; lỗi được
    gom vào `bad_json` để report tổng quan.
    """
    records = []
    bad_json = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                record["_line_no"] = line_no
                records.append(record)
            except Exception as exc:
                bad_json.append((line_no, str(exc)))
    return records, bad_json


def build_section_rows(records):
    """Flatten `documents[].sections[]` thành các row dễ thống kê.

    Input gốc có cấu trúc document -> sections. Audit cần thao tác theo từng
    section, nên hàm này chuẩn hóa các field quan trọng như `heading_path`,
    `word_count`, `heading_source`, `heading_level`, title, url và metadata
    document. Hàm không sửa source text.
    """
    rows = []
    for document in records:
        for fallback_index, section in enumerate(document.get("sections") or []):
            text = section.get("text") or ""
            heading_path = section.get("heading_path") or []
            if isinstance(heading_path, str):
                heading_path = [heading_path]
            word_count = section.get("word_count")
            if not isinstance(word_count, int):
                word_count = len(text.split())
            rows.append(
                {
                    "document_id": document.get("document_id"),
                    "url": document.get("url"),
                    "title": document.get("title"),
                    "language": document.get("language"),
                    "domain": document.get("source_domain") or document.get("source"),
                    "section_index": section.get("section_index", fallback_index),
                    "heading": section.get("heading") or "",
                    "heading_level": section.get("heading_level"),
                    "heading_source": section.get("heading_source"),
                    "heading_path": heading_path,
                    "text": text,
                    "word_count": word_count,
                }
            )
    return rows


def is_facet_heading(heading):
    """Nhận diện heading dạng facet/attribute bằng keyword rule.

    Facet là các heading như `Best time`, `How to get there`, `Tips`. Các
    heading này thường nên được gộp vào entity parent khi nội dung ngắn, thay vì
    mặc định tạo entity chunk riêng.
    """
    normalized = heading.lower().strip()
    return normalized in FACET_TERMS or any(
        normalized.startswith(term + ":") for term in FACET_TERMS
    )


def find_hierarchy_anomalies(records, section_rows):
    """Tìm các dấu hiệu hierarchy sai do HTML heading level.

    Hàm trả về hai nhóm:

    - `hierarchy_jumps`: heading level nhảy quá sâu so với section trước.
    - `entity_sibling_nested`: entity có vẻ là sibling nhưng lại nằm trong
      `heading_path` của entity trước đó, ví dụ rooftop bar A chứa rooftop bar B.

    Đây là heuristic audit, không phải ground truth tuyệt đối. Các record tìm
    được dùng để đưa vào review set và gold regression sample.
    """
    hierarchy_jumps = []
    entity_sibling_nested = []
    row_by_doc_section = {
        (row["document_id"], row["section_index"]): row for row in section_rows
    }

    for document in records:
        previous = None
        previous_entity_like = None
        document_id = document.get("document_id")
        for section in document.get("sections") or []:
            heading = section.get("heading") or ""
            level = section.get("heading_level")
            heading_path = section.get("heading_path") or []
            if isinstance(heading_path, str):
                heading_path = [heading_path]
            row = row_by_doc_section.get((document_id, section.get("section_index")))

            if previous and isinstance(level, int) and isinstance(
                previous.get("heading_level"), int
            ):
                if level - previous.get("heading_level") > 1 and row:
                    hierarchy_jumps.append(row)

            is_entity_like = (
                bool(ENTITY_HINT_RE.search(heading))
                and not is_facet_heading(heading)
                and len(heading.split()) <= 8
            )
            if row and is_entity_like and len(heading_path) >= 2:
                parent_heading = heading_path[-2]
                if previous_entity_like and parent_heading == previous_entity_like["heading"]:
                    entity_sibling_nested.append(
                        {
                            **row,
                            "suspected_parent": parent_heading,
                            "previous_entity": previous_entity_like["heading"],
                        }
                    )
                if (
                    parent_heading
                    and bool(ENTITY_HINT_RE.search(parent_heading))
                    and parent_heading != document.get("title")
                ):
                    entity_sibling_nested.append(
                        {
                            **row,
                            "suspected_parent": parent_heading,
                            "previous_entity": parent_heading,
                        }
                    )
            if is_entity_like:
                previous_entity_like = {
                    "heading": heading,
                    "section_index": section.get("section_index"),
                }
            previous = section

    return hierarchy_jumps, entity_sibling_nested


def find_parent_lead_candidates(section_rows):
    """Tìm section có thể dùng làm Parent `extractive_lead`.

    Một parent lead tốt thường là text trực tiếp dưới heading cha và parent đó
    có child descendants trong `heading_path`. Hàm chọn các section có heading,
    text đủ dài và có section con để gợi ý tạo `context_summary` nguyên văn.
    """
    candidates = []
    rows_by_doc = defaultdict(list)
    for row in section_rows:
        rows_by_doc[row["document_id"]].append(row)

    for rows in rows_by_doc.values():
        for row in rows:
            if not row["heading"] or row["word_count"] < 25:
                continue
            has_child = any(
                len(other["heading_path"]) > len(row["heading_path"])
                and other["heading_path"][: len(row["heading_path"])] == row["heading_path"]
                for other in rows
            )
            if has_child:
                candidates.append(row)
    return candidates


def add_unique(items, value):
    """Append một giá trị vào list nếu giá trị chưa tồn tại."""
    if value and value not in items:
        items.append(value)


def select_review_documents(records, anomaly_buckets, limit=50):
    """Chọn tập document cần review thủ công.

    Chiến lược chọn ưu tiên document có anomaly trước, sau đó thêm document có
    nhiều section và cuối cùng backfill bằng document đầu vào. Mục tiêu là có
    khoảng 40-60 document đa dạng để review boundary/hierarchy.
    """
    review_doc_ids = []
    for bucket in anomaly_buckets:
        for row in bucket[:20]:
            add_unique(review_doc_ids, row["document_id"])
    for document in sorted(records, key=lambda item: len(item.get("sections") or []), reverse=True)[
        :20
    ]:
        add_unique(review_doc_ids, document.get("document_id"))
    for document in records:
        add_unique(review_doc_ids, document.get("document_id"))
        if len(review_doc_ids) >= limit:
            break
    return review_doc_ids[:limit]


def build_gold_sample(
    entity_sibling_nested,
    visual_headings,
    noise_path_rows,
    long_headings,
    parent_lead_candidates,
    semantic_headings,
    limit=60,
):
    """Sinh gold sample JSONL cho regression structure.

    Gold sample chứa nhiều loại case: entity sibling bị lồng sai, visual heading,
    noise heading/path, paragraph-like heading, parent có extractive lead và
    semantic section bình thường. Đây là tập ban đầu để test T03/T04/T05, chưa
    thay thế review thủ công.
    """
    gold = []

    def add(row, role, parent=None, valid=True, reason=""):
        """Thêm một gold record theo schema regression tối thiểu."""
        gold.append(
            {
                "document_id": row.get("document_id"),
                "section_index": row.get("section_index"),
                "heading": row.get("heading"),
                "expected_role": role,
                "expected_parent_heading": parent,
                "is_valid_boundary": bool(valid),
                "reason": reason,
                "url": row.get("url"),
            }
        )

    for row in entity_sibling_nested[:15]:
        add(
            row,
            "entity",
            row.get("title"),
            True,
            f"Suspected sibling entity nested under '{row.get('suspected_parent')}'.",
        )
    for row in visual_headings[:12]:
        heading = (row["heading"] or "").lower()
        role = "noise" if NOISE_RE.search(heading) else (
            "facet" if heading in FACET_TERMS else "visual_heading"
        )
        parent = row["heading_path"][-2] if len(row["heading_path"]) > 1 else row.get("title")
        add(row, role, parent, role != "noise", "Visual heading from styled paragraph/strong text.")
    for row in noise_path_rows[:12]:
        add(row, "noise", None, False, "Heading path contains CTA/caption/noise text.")
    for row in long_headings[:10]:
        parent = row["heading_path"][-2] if len(row["heading_path"]) > 1 else row.get("title")
        add(
            row,
            "paragraph_like_heading",
            parent,
            False,
            "Heading is long or sentence-like; should be demoted or reviewed.",
        )
    for row in parent_lead_candidates[:12]:
        parent = row["heading_path"][-2] if len(row["heading_path"]) > 1 else None
        add(
            row,
            "parent_with_extractive_lead",
            parent,
            True,
            "Candidate parent has direct overview text before child sections.",
        )
    for row in semantic_headings:
        if len(gold) >= limit:
            break
        normalized = (row["heading"] or "").lower().strip()
        if row["word_count"] >= 40 and not NOISE_RE.search(row["heading"] or ""):
            role = "facet" if normalized in FACET_TERMS else "semantic_section"
            parent = row["heading_path"][-2] if len(row["heading_path"]) > 1 else None
            add(row, role, parent, True, "Normal semantic boundary sample.")

    seen = set()
    deduped = []
    for item in gold:
        key = (item["document_id"], item["section_index"], item["expected_role"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:limit]


def table_counter(counter, limit=20):
    """Render Counter thành bảng Markdown hai cột."""
    lines = ["| Giá trị | Số lượng |", "|---|---:|"]
    for key, value in counter.most_common(limit):
        lines.append(f"| `{key}` | {value} |")
    return "\n".join(lines)


def example_table(rows, extra_cols=None, limit=12):
    """Render một nhóm anomaly thành bảng Markdown có ví dụ cụ thể.

    Các giá trị dài được cắt ngắn để report dễ đọc, còn dữ liệu nguồn vẫn nằm
    nguyên trong `documents.jsonl` và gold sample.
    """
    extra_cols = extra_cols or []
    headers = ["document_id", "section_index", "heading", "word_count"] + extra_cols
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows[:limit]:
        values = []
        for header in headers:
            value = row.get(header, "")
            if isinstance(value, list):
                value = " > ".join(map(str, value))
            value = str(value).replace("\n", " ").replace("|", "\\|")
            if len(value) > 110:
                value = value[:107] + "..."
            values.append(value)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_outputs(input_path, out_dir):
    """Chạy toàn bộ audit và ghi report/gold sample ra thư mục output.

    Luồng xử lý:

    1. Đọc JSONL và flatten section.
    2. Tính thống kê phân phối và counter metadata.
    3. Tìm các nhóm lỗi boundary/hierarchy bằng heuristic.
    4. Chọn review set và sinh gold sample.
    5. Ghi Markdown report bằng `utf-8-sig` để tránh lỗi font khi mở trên
       Windows tools; ghi JSONL bằng UTF-8 chuẩn để dễ parse.
    """
    records, bad_json = load_jsonl(input_path)
    section_rows = build_section_rows(records)

    word_counts_doc = [
        len((document.get("text") or document.get("plain_text") or "").split())
        for document in records
    ]
    sections_per_doc = [len(document.get("sections") or []) for document in records]
    section_word_counts = [row["word_count"] for row in section_rows]

    missing_lang = [document for document in records if not document.get("language")]
    heading_source_counts = Counter(row["heading_source"] or "<missing>" for row in section_rows)
    heading_level_counts = Counter(
        str(row["heading_level"]) if row["heading_level"] is not None else "<missing>"
        for row in section_rows
    )
    language_counts = Counter(document.get("language") or "<missing>" for document in records)
    domain_counts = Counter(
        document.get("source_domain") or document.get("source") or "<missing>"
        for document in records
    )

    empty_sections = [row for row in section_rows if not row["text"].strip()]
    short_sections = [row for row in section_rows if 0 < row["word_count"] < 40]
    long_sections = [row for row in section_rows if row["word_count"] > 450]
    very_long_sections = [row for row in section_rows if row["word_count"] > 900]
    long_headings = [
        row
        for row in section_rows
        if len(row["heading"]) > 120
        or len(row["heading"].split()) > 16
        or PARAGRAPH_LIKE_RE.search(row["heading"] or "")
    ]
    visual_headings = [
        row for row in section_rows if (row["heading_source"] or "").lower() == "visual"
    ]
    semantic_headings = [
        row for row in section_rows if (row["heading_source"] or "").lower() == "semantic"
    ]
    noise_heading_rows = [row for row in section_rows if NOISE_RE.search(row["heading"] or "")]
    noise_path_rows = [
        row
        for row in section_rows
        if any(NOISE_RE.search(str(part)) for part in row["heading_path"])
    ]
    hierarchy_jumps, entity_sibling_nested = find_hierarchy_anomalies(records, section_rows)
    parent_lead_candidates = find_parent_lead_candidates(section_rows)

    review_doc_ids = select_review_documents(
        records,
        [
            noise_path_rows,
            entity_sibling_nested,
            long_headings,
            visual_headings,
            long_sections,
            short_sections,
            parent_lead_candidates,
        ],
    )
    gold = build_gold_sample(
        entity_sibling_nested,
        visual_headings,
        noise_path_rows,
        long_headings,
        parent_lead_candidates,
        semantic_headings,
    )

    out_dir.mkdir(exist_ok=True)
    report_path = out_dir / "semantic_data_audit.md"
    gold_path = out_dir / "semantic_structure_gold.jsonl"

    with gold_path.open("w", encoding="utf-8") as file:
        for item in gold:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")

    report = [
        "# T01 - Audit Dữ Liệu Hiện Tại Cho Semantic Parent-Child Hybrid RAG",
        "",
        f"- Input: `{input_path.as_posix()}`",
        f"- Số dòng JSON hợp lệ: {len(records)}",
        f"- Số dòng JSON lỗi: {len(bad_json)}",
        f"- Tổng số section: {len(section_rows)}",
        f"- Report sinh tại: `{report_path.as_posix()}`",
        f"- Gold sample sinh tại: `{gold_path.as_posix()}`",
        "",
        "## 1. Tóm Tắt Kết Luận",
        "",
        "- Dữ liệu đủ tốt để bắt đầu pipeline semantic Parent-Child từ `documents.jsonl`, vì mỗi document đã có `sections[]`, `heading`, `heading_path`, `text` và `word_count`.",
        "- Rủi ro chính không nằm ở text thô, mà nằm ở boundary/hierarchy: một số heading visual từ `<strong>`, CTA/caption/noise trong heading path, heading giống paragraph, và entity sibling bị lồng sai do cấp heading HTML.",
        "- Parent summary nên ưu tiên `extractive_lead`: lấy đoạn overview đầu tiên ngay dưới heading cha nếu section có text đủ tốt.",
        "- Cần có regression set trước khi viết chunker, đặc biệt cho case listicle/entity sibling như rooftop bars.",
        "",
        "## 2. Thống Kê Tổng Quan",
        "",
        "| Metric | Giá trị |",
        "|---|---:|",
        f"| Documents | {len(records)} |",
        f"| Sections | {len(section_rows)} |",
        f"| Empty sections | {len(empty_sections)} |",
        f"| Missing language documents | {len(missing_lang)} |",
        f"| Short sections `<40 words` | {len(short_sections)} |",
        f"| Long sections `>450 words` | {len(long_sections)} |",
        f"| Very long sections `>900 words` | {len(very_long_sections)} |",
        f"| Visual heading sections | {len(visual_headings)} |",
        f"| Long/paragraph-like headings | {len(long_headings)} |",
        f"| Noise headings | {len(noise_heading_rows)} |",
        f"| Heading paths containing noise | {len(noise_path_rows)} |",
        f"| Suspected hierarchy jumps | {len(hierarchy_jumps)} |",
        f"| Suspected nested sibling entities | {len(entity_sibling_nested)} |",
        f"| Parent lead candidates | {len(parent_lead_candidates)} |",
        "",
        "## 3. Word/Section Distribution",
        "",
        "| Distribution | min | p25 | median | p75 | p90 | p95 | max |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for name, values in [
        ("Words/document", word_counts_doc),
        ("Sections/document", sections_per_doc),
        ("Words/section", section_word_counts),
    ]:
        report.append(
            f"| {name} | {min(values) if values else 0:.0f} | {percentile(values, 25):.0f} | "
            f"{percentile(values, 50):.0f} | {percentile(values, 75):.0f} | "
            f"{percentile(values, 90):.0f} | {percentile(values, 95):.0f} | "
            f"{max(values) if values else 0:.0f} |"
        )

    report.extend(
        [
            "",
            "## 4. Heading Source, Level, Language, Domain",
            "",
            "### Heading Source",
            table_counter(heading_source_counts),
            "",
            "### Heading Level",
            table_counter(heading_level_counts),
            "",
            "### Language",
            table_counter(language_counts),
            "",
            "### Domain",
            table_counter(domain_counts),
            "",
            "## 5. Các Nhóm Lỗi Cần Xử Lý",
            "",
            "### 5.1. Heading dài hoặc giống paragraph",
            "Các heading này thường là text được style đậm trên web, không nên mặc định coi là semantic boundary mạnh.",
            example_table(long_headings, ["heading_source"], 12),
            "",
            "### 5.2. Heading visual từ styled text / `<strong>`",
            "Visual heading có thể là heading thật về mặt hiển thị, nhưng cần phân loại role: entity, facet, topic hay noise.",
            example_table(visual_headings, ["heading_level"], 12),
            "",
            "### 5.3. Heading path chứa CTA/caption/noise",
            "Các node này cần bị loại khỏi hierarchy hoặc demote thành paragraph/caption trước khi build Parent/Child.",
            example_table(noise_path_rows, ["heading_path"], 12),
            "",
            "### 5.4. Entity sibling bị lồng sai",
            "Đây là lỗi nguy hiểm cho Parent-Child: hai entity cùng cấp bị hiểu nhầm thành cha-con.",
            example_table(entity_sibling_nested, ["suspected_parent", "heading_path"], 12),
            "",
            "### 5.5. Section ngắn cần cân nhắc merge",
            "Section ngắn dưới 40 từ thường không đủ ngữ nghĩa độc lập, nên merge theo cùng Parent nếu là facet/attribute.",
            example_table(short_sections, ["heading_source", "heading_path"], 12),
            "",
            "### 5.6. Section dài cần semantic split",
            "Section dài trên 450 từ cần split sau khi giữ nguyên semantic scope và source span.",
            example_table(long_sections, ["heading_source", "heading_path"], 12),
            "",
            "### 5.7. Candidate cho Parent `extractive_lead`",
            "Các section này có text đủ dài và có child descendants, phù hợp để lấy overview/lead text làm `context_summary`.",
            example_table(parent_lead_candidates, ["heading_path"], 12),
            "",
            "## 6. Review Set Đề Xuất",
            "",
            "Chọn 50 documents để review thủ công, ưu tiên tài liệu có anomaly và tài liệu nhiều section.",
            "",
            "| # | document_id | title | sections | url |",
            "|---:|---|---|---:|---|",
        ]
    )

    record_by_id = {document.get("document_id"): document for document in records}
    for index, document_id in enumerate(review_doc_ids, 1):
        document = record_by_id.get(document_id, {})
        title = str(document.get("title") or "").replace("|", "\\|")
        if len(title) > 80:
            title = title[:77] + "..."
        url = str(document.get("url") or "").replace("|", "\\|")
        report.append(
            f"| {index} | `{document_id}` | {title} | {len(document.get('sections') or [])} | {url} |"
        )

    checks = [
        "Thống kê document, section và word distribution.",
        "Thống kê `heading_source`, `heading_level`, language và domain.",
        "Tìm language bị thiếu.",
        "Tìm heading dài giống paragraph.",
        "Tìm heading visual từ `<strong>`/styled text.",
        "Tìm heading path chứa CTA/caption/noise.",
        "Tìm hierarchy sai do HTML heading level.",
        "Tìm entity sibling bị lồng sai thành parent-child.",
        "Tìm section ngắn cần cân nhắc merge.",
        "Tìm section dài cần semantic split.",
        "Chọn 40-60 documents làm tập review thủ công.",
        "Tạo gold sample có entity, facet, topic/section, visual heading và noise.",
    ]
    report.extend(
        [
            "",
            "## 7. Gold Sample",
            "",
            f"Đã tạo `{gold_path.as_posix()}` với {len(gold)} records. Các role có trong sample:",
            "",
            table_counter(Counter(item["expected_role"] for item in gold), 20),
            "",
            "Gold sample này dùng cho regression ở T03/T04/T05: validate boundary, role classification và hierarchy repair.",
            "",
            "## 8. Khuyến Nghị Cho Task Tiếp Theo",
            "",
            "- T02 nên chỉ normalize text/heading và gắn warning, chưa sửa hierarchy trực tiếp.",
            "- T03 cần boundary validator riêng cho visual heading, paragraph-like heading và noise path.",
            "- T04 cần role classifier phân biệt `entity`, `facet`, `category`, `topic`, `visual_heading`, `noise`.",
            "- T05 cần hierarchy repair để xử lý entity sibling bị nested sai, ví dụ `Skylight Nha Trang -> The Summit, Hanoi`.",
            "- Parent Builder T08 nên dùng `extractive_lead` từ direct text dưới heading cha làm `context_summary` mặc định cho article có cấu trúc.",
            "",
            "## 9. Checklist T01",
            "",
        ]
    )
    for check in checks:
        report.append(f"- [x] {check}")
    report.append("")

    report_path.write_text("\n".join(report), encoding="utf-8-sig")
    return {
        "documents": len(records),
        "sections": len(section_rows),
        "empty_sections": len(empty_sections),
        "short_sections_lt40": len(short_sections),
        "long_sections_gt450": len(long_sections),
        "visual_headings": len(visual_headings),
        "long_or_paragraph_like_headings": len(long_headings),
        "noise_path_rows": len(noise_path_rows),
        "nested_sibling_entities": len(entity_sibling_nested),
        "parent_lead_candidates": len(parent_lead_candidates),
        "review_docs": len(review_doc_ids),
        "gold_records": len(gold),
        "report": str(report_path),
        "gold": str(gold_path),
    }


def main():
    """Parse CLI arguments và chạy audit với đường dẫn người dùng truyền vào."""
    parser = argparse.ArgumentParser(description="Audit documents.jsonl for semantic chunking.")
    parser.add_argument("--input", default="data/documents.jsonl", help="Input JSONL path.")
    parser.add_argument(
        "--out-dir",
        default="hybrid_chunk_report",
        help="Output directory for audit report and gold sample.",
    )
    args = parser.parse_args()

    result = write_outputs(Path(args.input), Path(args.out_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
