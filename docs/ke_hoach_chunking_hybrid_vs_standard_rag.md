# Kế Hoạch Chunking Cho RAG Du Lịch Việt Nam

## 1. Mục Tiêu

Mục tiêu của kế hoạch này là thiết kế chiến lược chunking phù hợp với dữ liệu du lịch Việt Nam đã được làm sạch từ HTML, nhằm phục vụ hệ thống Chatbot Du lịch sử dụng RAG.

Trọng tâm không phải là chia văn bản thành các đoạn có kích thước đều nhau, mà là tạo ra các **đơn vị tri thức có nghĩa**, có metadata rõ ràng và phù hợp cho:

- BM25 retrieval;
- vector retrieval;
- metadata filtering;
- reranking;
- parent-child retrieval;
- sinh câu trả lời có citation;
- mở rộng sau này sang Agentic RAG, Adaptive RAG hoặc GraphRAG.

## 2. Hiện Trạng Dữ Liệu

Dữ liệu đầu vào chính là file:

```text
data/clean_documents_full.jsonl
```

Tổng quan dữ liệu:

| Thống kê dữ liệu | Giá trị / Quan sát |
|---|---|
| Tổng số document | 281 |
| JSON hợp lệ | 281/281 |
| Trùng `document_id` | 0 |
| Trùng `url` | 0 |
| Trùng `plain_text` | 0 |
| Document thiếu `meta_description` | 38 |
| Section rỗng | 322 |
| Heading dài hơn 180 ký tự | 228 |
| Median sections/document | 5 |
| Median words/document | 784 |
| Nguồn chính | `vietnam.travel`, `2025.vietnam.travel` |

Nhận xét:

- Dữ liệu đã sạch tốt về mặt kỹ thuật.
- Không còn HTML thô trong `plain_text`.
- Cấu trúc `document -> sections -> blocks` đã đủ tốt để làm pre-chunk document.
- Tuy nhiên, chưa nên embedding trực tiếp vì còn heading nhiễu, section rỗng và metadata chưa chuẩn hóa đầy đủ.

## 3. Vấn Đề Của Standard RAG Chunking

Baseline `Standard RAG` thường dùng chiến lược:

```text
Document text
→ chia theo fixed-size chunk, ví dụ 300-500 tokens
→ overlap 30-100 tokens
→ embedding
→ vector search
→ LLM answer
```

Ví dụ cấu hình baseline:

```yaml
standard_rag:
  chunk_size: 500
  chunk_overlap: 50
  split_by: token_or_character
  metadata:
    - document_id
    - source_url
```

Cách này dễ triển khai nhưng có nhiều hạn chế với dữ liệu du lịch:

| Vấn đề | Tác động |
|---|---|
| Có thể cắt ngang section | Mất ngữ cảnh tự nhiên của nội dung |
| Có thể trộn nhiều entity | Retriever trả về chunk chứa nhiều địa điểm/món ăn khác nhau |
| Không hiểu itinerary day boundary | Có thể trộn ngày 1 với ngày 2 |
| Không tận dụng heading | Mất tín hiệu semantic quan trọng |
| Metadata nghèo | Khó filter theo tỉnh/thành, category, activity |
| Citation kém rõ | Khó biết câu trả lời đến từ section nào |
| Retrieval precision thấp hơn | Query cụ thể dễ lấy nhầm đoạn rộng hoặc nhiễu |

Standard RAG phù hợp làm baseline để so sánh, nhưng không nên là chiến lược chính cho hệ thống du lịch.

## 4. Nguyên Tắc Chunking Đề Xuất

Nguyên tắc cốt lõi:

```text
Meaning > Structure > Token
```

Thứ tự ưu tiên boundary:

```text
Document boundary
→ Heading/section boundary
→ Entity boundary
→ Itinerary day boundary
→ Activity/aspect boundary
→ Semantic boundary
→ Token limit
```

Không để token limit phá vỡ các boundary quan trọng như document, entity, section hoặc itinerary day.

## 5. Mapping Dữ Liệu Thực Tế Sang Chiến Lược Chunking

