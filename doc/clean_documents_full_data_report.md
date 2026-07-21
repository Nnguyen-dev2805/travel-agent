# Báo Cáo Tổng Quan Dữ Liệu `clean_documents_full.jsonl`

Ngày lập báo cáo: 2026-07-21  
File dữ liệu: `data/clean_documents_full.jsonl`  
Dung lượng: khoảng `3.6 MB`

## 1. Tóm Tắt Điều Hành

File `clean_documents_full.jsonl` hiện có `281` document ở định dạng JSONL. Toàn bộ `281/281` dòng đều parse JSON hợp lệ, không phát hiện trùng `document_id`, trùng `url`, hoặc trùng toàn bộ `plain_text`.

Về mặt kỹ thuật, dữ liệu đã được làm sạch khá tốt: không còn HTML tag thô trong `plain_text`, có cấu trúc `sections`, `blocks`, `heading_path`, và có trường `quality` để theo dõi trạng thái trích xuất.

Tuy nhiên, dữ liệu chưa nên được đưa thẳng vào embedding hoặc vector database. Vấn đề lớn nhất hiện tại nằm ở tầng ngữ nghĩa: nhiều đoạn mở bài đang bị extractor nhận nhầm thành heading. Điều này có thể làm nhiễu `heading`, `heading_path`, metadata và ảnh hưởng trực tiếp đến chất lượng retrieval.

Đánh giá tổng quan:

| Tiêu chí | Đánh giá |
|---|---|
| Độ hợp lệ JSON | Rất tốt |
| Độ sạch HTML | Tốt |
| Độ đầy đủ schema | Tốt |
| Độ sạch metadata | Trung bình khá |
| Độ đúng semantic structure | Cần cải thiện |
| Sẵn sàng cho chunking | Cần hậu xử lý thêm |
| Sẵn sàng cho embedding | Chưa nên embedding trực tiếp |

## 2. Thống Kê Tổng Quan

| Chỉ số | Giá trị |
|---|---:|
| Tổng số dòng JSONL | 281 |
| Dòng JSON hợp lệ | 281 |
| Dòng JSON lỗi | 0 |
| Duplicate `document_id` | 0 |
| Duplicate `url` | 0 |
| Duplicate `plain_text` | 0 |
| Document thiếu title | 0 |
| Document thiếu `meta_description` | 38 |
| Document không có block nội dung | 1 |
| Document còn HTML tag trong `plain_text` | 0 |

## 3. Nguồn Dữ Liệu

Dữ liệu đến từ 2 domain chính:

| Domain | Số document |
|---|---:|
| `vietnam.travel` | 247 |
| `2025.vietnam.travel` | 34 |

Nhận xét:

- `vietnam.travel` là nguồn chính, chủ yếu gồm các bài tiếng Anh về điểm đến, trải nghiệm, ẩm thực, văn hóa và lịch trình.
- `2025.vietnam.travel` gồm các bài tiếng Việt, phần nhiều mang tính tin tức, xúc tiến du lịch, sự kiện địa phương.

## 4. Ngôn Ngữ

| Language | Số document |
|---|---:|
| `None` | 247 |
| `vi-VN` | 34 |

Nhận xét:

- 247 document đang có `language = None`, nhưng nhiều khả năng là tiếng Anh.
- 34 document có `language = vi-VN`.
- Nên chạy bước language detection hoặc gán ngôn ngữ theo domain/path để đảm bảo metadata chính xác cho RAG đa ngôn ngữ.

Đề xuất:

- Gán `language = en` cho các bài tiếng Anh sau khi xác minh.
- Giữ `vi-VN` hoặc chuẩn hóa thành `vi` cho các bài tiếng Việt.
- Nên thống nhất format metadata ngôn ngữ, ví dụ chỉ dùng `en` và `vi`.

## 5. Cấu Trúc Document

Mỗi document có cấu trúc chính:

```json
{
  "document_id": "...",
  "url": "...",
  "raw_title": "...",
  "clean_title": "...",
  "meta_description": "...",
  "language": "...",
  "sections": [...],
  "plain_text": "...",
  "quality": {...}
}
```

Mỗi section có cấu trúc:

```json
{
  "heading": "...",
  "heading_level": 1,
  "heading_path": [...],
  "blocks": [...]
}
```

Mỗi block hiện tại chủ yếu thuộc 2 loại:

| Block type | Số lượng |
|---|---:|
| `paragraph` | 4,124 |
| `list` | 62 |

Nhận xét:

- Cấu trúc này phù hợp với dạng pre-chunk document.
- Có thể dùng `sections` làm đơn vị nền tảng cho semantic chunking.
- Chưa thấy các block giàu cấu trúc khác như `table`, `image_caption`, `quote`.

## 6. Phân Bố Độ Dài Document

### Sections trên mỗi document

| Metric | Giá trị |
|---|---:|
| Min | 1 |
| P25 | 2 |
| Median | 5 |
| P75 | 8 |
| P90 | 10 |
| Max | 25 |
| Average | 5.6 |

### Blocks trên mỗi document

