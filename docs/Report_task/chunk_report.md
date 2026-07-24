# Báo Cáo Pipeline Chunking Parent-Child

Mục tiêu của pipeline là xây dựng dữ liệu chunk phục vụ Hybrid RAG theo hướng:

- `Parent` = một bài viết / một document.
- `Child` = các đoạn nội dung nhỏ bên trong bài, gắn với heading phía trên nó.
- `source_text` giữ nội dung gốc để làm evidence/citation.
- `retrieval_text` là text dẫn xuất có thêm title, heading, heading path để phục vụ BM25/vector retrieval.

Pipeline hiện tại là **document-parent + heading-aware paragraph/sentence chunking**. Đây chưa phải full semantic role chunking sâu theo entity/event/quote, nhưng đã giữ được cấu trúc bài viết tốt hơn fixed-size chunking.

## 0. Pipeline Tổng Thể

```text
data/documents.jsonl
        |
        v
Task 1 - Audit dữ liệu hiện tại
        |
        v
hybrid_chunk_report/semantic_data_audit.md
hybrid_chunk_report/semantic_structure_gold.jsonl
        |
        v
Task 2 - Clean heading và heading_path
        |
        v
data/document_clean.json
        |
        v
Task 3 - Build Document Parent
        |
        v
data/chunks/semantic_parents.jsonl
        |
        v
Task 4 - Build Children Chunks
        |
        v
data/chunks/semantic_children.jsonl
        |
        v
Task 5 - Chunk report / validation
        |
        v
hybrid_chunk_report/parent_child_chunk_report.md
```

Sau bước này mới đến retrieval:

```text
semantic_children.jsonl
-> BM25 index trên retrieval_text
-> Vector index trên retrieval_text
-> Hybrid retrieval
-> Parent expansion
-> LLM answer + citation từ source_text
```

## 1. Phân Tích Dữ Liệu

Dữ liệu đầu vào là:

```text
data/documents.jsonl
```

File có `281` document, tương ứng khoảng `281` bài viết/trang du lịch được crawl từ `vietnam.travel` và `2025.vietnam.travel`.

| Nhóm URL | Số document | Đặc điểm |
|---|---:|---|
| `things-to-do` | 211 | Bài gợi ý trải nghiệm, ẩm thực, văn hóa, hoạt động, nightlife |
| `places-to-go` | 22 | Trang điểm đến, tỉnh/thành, khu vực |
| `plan-your-trip` | 12 | Lịch trình, hướng dẫn lên kế hoạch, itinerary |
| URL tin tức tiếng Việt 2025 | 34 | Tin tức, sự kiện, kích cầu, xúc tiến du lịch địa phương |
| Khác | 2 | Trang ít cấu trúc hoặc không thuộc nhóm trên |

Phần lớn dữ liệu trong `things-to-do` và `places-to-go` có cấu trúc theo heading. Nhóm news tiếng Việt thường ít heading hơn, nhiều bài chỉ có một section dài.

### Cấu Trúc JSON Đầu Vào

Mỗi dòng trong `data/documents.jsonl` là một document:

```json
{
  "document_id": "...",
  "url": "https://vietnam.travel/...",
  "title": "...",
  "meta_description": "...",
  "language": "en",
  "source": "Vietnam Travel",
  "source_domain": "vietnam.travel",
  "raw_html_path": "data/raw_html/....html",
  "text": "full cleaned text",
  "sections": [
    {
      "section_index": 0,
      "heading": "...",
      "heading_level": 1,
      "heading_source": "document|semantic|visual|fallback",
      "heading_path": ["...", "..."],
      "text": "section body text",
      "word_count": 79
    }
  ]
}
```

## 2. Task 1 - Audit Dữ Liệu

**Đọc file** rag/preprocessing/clean_documents_sematics.py 

Mục tiêu là phát hiện vấn đề trước khi chunk.

Các vấn đề chính đã ghi nhận:

- Heading thật từ HTML và heading visual từ `<strong>`/bold paragraph không đồng bộ.
- Một số heading dài ở đầu bài thực chất là summary/lead paragraph.
- Một số `heading_path` chứa CTA/caption/noise như `Click the image below for a 360-degree tour`.
- Một số entity sibling bị lồng sai do heading level HTML, ví dụ rooftop bar này bị lồng dưới rooftop bar khác.
- News/bài viết ngắn có ít heading, cần xử lý theo paragraph/sentence.

