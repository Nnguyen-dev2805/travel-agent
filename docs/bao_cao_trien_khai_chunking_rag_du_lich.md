# Báo cáo thiết kế và triển khai Chunking cho Chatbot Du lịch sử dụng RAG

## 1. Mục tiêu

Mục tiêu của giai đoạn chunking là chuyển các tài liệu du lịch đã được làm sạch từ HTML thành các đơn vị tri thức nhỏ, có cấu trúc và phù hợp cho:

- tìm kiếm bằng BM25;
- tìm kiếm vector;
- lọc bằng metadata;
- reranking;
- mở rộng ngữ cảnh theo parent–child;
- sinh câu trả lời có nguồn tham chiếu rõ ràng.

Dữ liệu đầu vào không còn là văn bản tự do mà là các tài liệu bán cấu trúc, thường gồm:

```text
Document title
    └── Section heading
            └── Paragraph / list / content block
```

Vì vậy, chiến lược chunking nên ưu tiên cấu trúc tự nhiên của tài liệu trước khi sử dụng semantic chunking.

---

## 2. Nguyên tắc thiết kế

### 2.1. Không sử dụng một chiến lược chunking duy nhất

Dữ liệu du lịch có nhiều loại tài liệu khác nhau:

- bài danh sách địa điểm;
- bài hướng dẫn điểm đến;
- lịch trình du lịch;
- bài báo hoặc tin tức;
- bài về ẩm thực;
- bài sự kiện;
- bài tổng quan tỉnh thành.

Mỗi loại tài liệu có cấu trúc và đơn vị tri thức khác nhau. Do đó, hệ thống cần chọn chiến lược chunking dựa trên cấu trúc của từng document.

### 2.2. Thứ tự ưu tiên boundary

Thứ tự ưu tiên khi xác định ranh giới chunk:

```text
Document boundary
→ Heading/section boundary
→ Entity boundary
→ Itinerary day boundary
→ Semantic boundary
→ Token limit
```

Các boundary ở cấp cao hơn không được phép bị phá vỡ bởi semantic chunking hoặc token-based chunking.

### 2.3. Vai trò của title và heading

```text
Title   → xác định phạm vi hoặc chủ đề toàn document
Heading → xác định chủ đề cục bộ hoặc entity
Content → cung cấp facts và bằng chứng
```

Ví dụ:

```text
Title:
5 unique towns in the Mekong Delta

Heading:
Can Tho
```

Trong trường hợp này:

- title tạo semantic namespace: các thị trấn tại Đồng bằng sông Cửu Long;
- heading xác định entity cụ thể: Cần Thơ;
- nội dung trong section mô tả facts của entity đó.

Tuy nhiên, title không phải lúc nào cũng là một entity cụ thể. Title có thể là:

- entity;
- collection;
- destination scope;
- itinerary name;
- chủ đề bài viết.

---

## 3. Phân loại cấu trúc tài liệu

Thay vì chỉ dựa vào loại bài viết, hệ thống nên đánh giá độ mạnh của cấu trúc.

### 3.1. Strong structure

Đặc điểm:

```text
Title
→ nhiều heading ngắn
→ mỗi heading có một nhóm paragraph rõ ràng
```

Ví dụ:

- danh sách rooftop bar;
- danh sách món ăn;
- danh sách spa;
- danh sách địa điểm;
- danh sách thị trấn.

Chiến lược:

```text
Chunk theo heading hoặc entity
```

### 3.2. Medium structure

Đặc điểm:

```text
Title
→ heading rõ
→ một số section rất dài
```

Ví dụ:

- destination guide;
- city guide;
- bài tổng quan tỉnh thành;
- bài “things to do”.

Chiến lược:

```text
Chunk theo heading
→ semantic split bên trong section dài
```

### 3.3. Weak structure

Đặc điểm:

```text
Title
→ một section lớn
→ nhiều paragraph liên tiếp
→ ít hoặc không có heading
```

Ví dụ:

- bài báo;
- bài tin tức;
- bài phân tích;
- bài phỏng vấn.