| Metric | Giá trị |
|---|---:|
| Min | 0 |
| P25 | 10 |
| Median | 13 |
| P75 | 17 |
| P90 | 25 |
| Max | 87 |
| Average | 14.9 |

### Words trên mỗi document

| Metric | Giá trị |
|---|---:|
| Min | 50 |
| P25 | 500 |
| Median | 784 |
| P75 | 1,001 |
| P90 | 1,278 |
| Max | 2,605 |
| Average | 792.2 |

Nhận xét:

- Độ dài document khá phù hợp để chunk theo section.
- Không nên chunk trực tiếp từ `plain_text` theo số token cố định.
- Nhiều document có kích thước vừa phải, có thể giữ nguyên section thành chunk nếu section không quá dài.

## 7. Các Nhóm Nội Dung Chính

Theo URL path:

| Nhóm URL | Số document | Đặc điểm |
|---|---:|---|
| `things-to-do` | 212 | Bài gợi ý trải nghiệm, ẩm thực, văn hóa, hoạt động, nightlife |
| `places-to-go` | 22 | Trang điểm đến, tỉnh/thành, khu vực |
| `plan-your-trip` | 13 | Lịch trình, hướng dẫn lên kế hoạch, itinerary |
| URL tin tức tiếng Việt 2025 | 34 | Tin tức, sự kiện, kích cầu, xúc tiến du lịch địa phương |

Theo keyword suy luận nội dung:

| Category suy luận | Số document có dấu hiệu |
|---|---:|
| Attractions | 230 |
| Cuisine | 226 |
| Activities | 226 |
| Culture | 166 |
| Accommodation | 135 |
| Weather | 126 |
| Transportation | 124 |
| Nightlife | 99 |
| Itinerary | 92 |
| Shopping | 77 |

Lưu ý: bảng trên là suy luận bằng keyword, chưa phải metadata category chính thức. Cần có bước classifier/rule-based enrichment riêng để gán category chuẩn.

## 8. Các Điểm Đến Xuất Hiện Nhiều

| Điểm đến / địa danh | Số document có dấu hiệu |
|---|---:|
| Hanoi | 85 |
| Ho Chi Minh | 62 |
| Hue | 60 |
| Hoi An | 45 |
| Nha Trang | 43 |
| Da Nang | 42 |
| Phu Quoc | 32 |
| Mekong | 27 |
| Sapa | 23 |
| Ha Long | 21 |
| Ha Noi | 20 |
| Phong Nha | 18 |
| Halong | 15 |
| Ninh Binh | 14 |
| Da Lat | 14 |
| Can Tho | 9 |
| Mui Ne | 8 |
| Con Dao | 8 |
| Dalat | 6 |
| Quang Binh | 4 |

Nhận xét:

- Dữ liệu có độ phủ tốt với các điểm đến du lịch phổ biến của Việt Nam.
- Cần chuẩn hóa alias địa danh để phục vụ metadata và filter retrieval.
- Một số alias nên chuẩn hóa:
  - `Hanoi` và `Ha Noi`
  - `Ha Long` và `Halong`
  - `Dalat` và `Da Lat`
  - `Ho Chi Minh`, `Ho Chi Minh City`, `Saigon`, `TP. Hồ Chí Minh`

## 9. Đánh Giá Độ Sạch Dữ Liệu

### 9.1. Điểm Mạnh

1. JSONL hợp lệ 100%.
2. Không có duplicate theo `document_id`, `url`, `plain_text`.
3. Không còn HTML tag thô trong `plain_text`.
4. Có cấu trúc document/section/block rõ ràng.
5. Có `quality.status` và warning để truy vết lỗi extraction.
6. Đã loại được một phần duplicate paragraph/heading.

### 9.2. Vấn Đề Cần Xử Lý

#### Heading bị nhiễu

Có `228` heading dài hơn 180 ký tự. Nhiều heading trong số này thực chất là paragraph mở đầu bị nhận nhầm thành heading.

Ví dụ dạng lỗi:

```text
When it comes to rooftop bars, Vietnam is up there with the best in Asia...
```

Đây là một paragraph giới thiệu, không phải heading.

Tác động:

- Làm sai `heading_path`.
- Làm sai semantic chunk.
- Làm metadata `heading` bị nhiễu.
- Làm retriever khó match đúng intent/category.

Mức độ ưu tiên: cao.

#### Section rỗng

Có `322` section không có block nội dung.

Một số section rỗng có thể hợp lệ, ví dụ title section hoặc route label. Tuy nhiên nếu để nguyên, chunker có thể tạo chunk rỗng hoặc heading context không cần thiết.

Tác động:

- Tăng nhiễu trong document tree.
- Làm khó semantic chunking.
- Có thể tạo metadata heading không có nội dung.

Mức độ ưu tiên: trung bình cao.

#### Thiếu `meta_description`

Có `38` document thiếu `meta_description`.

Tác động:

- Không quá nghiêm trọng nếu nội dung chính đầy đủ.
- Có thể ảnh hưởng đến document summary, preview, hoặc reranking nếu dùng description làm signal.

Mức độ ưu tiên: trung bình.