### File Tạo Ra

```text
hybrid_chunk_report/semantic_data_audit.md
hybrid_chunk_report/semantic_structure_gold.jsonl
```

### Cấu Trúc JSON Gold Sample

`semantic_structure_gold.jsonl` dùng để review/regression cho các bước sau:

```json
{
  "document_id": "...",
  "section_index": 2,
  "heading": "Best for after-dinner drinks: The Summit, Hanoi",
  "expected_role": "entity",
  "expected_parent_heading": "7 stunning rooftop bars in Vietnam | Vietnam Tourism",
  "is_valid_boundary": true,
  "reason": "Suspected sibling entity nested under another entity.",
  "url": "https://vietnam.travel/..."
}
```

## 3. Task 2 - Clean Heading Và Heading Path

Input:

```text
data/documents.jsonl
```

Output:

```text
data/document_clean.json
```

Script:

```text
tools/clean_documents_semantic.py
```

Lệnh chạy:

```powershell
python tools/clean_documents_semantic.py --input data/documents.jsonl --output data/document_clean.json
```

### 3.1. Xử Lý Heading Dài / Giống Paragraph

Một số bài có đoạn lead/summary ở đầu bị parse nhầm thành heading. Với các heading này:

- Không dùng làm node hierarchy.
- Chuyển heading đó xuống `section.text`.
- Lưu lại trong `demoted_summary_text`.
- Dùng title bài làm heading thay thế.

Ví dụ trước clean:

```json
{
  "heading": "Great news for foodie travellers to Vietnam! MICHELIN Guide has finally arrived...",
  "heading_path": [
    "Love Vietnamese food, grab your MICHELIN Guide Hanoi & Ho Chi Minh City | Vietnam Tourism",
    "Great news for foodie travellers to Vietnam! MICHELIN Guide has finally arrived..."
  ],
  "text": "Taking place earlier this June..."
}
```

Sau clean:

```json
{
  "heading": "Love Vietnamese food, grab your MICHELIN Guide Hanoi & Ho Chi Minh City | Vietnam Tourism",
  "heading_source": "demoted_summary",
  "demoted_summary_text": "Great news for foodie travellers to Vietnam! MICHELIN Guide has finally arrived...",
  "text": "Great news for foodie travellers to Vietnam! MICHELIN Guide has finally arrived...\n\nTaking place earlier this June...",
  "heading_path": [
    "Love Vietnamese food, grab your MICHELIN Guide Hanoi & Ho Chi Minh City | Vietnam Tourism"
  ],
  "clean_actions": [
    "demote_paragraph_like_heading_to_summary_text"
  ]
}
```

### 3.2. Xử Lý CTA / Caption / Noise Trong Heading Path

Các node như:

```text
Click the image below for a 360-degree tour
Photo by...
Read more
For more information...
```

không bị dùng làm heading hierarchy. Pipeline remove chúng khỏi `heading_path`, đồng thời giữ provenance để audit.

Ví dụ trước clean:

```json
{
  "heading": "Cruise the bay",
  "heading_path": [
    "Ha Long | Vietnam Tourism",
    "Click the image below for a 360-degree tour",
    "Top things to do in Ha Long Bay",
    "Cruise the bay"
  ]
}
```

Sau clean:

```json
{
  "heading": "Cruise the bay",
  "heading_path": [
    "Ha Long | Vietnam Tourism",
    "Top things to do in Ha Long Bay",
    "Cruise the bay"
  ],
  "original_heading_path": [
    "Ha Long | Vietnam Tourism",
    "Click the image below for a 360-degree tour",
    "Top things to do in Ha Long Bay",
    "Cruise the bay"
  ],
  "removed_heading_path_nodes": [
    "Click the image below for a 360-degree tour"
  ],
  "clean_actions": [
    "remove_noise_from_heading_path"
  ]
}
```

### Cấu Trúc JSON `document_clean.json`

`document_clean.json` là JSON array:

```json
[
  {
    "document_id": "...",
    "url": "...",
    "title": "...",
    "meta_description": "...",
    "language": "en",
    "source_domain": "vietnam.travel",
    "text": "original full text",
    "clean_text": "rebuilt clean text",
    "sections": [
      {
        "section_index": 1,
        "heading": "Cruise the bay",
        "heading_level": 4,
        "heading_source": "visual",
        "heading_path": ["Ha Long | Vietnam Tourism", "Top things to do in Ha Long Bay", "Cruise the bay"],
        "text": "Nothing beats spending watching the sun set...",
        "word_count": 41,
        "original_heading_path": ["..."],
        "removed_heading_path_nodes": ["Click the image below for a 360-degree tour"],
        "clean_actions": ["remove_noise_from_heading_path"]
      }
    ],
    "cleaning_metadata": {
      "pipeline": "semantic_document_clean_v1",
      "handled_issues": [
        "paragraph_like_heading_at_article_start",
        "cta_caption_noise_in_heading_path"
      ],
      "stats": {
        "path_noise_removed": 1
      }
    }
  }
]
```

Kết quả hiện tại:

```text
documents: 281
demoted_paragraph_like_heading: 20
path_noise_removed: 72
sections_with_path_noise: 72
noise_heading_marked: 13
```

## 4. Task 3 - Xây Dựng Parent
**Đọc file** rag/chunking/build_document_parent_child_chunks.py 


Input:

```text
data/document_clean.json
```

Output:

```text
data/chunks/semantic_parents.jsonl
```

Script:

```text
tools/build_document_parent_child_chunks.py
```

Thiết kế hiện tại:

- Mỗi bài viết là một Parent.
- Parent không lưu toàn bộ nội dung bài viết.
- Parent lưu summary, metadata, provenance và danh sách `child_ids`.
- `context_summary` ưu tiên lấy paragraph đầu tiên trước khi gặp heading tiếp theo, thường là `sections[0].text`.
- Với news/bài ít cấu trúc, summary lấy từ paragraph đầu trong section đầu tiên.

### Cấu Trúc JSON Parent

Mỗi dòng trong `semantic_parents.jsonl` là một Parent:

```json
{
  "schema_version": "1.0",
  "parent_id": "{document_id}:parent:document",
  "document_id": "...",
  "parent_parent_id": null,
  "parent_granularity": "document",
  "node_type": "document",
  "title": "7 stunning rooftop bars in Vietnam | Vietnam Tourism",
  "clean_title": "7 stunning rooftop bars in Vietnam",
  "heading": "7 stunning rooftop bars in Vietnam | Vietnam Tourism",
  "heading_path": [
    "7 stunning rooftop bars in Vietnam | Vietnam Tourism"
  ],
  "context_summary": "When it comes to rooftop bars, Vietnam is up there with the best in Asia...",
  "summary_type": "extractive_lead",
  "summary_source_spans": [
    {
      "section_index": 0,
      "char_start": 0,
      "char_end": 430
    }
  ],
  "summary_model": null,
  "source_section_indexes": [0, 1, 2, 3],
  "child_ids": [
    "{document_id}:child:0000:00",
    "{document_id}:child:0001:00"
  ],
  "metadata": {
    "document_type": "listicle_or_guide",
    "language": "en",
    "source": "Vietnam Travel",
    "source_domain": "vietnam.travel",
    "source_url": "https://vietnam.travel/...",
    "raw_html_path": "data/raw_html/....html"
  },
  "expandable": true,
  "pipeline_version": "document-parent-child-v1"
}
```

## 5. Task 4 - Xây Dựng Children

Input:

```text
data/document_clean.json
data/chunks/semantic_parents.jsonl
```

Output:

```text
data/chunks/semantic_children.jsonl
```

Thiết kế hiện tại:

- Child được tạo từ `sections[].text`.
- Heading phía trên section được lưu vào `heading` và `heading_path`.
- Heading/path được đưa vào `retrieval_text` để embedding và BM25 sử dụng.
- `source_text` chỉ chứa nội dung gốc từ section text, không tự nhét heading vào source evidence.
- Section dài được split theo paragraph, nếu paragraph quá dài thì split tiếp theo sentence.
- Các unit nhỏ được gom lại theo chunk size.

Config hiện tại:

```text
summary_max_words = 120
target_child_words = 220
max_child_words = 360
min_child_words = 40
```

Kết quả hiện tại:

```text
parents: 281
children: 1844
overview children: 281
section children: 1411
split_part children: 152
max child word_count: 351
```

### Cấu Trúc JSON Child

Mỗi dòng trong `semantic_children.jsonl` là một Child:

```json
{
  "schema_version": "1.0",
  "child_id": "{document_id}:child:0001:00",
  "document_id": "...",
  "parent_id": "{document_id}:parent:document",
  "child_index": 1,
  "section_index": 1,
  "section_chunk_index": 0,
  "child_type": "overview|section|split_part",
  "heading": "Cruise the bay",
  "heading_path": [
    "Ha Long | Vietnam Tourism",
    "Top things to do in Ha Long Bay",
    "Cruise the bay"
  ],
  "source_spans": [
    {
      "section_index": 1,
      "char_start": 0,
      "char_end": 255
    }
  ],
  "source_joiner": "\n\n",
  "source_text": "Nothing beats spending watching the sun set...",
  "retrieval_text": "Article: Ha Long\nSection: Cruise the bay\nHeading path: Ha Long | Vietnam Tourism > Top things to do in Ha Long Bay > Cruise the bay\nSource: https://vietnam.travel/...\nLanguage: en\n\nNothing beats spending watching the sun set...",
  "metadata": {
    "document_type": "structured_article",
    "language": "en",
    "source_domain": "vietnam.travel",
    "source_url": "https://vietnam.travel/...",
    "heading_source": "visual",
    "heading_level": 4
  },
  "word_count": 41,
  "previous_child_id": "{document_id}:child:0000:00",
  "next_child_id": "{document_id}:child:0002:00",
  "pipeline_version": "document-parent-child-v1"
}
```

## 6. Task 5 - Report Và Validation

Output:

```text
hybrid_chunk_report/parent_child_chunk_report.md
```

Validation hiện tại:

```text
Parents: 281
Children: 1844
Child mồ côi parent: 0
Child source_text rỗng: 0
heading_path còn "Click the image below...": 0
```

Report chunk hiện có cấu trúc:

```json
{
  "input": "data/document_clean.json",
  "parent_output": "data/chunks/semantic_parents.jsonl",
  "child_output": "data/chunks/semantic_children.jsonl",
  "documents": 281,
  "parents": 281,
  "children": 1844,
  "child_type_counts": {
    "overview": 281,
    "section": 1411,
    "split_part": 152
  },
  "child_word_count": {
    "min": 1,
    "max": 351,
    "avg": 109.86
  }
}
```

## 7. Heading Được Dùng Như Thế Nào

Heading không được nhét vào `source_text`, vì `source_text` cần giữ nguyên văn từ `sections[].text` để làm citation.

Heading được dùng ở các chỗ:

- `heading`: label trực tiếp của Child.
- `heading_path`: hierarchy context của Child.
- `retrieval_text`: text dùng cho BM25/vector embedding.
- Context builder/prompt sau này có thể hiển thị heading kèm source text.

Ví dụ:

```text
source_text:
Nothing beats spending watching the sun set over the calm waters of Ha Long Bay...

retrieval_text:
Article: Ha Long
Section: Cruise the bay
Heading path: Ha Long | Vietnam Tourism > Top things to do in Ha Long Bay > Cruise the bay

Nothing beats spending watching the sun set over the calm waters of Ha Long Bay...
```

## 8. Giới Hạn Hiện Tại

Pipeline hiện tại chưa làm full semantic role labeling.

Nó đã có:

- document boundary;
- heading-aware section boundary;
- paragraph boundary;
- sentence fallback;
- parent summary từ lead paragraph;
- provenance bằng source spans.

Nó chưa có:

- phân loại role news như `lead`, `background`, `quote`, `tourism_impact`;
- entity-level Parent;
- facet grouping sâu như `best_time`, `how_to_get_there`, `tips`;
- LLM labeling cho low-confidence paragraph.

Do đó nên gọi pipeline hiện tại là:

```text
Document-parent heading-aware paragraph/sentence chunking
```

Không nên gọi là full semantic chunking hoàn chỉnh.