Chiến lược:

```text
Semantic chunk theo nhóm paragraph
```

---

## 4. Pipeline tổng thể

```text
Raw HTML
    ↓
Main content extraction
    ↓
Clean document
    ↓
Structural normalization
    ↓
Document structure analysis
    ↓
Chunk strategy selection
    ↓
Parent creation
    ↓
Child chunk creation
    ↓
Metadata enrichment
    ↓
BM25 index + Vector index
    ↓
Retrieval evaluation
```

---

## 5. Chuẩn hóa dữ liệu trước khi chunking

Chunking chỉ hiệu quả khi cấu trúc đầu vào đủ chính xác.

### 5.1. Sửa heading bị nhận sai

Một số đoạn introduction dài có thể bị extractor nhận thành heading. Các đoạn này nên được chuyển thành:

```json
{
  "lead": [
    {
      "type": "paragraph",
      "text": "..."
    }
  ]
}
```

Không đưa đoạn introduction dài vào `heading_path`.

### 5.2. Chuẩn hóa itinerary

Các marker như:

```text
DAY 1
DAY 2
DAY 3
```

không nên nằm trong paragraph của ngày trước.

Cần chuyển thành metadata:

```json
{
  "day_number": 2,
  "heading": "Hanoi city highlights"
}
```

Các section như:

```text
Route
Highlights
```

nên chuyển thành metadata document thay vì tạo retrieval chunk độc lập.

### 5.3. Loại nội dung nhiễu

Các nội dung không phục vụ QA du lịch nên bị loại khỏi embedding text:

- photo credit;
- author credit không cần thiết;
- newsletter;
- navigation;
- copyright;
- quảng cáo;
- boilerplate.

Có thể giữ lại trong metadata nếu cần truy vết nguồn.

### 5.4. Chuẩn hóa ngôn ngữ

Mỗi document nên có:

```json
"language": "en"
```

hoặc:

```json
"language": "vi"
```

Điều này hỗ trợ embedding đa ngôn ngữ và query routing.

---

## 6. Chiến lược chunking theo loại tài liệu

## 6.1. Listicle hoặc entity collection

Ví dụ:

- 7 rooftop bars in Vietnam;
- 5 unique towns in the Mekong Delta;
- best wellness experiences;
- top restaurants;
- must-visit attractions.

### Đơn vị chunk tự nhiên

```text
Một heading đại diện một entity
```

Ví dụ:

```text
Document:
7 stunning rooftop bars in Vietnam

Section:
Sky 36, Da Nang
```

Section này nên được xem là parent của entity `Sky 36`.

### Rule

```text
Section ≤ 350 tokens
→ giữ nguyên thành một child chunk

Section > 350–450 tokens
→ chia theo paragraph hoặc semantic boundary

Không merge hai entity khác nhau
```

### Ví dụ

```json
{
  "entity_name": "Sky 36",
  "entity_type": "rooftop_bar",
  "location": "Da Nang",
  "parent_text": "...",
  "child_chunks": [
    {
      "chunk_type": "entity_content",
      "source_text": "..."
    }
  ]
}
```

---

## 6.2. Itinerary

Ví dụ:

- Vietnam In Depth;
- Heritage Sites of Vietnam;
- 10-day central Vietnam itinerary.

### Đơn vị parent

```text
Một ngày hoặc một chặng hành trình
```

Ví dụ:

```text
Day 5 — Ninh Binh exploration
```

### Rule

```text
Day ≤ 400 tokens
→ một ngày = một child chunk

Day > 400 tokens
→ chia theo activity hoặc location

Activity > 450 tokens
→ semantic split bên trong activity
```

### Boundary bắt buộc

Không cho phép chunk:

- chứa nội dung của hai ngày khác nhau;
- trộn hai route khác nhau;
- tách marker ngày khỏi nội dung ngày;
- merge ngày ngắn với ngày kế tiếp.

### Ví dụ hierarchy