#### Document quá ngắn hoặc không có block

Có 1 document không có block nội dung:

```text
[Infographic] Visa exemption for citizens of Poland, Czech and Switzerland
```

Tác động:

- Giá trị retrieval thấp nếu chỉ có title/plain text ngắn.
- Nên gắn flag `low_content` hoặc loại khỏi index chính.

Mức độ ưu tiên: trung bình.

## 10. Đánh Giá Cho RAG

Dữ liệu hiện tại phù hợp để làm đầu vào cho pipeline:

```text
Clean Document -> Metadata Enrichment -> Semantic Chunking -> Embedding
```

Không nên làm:

```text
plain_text -> fixed-size token chunk -> embedding
```

Lý do:

- `plain_text` làm mất cấu trúc heading/section.
- Fixed-size chunk có thể cắt ngang một section đang hoàn chỉnh về nghĩa.
- Metadata như province/category/heading chưa được chuẩn hóa.

Hướng tốt hơn:

1. Dùng `sections` làm đơn vị semantic ban đầu.
2. Sửa heading bị nhầm paragraph.
3. Bỏ qua section rỗng khi chunk.
4. Gán category theo heading, URL và nội dung.
5. Gán province/destination theo entity extraction.
6. Chỉ chia nhỏ section nếu section quá dài.

## 11. Metadata Nên Bổ Sung

Mỗi chunk nên có metadata:

```json
{
  "document_id": "...",
  "chunk_id": "...",
  "source": "vietnam.travel",
  "url": "...",
  "language": "en",
  "province": "Da Nang",
  "destination": "Da Nang",
  "category": "Cuisine",
  "heading": "Must-try local dishes",
  "heading_path": ["Da Nang", "Food", "Must-try local dishes"],
  "content_type": "guide",
  "url_group": "things-to-do"
}
```

Metadata nên ưu tiên:

| Metadata | Mục đích |
|---|---|
| `province` | Filter theo tỉnh/thành |
| `destination` | Tìm điểm đến cụ thể |
| `category` | Filter theo Cuisine, Attractions, Transportation... |
| `language` | Hỗ trợ retrieval đa ngôn ngữ |
| `content_type` | Phân biệt guide, itinerary, news, infographic |
| `heading_path` | Giữ ngữ cảnh semantic |
| `source` / `url` | Truy vết nguồn |

## 12. Đề Xuất Xử Lý Tiếp Theo

### Ưu tiên 1: Làm sạch heading

Cần viết rule để chuyển heading dài hoặc heading có cấu trúc paragraph thành paragraph.

Rule gợi ý:

- Nếu heading dài hơn 160-180 ký tự và không có block: chuyển thành paragraph intro.
- Nếu heading có trên 2 câu và kết thúc bằng dấu chấm: khả năng cao là paragraph.
- Nếu `heading_level = 2` nhưng nội dung dài như meta description: chuyển thành block paragraph dưới title section.

### Ưu tiên 2: Loại section rỗng khỏi chunking

Không nhất thiết phải xóa khỏi clean document gốc nếu cần trace, nhưng chunker nên bỏ qua section không có block.

### Ưu tiên 3: Chuẩn hóa language

Gán ngôn ngữ cho tất cả document:

- `en` cho bài tiếng Anh.
- `vi` cho bài tiếng Việt.

### Ưu tiên 4: Gán category

Có thể kết hợp rule-based và LLM lightweight classifier:

- Rule theo URL: `things-to-do`, `places-to-go`, `plan-your-trip`.
- Rule theo heading: `Food`, `Where to stay`, `Weather`, `Getting around`.
- Keyword/entity matching.
- LLM classifier cho trường hợp nhập nhằng.

### Ưu tiên 5: Extract province/destination

Cần có dictionary địa danh Việt Nam và alias:

```json
{
  "Da Nang": ["Danang", "Da Nang"],
  "Ha Noi": ["Hanoi", "Ha Noi"],
  "Ho Chi Minh City": ["Ho Chi Minh City", "HCMC", "Saigon", "TP. Ho Chi Minh"],
  "Da Lat": ["Dalat", "Da Lat"],
  "Ha Long": ["Ha Long", "Halong"]
}
```

## 13. Kết Luận

`clean_documents_full.jsonl` là bộ dữ liệu có nền tảng tốt: hợp lệ, đã tách cấu trúc, không còn HTML thô, không có trùng lặp nghiêm trọng. Đây là đầu vào tốt cho một pipeline RAG nghiêm túc.

Tuy nhiên, chất lượng retrieval sẽ bị ảnh hưởng nếu embedding ngay lập tức, vì heading và section tree chưa thật sự sạch về mặt ngữ nghĩa. Việc cần làm tiếp theo là semantic cleaning: sửa heading bị nhầm paragraph, bỏ qua section rỗng, chuẩn hóa ngôn ngữ, gán category và province/destination metadata.

Khuyến nghị: không embedding trực tiếp file này. Hãy dùng file này làm pre-chunk document, sau đó tạo một bước `metadata_enrichment + semantic_chunking` trước khi đưa vào vector database.