| Đặc điểm dữ liệu | Cấu trúc nhận diện | Chiến lược chunking | Độ phù hợp | Điều kiện triển khai |
|---|---|---|---|---|
| Document có nhiều heading, mỗi heading mô tả một địa điểm/đối tượng | Strong Structure / Entity Collection | Chunk theo Heading/Entity | Rất cao | Cần sửa heading dài bị nhầm paragraph |
| Document mô tả một điểm đến với nhiều khía cạnh | Destination Guide | Chunk theo Heading/Aspect, semantic split nếu section dài | Rất cao | Cần chuẩn hóa aspect/category |
| Document chia theo Day hoặc Route | Itinerary | Chunk theo Day -> Activity | Rất cao | Cần parse `DAY N`, route, highlights |
| Document có rất ít heading, chủ yếu là paragraph liên tục | Weak Structure / News Article | Semantic Paragraph Chunking | Cao | Cần topic boundary detection |
| Median 5 sections/document | Section là boundary tự nhiên | Dùng section làm parent candidate | Rất cao | Cần bỏ section rỗng |
| Median 784 words/document | Độ dài vừa phải | Không cần fixed-size chunking toàn document | Rất cao | Chỉ split khi section quá dài |

## 6. Chiến Lược Chunking Chính

Chiến lược đề xuất:

```text
Structure-aware
+ Entity-aware
+ Itinerary-aware
+ Parent-child
+ Semantic split có điều kiện
```

Pipeline tổng thể:

```text
Clean Document
→ Structure Normalization
→ Structure Validation
→ Document Type Classification
→ Entity/Location/Aspect Extraction
→ Knowledge Unit Creation
→ Parent Creation
→ Child Chunk Creation
→ Metadata Enrichment
→ Chunk Quality Validation
→ BM25 Index + Vector Index
→ Retrieval Evaluation
```

## 7. Bước 1: Structure Normalization

Trước khi chunk, cần chuẩn hóa lại cấu trúc document.

### 7.1. Sửa heading bị nhận nhầm

Một số paragraph mở đầu đang bị nhận nhầm thành heading. Cần chuyển các heading này thành `lead` hoặc paragraph.

Rule gợi ý:

- Nếu heading dài hơn 160-180 ký tự và không có block, khả năng cao là paragraph mở đầu.
- Nếu heading có nhiều hơn 2 câu, khả năng cao là paragraph.
- Nếu heading kết thúc bằng dấu chấm và có độ dài lớn, cần kiểm tra lại.
- Không đưa intro paragraph dài vào `heading_path`.

Đầu ra mong muốn:

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

### 7.2. Loại section rỗng khỏi chunking

Section không có block không nên tạo chunk độc lập.

Có thể giữ section rỗng trong document gốc để trace, nhưng chunker phải bỏ qua khi tạo parent/child.

### 7.3. Chuẩn hóa language

Chuẩn hóa:

```json
"language": "en"
```

hoặc:

```json
"language": "vi"
```

Không nên để `language = None` khi đưa vào index.

## 8. Bước 2: Document Type Classification

Mỗi document cần được gán `document_type`.

Các loại chính:

| Document type | Dấu hiệu | Chunker |
|---|---|---|
| `listicle` | Nhiều heading ngắn, mỗi heading là một entity | HeadingEntityChunker |
| `destination_guide` | Một điểm đến, nhiều aspect | HeadingAspectChunker |
| `itinerary` | Có `DAY N`, route, lịch trình | ItineraryChunker |
| `news_article` | Ít heading, paragraph liên tục | SemanticParagraphChunker |
| `event_article` | Tin/sự kiện du lịch | SemanticParagraphChunker |
| `infographic` | Nội dung ngắn, ít text | LowContentHandler |

Pseudo-code:

```python
def select_chunk_strategy(document):
    document_type = classify_document_type(document)
    structure_score = calculate_structure_score(document)

    if document_type == "itinerary":
        return ItineraryChunker()

    if document_type == "listicle" and structure_score >= 0.7:
        return HeadingEntityChunker()

    if document_type == "destination_guide":
        return HeadingAspectChunker()

    if structure_score < 0.5:
        return SemanticParagraphChunker()

    return HeadingSemanticChunker()
```

## 9. Bước 3: Knowledge Unit Creation

Không nên xem chunk chỉ là đoạn text. Trước tiên nên tạo **knowledge unit**, tức là một đơn vị tri thức có nghĩa.

Ví dụ:

```text
Document: 7 stunning rooftop bars in Vietnam
Knowledge unit: Sky 36, Da Nang
```

```text
Document: Vietnam In Depth
Knowledge unit: Day 5 - Ninh Binh
```

```text
Document: Things to do in Hue
Knowledge unit: Cuisine - Bun bo Hue
```

Knowledge unit giúp hệ thống hiểu:

- nội dung nói về entity nào;
- thuộc địa điểm nào;
- thuộc category nào;
- phục vụ intent truy vấn nào;
- nên mở rộng context đến đâu khi trả lời.

Schema gợi ý:

```json
{
  "knowledge_unit_id": "doc_001_ku_001",
  "document_id": "doc_001",
  "unit_type": "entity",
  "name": "Sky 36",
  "locations": ["Da Nang", "Vietnam"],
  "category": "Nightlife",
  "heading": "Best for river views: Sky 36, Da Nang",
  "source_url": "..."
}
```

## 10. Bước 4: Parent-Child Chunking

### 10.1. Parent

Parent đại diện cho một đơn vị ngữ nghĩa lớn:

- một entity section;
- một ngày trong itinerary;
- một aspect của điểm đến;
- một nhóm paragraph trong news article;
- một route/chặng hành trình.

Parent dùng để:

- mở rộng context;
- trả lời câu hỏi tổng quát;
- giữ quan hệ giữa các child;
- phục vụ citation.

### 10.2. Child

Child là đơn vị nhỏ dùng cho retrieval:

- BM25;
- vector search;
- reranking.

Flow:

```text
Query
→ retrieve child
→ rerank
→ expand parent nếu cần
→ đưa answer context vào LLM
```

Không phải query nào cũng cần expand parent. Parent expansion chỉ nên dùng khi child thiếu ngữ cảnh hoặc query có phạm vi rộng.

## 11. Chunking Theo Từng Loại Document

### 11.1. Listicle / Entity Collection

Ví dụ:

- `7 stunning rooftop bars in Vietnam`;
- `5 unique towns in the Mekong Delta`;
- `Nha Trang's best wellness experiences`;
- danh sách món ăn;
- danh sách điểm tham quan.

Rule:

```text
Một heading/entity = một parent
Section ngắn <= 350 tokens -> một child
Section dài > 350-450 tokens -> split theo paragraph hoặc semantic boundary
Không merge hai entity khác nhau
```

Metadata quan trọng:

```json
{
  "document_type": "listicle",
  "parent_type": "entity_section",
  "entity_name": "Sky 36",
  "entity_type": "rooftop_bar",
  "locations": ["Da Nang"],
  "category": "Nightlife"
}
```

### 11.2. Destination Guide

Ví dụ:

- `Da Nang`;
- `Ha Long`;
- `Phong Nha`;
- `Things to do in Da Nang`;
- `Food guide to Hue`.

Rule:

```text
Một aspect lớn = một parent
Overview, Attractions, Food, Transport, Weather, Accommodation là các aspect ưu tiên
Section <= 350 tokens -> giữ nguyên
Section dài -> split theo entity nếu có
Không có entity rõ -> semantic split trong section
```

Metadata quan trọng:

```json
{
  "document_type": "destination_guide",
  "parent_type": "aspect_section",
  "destination": "Da Nang",
  "category": "Transportation",
  "heading_path": ["Da Nang", "Getting around"]
}
```

### 11.3. Itinerary

Ví dụ:

- `Vietnam In Depth`;
- `Heritage Sites of Vietnam`;
- lịch trình miền Bắc/miền Trung/miền Nam.

Rule:

```text
Một ngày = một parent
Không trộn hai ngày khác nhau
Không tách DAY marker khỏi nội dung ngày
Ngày <= 400 tokens -> một child
Ngày dài > 400 tokens -> split theo activity hoặc location
Activity dài > 450 tokens -> semantic split trong activity
```

Metadata quan trọng:

```json
{
  "document_type": "itinerary",
  "parent_type": "itinerary_day",
  "day_number": 5,
  "route": ["Ninh Binh", "Ha Long"],
  "locations": ["Ninh Binh", "Ha Long"],
  "activities": ["boat trip", "overnight cruise"]
}
```

### 11.4. News Article / Event Article

Ví dụ:

- tin tức xúc tiến du lịch;
- bài viết về sự kiện;
- bài ít heading, nhiều paragraph liên tục.

Rule:

```text
Ưu tiên giữ nguyên paragraph
Group paragraph theo topic
Không cắt giữa câu
Target 250 tokens
Min 120 tokens
Max 450 tokens
Overlap 30 tokens nếu semantic segment bị chia
```

Metadata quan trọng:

```json
{
  "document_type": "news_article",
  "parent_type": "topic_segment",
  "locations": ["Quang Ninh"],
  "category": "Event",
  "published_at": null,
  "language": "vi"
}
```

## 12. Retrieval Text

Không embedding toàn bộ JSON. Chỉ embedding trường `retrieval_text`.