```text
Day 5 — Ninh Binh
    ├── Trang An boat trip
    ├── Hang Mua viewpoint
    └── Overnight in Ninh Binh
```

---

## 6.3. Destination guide

Ví dụ:

- Ninh Binh travel guide;
- things to do in Da Nang;
- wellness in Nha Trang;
- food guide to Hue.

### Đơn vị parent

Mỗi aspect hoặc heading lớn:

```text
Overview
Things to do
Food
Transport
Weather
Accommodation
```

### Rule

```text
Section ≤ 350 tokens
→ giữ nguyên

Section > 350–450 tokens
→ chia theo entity nếu có

Không có entity rõ
→ semantic split trong section
```

### Ví dụ

```text
Food
    ├── Bun bo Hue
    ├── Com hen
    └── Banh khoai
```

Nếu heading con là tên món ăn, mỗi món ăn trở thành entity chunk.

---

## 6.4. News article hoặc bài báo ít cấu trúc

Ví dụ:

- tin tức du lịch;
- bài báo về đoàn làm phim;
- bài phân tích xu hướng;
- bài sự kiện dài không có heading.

### Chiến lược

```text
Paragraph grouping
→ semantic similarity
→ topic boundary detection
→ token control
```

### Cấu hình khởi đầu

```yaml
target_tokens: 250
min_tokens: 120
max_tokens: 450
overlap_tokens: 30
```

### Rule

- không cắt giữa câu;
- ưu tiên giữ nguyên paragraph;
- chỉ dùng overlap khi semantic segment bị chia;
- lưu `previous_chunk_id` và `next_chunk_id`;
- không semantic split vượt document boundary.

### Ví dụ topic segment

```text
Chunk 1: Bối cảnh sự kiện
Chunk 2: Nội dung hợp tác
Chunk 3: Tiềm năng điểm đến
Chunk 4: Ảnh hưởng đến du lịch
Chunk 5: Kế hoạch tiếp theo
```

---

## 7. Parent–child chunking

Parent–child là kiến trúc phù hợp nhất với chatbot du lịch.

### 7.1. Parent

Parent đại diện cho một đơn vị cấu trúc lớn:

- entity section;
- itinerary day;
- aspect;
- article section;
- route.

Parent giữ toàn bộ context và dùng để:

- mở rộng context;
- trả lời câu hỏi tổng quát;
- citation;
- giữ quan hệ giữa các child.

### 7.2. Child

Child là đơn vị nhỏ dùng để:

- BM25;
- embedding;
- vector retrieval;
- reranking.

Ví dụ:

```text
Parent:
Day 5 — Ninh Binh

Children:
- Trang An boat trip
- Hang Mua viewpoint
- Overnight information
```

### 7.3. Retrieval flow

```text
Query
→ retrieve child
→ rerank
→ mở rộng parent nếu cần
→ đưa context vào LLM
```

Không phải query nào cũng cần lấy toàn bộ parent. Parent expansion chỉ nên được dùng khi child thiếu ngữ cảnh.

---

## 8. Cấu trúc lưu trữ

Nên lưu tối thiểu ba tầng:

```text
documents.jsonl
parents.jsonl
chunks.jsonl
```

---

## 8.1. Document schema

```json
{
  "document_id": "doc_001",
  "source_url": "https://vietnam.travel/...",
  "domain": "vietnam.travel",

  "raw_title": "...",
  "clean_title": "...",

  "document_type": "listicle",
  "structure_type": "strong",
  "structure_score": 0.92,

  "main_scope": "Vietnam rooftop bars",
  "language": "en",

  "lead": [
    {
      "type": "paragraph",
      "text": "..."
    }
  ],

  "sections": [
    {
      "section_id": "doc_001_sec_001",
      "heading": "...",
      "heading_level": 2,
      "heading_path": ["...", "..."],
      "blocks": [
        {
          "type": "paragraph",
          "text": "..."
        }
      ]
    }
  ],

  "metadata": {
    "route": [],
    "highlights": [],
    "published_at": null,
    "updated_at": null
  }
}
```

