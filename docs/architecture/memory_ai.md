# 🧠 Thiết Kế Kiến Trúc: Hệ Thống Memory AI

> **Tài liệu gốc tham khảo:** `docs/knowledge/Task 02 - Báo cáo Research Memory AI.pdf`
> **Mục đích:** File này cung cấp ngữ cảnh kiến trúc cho các AI Agent khi thực hiện code/refactor các module liên quan đến Memory. Mọi thay đổi logic về sau PHẢI bám sát tài liệu này.

---

## 1. Tổng Quan Hệ Thống (System Overview)

Hệ thống Memory AI quản lý trí nhớ dài hạn (Long-term Semantic Memory) và trí nhớ ngắn hạn (Working Memory) cho Agent. Nó bao gồm 3 phân hệ chính:
1. **Read Pipeline (Đọc & Truy xuất)**: Trích xuất context liên quan từ Database để ghép vào Prompt.
2. **Write Pipeline (Ghi & Hợp nhất)**: Đánh giá hội thoại mới, trích xuất fact, xử lý trùng lặp và lưu trữ.
3. **Async Event & Concurrency**: Hệ thống hàng đợi (Queue) giải quyết bài toán đồng bộ dữ liệu giữa PostgreSQL (Nguồn sự thật) và Vector DB (ChromaDB) mà không chặn luồng (blocking) API.

---

## 2. Đường Ống Ghi (Memory Write Pipeline)

Khi một phiên hội thoại diễn ra, dữ liệu đi qua 5 bước nghiêm ngặt sau:

### 2.1 Extraction (Trích xuất)
- Dùng LLM với định dạng JSON (Structured Output).
- Biến đổi những câu nói tự nhiên của User (VD: *"Tôi bị dị ứng hải sản"*) thành các Fact có cấu trúc.
- Trả về danh sách `ExtractedMemory`.

### 2.2 Validation (Kiểm tra hợp lệ)
- **Rule-based:** Lọc bỏ những thông tin tạm thời (VD: *"Tôi đang ở Starbucks"*).
- Đảm bảo `fact_type` hợp lệ và `confidence` > threshold.

### 2.3 Deduplication (Lọc trùng lặp)
- Dùng Vector Search (ChromaDB) để tìm các Memory *có khả năng trùng* của user này.
- Phát hiện:
  - Exact duplicate (Trùng 100%).
  - Near-duplicate (Cùng entity, nhưng chi tiết khác).

### 2.4 Conflict Resolution (Giải quyết xung đột)
Mọi Fact mới phải qua bộ xử lý Xung đột để đưa ra Hành động (Action):
1. **SKIP**: Bỏ qua nếu hoàn toàn trùng với Fact cũ.
2. **CREATE**: Tạo mới nếu hoàn toàn không trùng.
3. **UPDATE**: Cập nhật giá trị mới nhất (cùng `fact_key`, mới hơn về thời gian).
4. **MERGE**: Ghép thông tin (VD: Cũ "Thích đi du lịch", Mới "Đặc biệt thích đi biển").
5. **DEPRECATE + CREATE**: Mâu thuẫn hoàn toàn. Hủy (Deprecate) cái cũ để giữ lịch sử, và tạo mới cái hiện tại.

---

## 3. Đường Ống Đọc (Memory Read Pipeline)

Khi User đặt câu hỏi mới, hệ thống cần lấy ra Context chuẩn xác nhất:

1. **Hybrid Retrieval**:
   - Semantic (Vector Search bằng ChromaDB).
   - Metadata Filtering (Chỉ lấy status `active`, lọc theo `user_id`).
2. **Weighted Score Ranking**:
   - `Final_Score` = $w_1 \times Relevance$ + $w_2 \times Temporal$ + $w_3 \times Importance$.
3. **Top-K Context**:
   - Lọc bỏ các memory có `Final_Score` < Threshold.
   - Giới hạn Budget Token, chỉ lấy tối đa K memories đưa vào Prompt.

---

## 4. Kiến Trúc Bất Đồng Bộ & Lưu Trữ (Async & Persistence)

Hệ thống thiết kế theo Pattern **Transactional Outbox & Eventual Consistency**.

### 4.1 PostgreSQL (Source of Truth)
- Chịu trách nhiệm lưu trữ toàn bộ Metadata, Versioning và Text của Memory.
- Khi Write Pipeline chạy xong -> `COMMIT` vào PostgreSQL.

### 4.2 Background Worker (Celery/FastAPI BackgroundTasks)
- **Tuyệt đối không gọi ChromaDB trực tiếp trong API Request của User.**
- Khi Postgres lưu thành công, đẩy 1 Message (memory_id, version) vào Redis Queue.
- Worker sẽ nhặt Message này lên và chạy bất đồng bộ (Embedding Content → Upsert vào ChromaDB).

### 4.3 Idempotency & Concurrency (Chống Race Condition)
- Sử dụng **Optimistic Versioning** (Mỗi Memory có một số nguyên `version`).
- Khi Worker chạy cập nhật ChromaDB, nó so sánh `version` của DB với `version` của Event.
  - Nếu bản ghi trong Event cũ hơn (Stale) → Bỏ qua (SKIP).
  - Nếu bằng hoặc lớn hơn → UPSERT vào ChromaDB.

---

## 5. Vòng Đời Trí Nhớ (Memory Lifecycle)

Mỗi Memory không tồn tại vĩnh viễn với cùng một mức độ ưu tiên.
- `CANDIDATE`: Mới trích xuất, cần đánh giá.
- `ACTIVE`: Được dùng thường xuyên.
- `REINFORCED`: Được user nhắc lại nhiều lần (Promotion).
- `STALE / ARCHIVED`: Lâu không dùng, giảm Importance (Decay).
- `DEPRECATED`: Bị thay thế bởi thông tin mới.

> **💡 Lưu ý cho AI Developer:** Khi viết code cho Memory, hãy luôn kiểm tra xem code của bạn có đang vi phạm luồng Write Pipeline và có block luồng Async hay không.