Template đề xuất:

```text
Document: {document_title}
Section: {heading}
Entity: {entity_name}
Location: {locations}
Category: {category}
Document type: {document_type}

{source_text}
```

Cần phân biệt 3 loại text:

| Trường | Vai trò |
|---|---|
| `source_text` | Nội dung gốc, dùng cho citation và truy vết |
| `retrieval_text` | Nội dung giàu context, dùng cho BM25/vector retrieval |
| `answer_text` | Nội dung sạch, tự nhiên, dùng để đưa vào LLM trả lời |

Lưu ý:

- `retrieval_text` không nên nhồi quá nhiều metadata.
- Với BM25, có thể thêm nhiều keyword/entity alias hơn.
- Với vector search, nên giữ text tự nhiên để embedding không bị loãng.

## 13. Metadata Chunk Đề Xuất

Mỗi chunk nên có metadata:

```json
{
  "chunk_id": "doc_001_sec_001_chunk_001",
  "parent_id": "doc_001_sec_001",
  "knowledge_unit_id": "doc_001_ku_001",
  "document_id": "doc_001",
  "source_url": "https://vietnam.travel/...",
  "source_domain": "vietnam.travel",
  "language": "en",
  "document_title": "7 stunning rooftop bars in Vietnam",
  "document_type": "listicle",
  "structure_type": "strong",
  "chunk_type": "entity_content",
  "heading": "Best for river views: Sky 36, Da Nang",
  "heading_path": ["7 stunning rooftop bars in Vietnam", "Sky 36"],
  "entity_name": "Sky 36",
  "entity_type": "rooftop_bar",
  "locations": ["Da Nang", "Vietnam"],
  "province": "Da Nang",
  "category": "Nightlife",
  "intent_tags": ["things_to_do", "nightlife", "where_to_go"],
  "day_number": null,
  "token_count": 270,
  "previous_chunk_id": null,
  "next_chunk_id": null
}
```

Metadata quan trọng nhất cho retrieval:

| Metadata | Lý do |
|---|---|
| `province` / `locations` | Filter theo điểm đến |
| `category` | Filter theo nhu cầu: cuisine, attraction, transport |
| `document_type` | Chọn strategy retrieval |
| `entity_name` | Trả lời câu hỏi cụ thể |
| `day_number` | Truy vấn itinerary |
| `intent_tags` | Match theo ý định người dùng |
| `language` | Query routing đa ngôn ngữ |
| `source_url` | Citation |

## 14. So Sánh Với Baseline Standard RAG

| Tiêu chí | Standard RAG | Chunking đề xuất |
|---|---|---|
| Cách chia chunk | Fixed-size theo token/character | Theo structure, entity, day, aspect |
| Tận dụng heading | Thấp | Cao |
| Tôn trọng section boundary | Không đảm bảo | Có |
| Tôn trọng entity boundary | Không đảm bảo | Có |
| Tôn trọng itinerary day | Không đảm bảo | Có |
| Metadata | Nghèo | Giàu metadata |
| Retrieval theo tỉnh/thành | Khó | Tốt |
| Retrieval theo category | Khó | Tốt |
| Retrieval câu hỏi cụ thể | Trung bình | Tốt |
| Retrieval câu hỏi itinerary | Yếu | Tốt |
| Citation | Chung chung | Rõ theo document/section/entity |
| Khả năng mở rộng Agent | Thấp | Cao |
| Chi phí triển khai | Thấp | Cao hơn |
| Độ phức tạp | Thấp | Trung bình-cao |
| Phù hợp với dữ liệu hiện tại | Trung bình | Cao, sau normalization |

Kết luận so sánh:

- `Standard RAG` phù hợp để làm baseline nhanh.
- Chiến lược đề xuất phù hợp hơn với dữ liệu du lịch vì giữ được cấu trúc tri thức.
- Nên triển khai cả hai để đánh giá định lượng bằng cùng tập câu hỏi.

## 15. Evaluation Plan

Cần so sánh ít nhất 2 hệ:

```text
Baseline A: Standard RAG
Approach B: Hybrid Structure-aware Chunking
```

Nếu có thời gian, thêm:

```text
Baseline C: Structural-only Chunking
```

### 15.1. Bộ câu hỏi kiểm thử

Nhóm câu hỏi entity:

```text
Sky 36 nằm ở đâu?
Spa nào nổi bật ở Nha Trang?
Cần Thơ có hoạt động gì?
```

Nhóm câu hỏi destination/aspect:

```text
Đà Nẵng có những điểm tham quan nào?
Huế có món ăn gì nên thử?
Đi Phong Nha nên chú ý gì?
```

Nhóm câu hỏi itinerary:

```text
Ngày thứ hai trong lịch trình đi đâu?
Ngày nào ghé Ninh Bình?
Lịch trình tại Huế có gì?
```

Nhóm câu hỏi broad query:

```text
Tóm tắt các thị trấn nổi bật ở Mekong Delta.
Gợi ý các điểm đến phù hợp cho người thích biển.
So sánh Nha Trang và Phú Quốc cho du lịch nghỉ dưỡng.
```

### 15.2. Metric

Retrieval metrics:

```text
Recall@K
MRR
nDCG@K
Context Precision
Context Recall
```

Answer metrics:

```text
Answer Faithfulness
Answer Relevance
Entity Accuracy
Location Accuracy
Day Accuracy
Citation Accuracy
```

Chunk quality metrics:

```text
Entity Purity
Section Integrity
Orphan Heading Rate
Empty Chunk Rate
Oversized Chunk Rate
Metadata Completeness
Answerability
```

## 16. Tiêu Chí Thành Công

Chiến lược chunking đề xuất được xem là tốt hơn Standard RAG nếu:

- Recall@5 cao hơn baseline;
- MRR cao hơn baseline;
- Context precision cao hơn baseline;
- Ít chunk bị trộn entity hơn;
- Câu trả lời itinerary đúng ngày hơn;
- Citation rõ ràng hơn;
- Câu trả lời ít hallucination hơn;
- Có thể filter tốt theo province/category/language.

## 17. Kế Hoạch Triển Khai

### Giai đoạn 1: Chuẩn hóa document

Đầu vào:

```text
data/clean_documents_full.jsonl
```

Thực hiện:

1. Sửa heading bị nhận nhầm paragraph.
2. Bỏ section rỗng khỏi quá trình chunk.
3. Chuẩn hóa `language`.
4. Parse itinerary marker như `DAY 1`, `DAY 2`.
5. Chuyển `Route`, `Highlights` thành metadata nếu phù hợp.
6. Gắn `document_type`.
7. Gắn `structure_type` và `structure_score`.

Đầu ra:

```text
data/processed/normalized_documents.jsonl
```

### Giai đoạn 2: Tạo chunk baseline Standard RAG

Thực hiện:

```text
plain_text -> fixed-size chunks
```

Cấu hình:

```yaml
chunk_size: 500
chunk_overlap: 50
```

Đầu ra:

```text
data/chunks/chunks_standard_rag.jsonl
```

### Giai đoạn 3: Tạo chunk hybrid

Thực hiện:

```text
normalized_documents
→ knowledge_units
→ parents
→ child_chunks
```

Đầu ra:

```text
data/chunks/knowledge_units.jsonl
data/chunks/parents.jsonl
data/chunks/chunks_hybrid.jsonl
```

### Giai đoạn 4: Indexing

Tạo index cho cả baseline và hybrid:

```text
BM25 index
Vector index
Metadata index
```

### Giai đoạn 5: Evaluation

So sánh:

```text
Standard RAG vs Hybrid Structure-aware Chunking
```

Theo các nhóm câu hỏi:

- entity query;
- destination/aspect query;
- itinerary query;
- broad query;
- Vietnamese query;
- English query.

## 18. Kết Luận

Chiến lược chunking đề xuất phù hợp với đặc điểm dữ liệu hiện tại hơn Standard RAG.

Lý do chính:

- Dữ liệu có cấu trúc section rõ ràng.
- Phần lớn document thuộc nhóm `things-to-do`, rất phù hợp với entity-based chunking.
- Các bài itinerary cần boundary theo ngày, không thể xử lý tốt bằng fixed-size chunking.
- Các trang điểm đến cần chunk theo aspect như cuisine, attractions, transportation, weather.
- Median document chỉ khoảng 784 words, nên fixed-size chunking toàn document không đem lại nhiều lợi ích.

Tuy nhiên, trước khi triển khai hybrid chunking cần chuẩn hóa dữ liệu:

- sửa heading bị nhiễu;
- bỏ section rỗng;
- chuẩn hóa language;
- gắn document type;
- extract location/category/entity.

Khuyến nghị cuối cùng:

```text
Standard RAG chỉ dùng làm baseline.
Hybrid Structure-aware Chunking nên là hướng chính cho hệ thống RAG du lịch.
```