---

## 8.2. Parent schema

```json
{
  "parent_id": "doc_001_sec_001",
  "document_id": "doc_001",

  "document_title": "...",
  "document_type": "listicle",

  "parent_type": "entity_section",

  "heading": "...",
  "heading_path": ["...", "..."],

  "entity": {
    "name": "Sky 36",
    "entity_type": "rooftop_bar"
  },

  "locations": [
    "Da Nang",
    "Vietnam"
  ],

  "day_number": null,

  "parent_text": "...",
  "token_count": 280,

  "source_url": "...",
  "language": "en"
}
```

---

## 8.3. Child chunk schema

```json
{
  "chunk_id": "doc_001_sec_001_chunk_001",
  "parent_id": "doc_001_sec_001",
  "document_id": "doc_001",

  "chunk_index": 0,
  "chunk_type": "entity_content",

  "document_title": "...",
  "document_type": "listicle",

  "heading": "...",
  "heading_path": ["...", "..."],

  "entity_name": "Sky 36",
  "entity_type": "rooftop_bar",

  "locations": [
    "Da Nang",
    "Vietnam"
  ],

  "day_number": null,

  "source_text": "...",
  "retrieval_text": "...",

  "token_count": 270,

  "previous_chunk_id": null,
  "next_chunk_id": null,

  "source_url": "...",
  "language": "en"
}
```

---

## 9. Retrieval text

Không embedding toàn bộ JSON.

Chỉ embedding trường:

```text
retrieval_text
```

### Template đề xuất

```text
Document: {document_title}
Section: {heading}
Entity: {entity_name}
Location: {locations}
Document type: {document_type}

{source_text}
```

Ví dụ:

```text
Document: 7 stunning rooftop bars in Vietnam
Section: Best for river views: Sky 36, Da Nang
Entity: Sky 36
Location: Da Nang, Vietnam
Document type: listicle

Vietnam’s central city of Da Nang...
```

### Phân biệt hai trường

```text
source_text
→ nội dung nguyên bản, dùng cho LLM và citation

retrieval_text
→ nội dung giàu context, dùng cho BM25 và embedding
```

---

## 10. Cấu hình chunking khởi đầu

```yaml
chunking:
  min_child_tokens: 80
  target_child_tokens: 250
  short_section_max_tokens: 350
  max_child_tokens: 450
  overlap_tokens: 30

boundaries:
  allow_cross_document: false
  allow_cross_section: false
  allow_cross_entity: false
  allow_cross_day: false

strategies:
  listicle: heading_entity
  itinerary: day_then_activity
  destination_guide: heading_then_semantic
  news_article: semantic_paragraph

parent_child:
  enabled: true
  retrieve_children: true
  expand_parent_when_needed: true
```

Các threshold trên chỉ là cấu hình ban đầu. Cần điều chỉnh bằng retrieval evaluation.

---

## 11. Logic chọn chunker

Pseudo-code:

```python
def select_chunk_strategy(document):
    structure_score = calculate_structure_score(document)

    if document.document_type == "itinerary":
        return ItineraryChunker()

    if structure_score >= 0.8:
        return HeadingEntityChunker()

    if structure_score >= 0.5:
        return HeadingSemanticChunker()

    return SemanticParagraphChunker()
```

### Structure score có thể dựa trên

- số heading;
- tỷ lệ heading/paragraph;
- độ dài heading;
- số block trong mỗi section;
- độ cân bằng giữa các section;
- tỷ lệ section rỗng;
- tỷ lệ đoạn intro bị nhận nhầm;
- mức độ lặp heading;
- sự tồn tại của marker ngày.

---

## 12. Kế hoạch triển khai

## Giai đoạn 1: Chuẩn hóa document

Thực hiện:

1. sửa heading bị nhận sai;
2. parse `DAY N`;
3. chuyển `Route` và `Highlights` thành metadata;
4. loại boilerplate;
5. thêm `document_type`;
6. thêm `structure_type`;
7. validate JSONL.

Đầu ra:

```text
normalized_documents.jsonl
```

---

## Giai đoạn 2: Xây baseline

Triển khai ba baseline.

### Baseline A: Fixed-size

```text
300 tokens
50 tokens overlap
```

Mục đích là làm mốc so sánh.

### Baseline B: Structural chunking

```text
Listicle      → heading/entity
Itinerary     → day
Guide         → heading
News          → paragraph group
```

### Baseline C: Hybrid chunking

```text
Structural boundary
+ semantic split section dài
+ parent–child
```

Đầu ra:

```text
chunks_fixed.jsonl
chunks_structural.jsonl
chunks_hybrid.jsonl
```

---

## Giai đoạn 3: Indexing

Tạo:

```text
BM25 index
Vector index
Metadata index
```

Metadata dùng để filter:

- document type;
- entity;
- location;
- aspect;
- day number;
- language;
- source domain.

---

## Giai đoạn 4: Evaluation

Tạo tập câu hỏi kiểm thử.

### Entity query

```text
Sky 36 nằm ở đâu?
Spa nào ở Nha Trang?
Can Tho có hoạt động gì?
```

### Itinerary query

```text
Ngày thứ hai đi đâu?
Ngày nào ghé Ninh Bình?
Lịch trình tại Huế có gì?
```

### Aspect query

```text
Món ăn nổi bật ở Huế là gì?
Có rooftop bar nào nhìn ra sông?
```

### Broad query

```text
Những điểm đến nào có trong hành trình?
Tóm tắt các thị trấn ở Mekong Delta.
```

### Metric

```text
Recall@K
MRR
nDCG@K
Context precision
Entity accuracy
Day accuracy
Answer faithfulness
```

Ngoài metric tự động, cần kiểm tra thủ công:

- chunk có trộn entity không;
- chunk có vượt ngày không;
- retrieved context có đủ trả lời không;
- chunk có quá nhiều thông tin dư không;
- title và heading có được giữ đúng không.

---

## 13. Cấu trúc thư mục đề xuất

```text
data/
├── raw/
│   ├── crawl_metadata.jsonl
│   └── html/
│
├── processed/
│   ├── clean_documents.jsonl
│   ├── normalized_documents.jsonl
│   └── rejected_documents.jsonl
│
├── chunks/
│   ├── parents.jsonl
│   ├── chunks_fixed.jsonl
│   ├── chunks_structural.jsonl
│   └── chunks_hybrid.jsonl
│
├── indexes/
│   ├── bm25/
│   ├── vector/
│   └── metadata/
│
├── evaluation/
│   ├── queries.jsonl
│   ├── ground_truth.jsonl
│   └── retrieval_results.jsonl
│
└── configs/
    ├── preprocessing.yaml
    ├── chunking.yaml
    └── retrieval.yaml
```

---

## 14. Kết luận

Chiến lược chunking phù hợp nhất cho chatbot du lịch là:

```text
Structure-aware
+ Entity-aware
+ Itinerary-aware
+ Parent–child
+ Semantic split có điều kiện
```

Quy tắc chính:

```text
Listicle
→ một entity heading = một parent/chunk

Itinerary
→ một ngày = một parent
→ ngày dài chia theo activity hoặc location

Destination guide
→ một heading/aspect = một parent
→ section dài mới semantic split

News article
→ semantic chunk theo nhóm paragraph
```

Semantic chunking không nên được áp dụng trên toàn bộ corpus hoặc toàn bộ document có cấu trúc mạnh.

Tư tưởng cốt lõi:

> Cấu trúc quyết định nơi được phép chunk. Semantic similarity chỉ quyết định điểm chia bên trong một cấu trúc đã được xác định.

Thiết kế này giúp hệ thống:

- giữ đúng entity;
- tránh trộn thông tin;
- tăng retrieval precision;
- hỗ trợ metadata filtering;
- dễ citation;
- dễ cập nhật dữ liệu;
- phù hợp để mở rộng sang Agentic RAG hoặc GraphRAG sau này.
