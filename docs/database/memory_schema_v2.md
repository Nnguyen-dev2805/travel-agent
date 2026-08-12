# 🗄️ Thiết Kế Database: Memory Schema V2

> **Tài liệu gốc tham khảo:** `docs/knowledge/Task 02 - Báo cáo Research Memory AI.pdf`
> **Mục đích:** Đặc tả cấu trúc bảng và các Enums cho hệ thống Memory AI. AI Agent BẮT BUỘC phải tham chiếu file này khi tạo SQLAlchemy Models hoặc viết Alembic Migrations.

---

## 1. Định nghĩa Enums (Python `enum.Enum`)

Hệ thống sử dụng các Enum tĩnh để đảm bảo tính nhất quán dữ liệu:

### `MemoryType`
- `SEMANTIC`: Trí nhớ dài hạn (Sở thích, thói quen, thông tin cá nhân).
- `EPISODIC`: Trí nhớ theo sự kiện (Tóm tắt một phiên chat).
- `WORKING`: Trí nhớ ngắn hạn (Ngữ cảnh của phiên chat hiện tại).

### `FactType`
- Phân loại các thông tin Semantic để lọc dễ dàng:
- `PREFERENCE`, `IDENTITY`, `VISITED_PLACE`, `BUDGET`, `TRAVEL_STYLE`, `DIETARY`, `BEHAVIOR`.

### `MemoryStatus`
- Dùng cho Memory Lifecycle:
- `CANDIDATE`: Chờ đánh giá, chưa được đưa vào RAG.
- `ACTIVE`: Đang sử dụng (mặc định cho RAG).
- `REINFORCED`: Thông tin quan trọng, được nhắc lại nhiều lần.
- `STALE`: Đã lâu không truy cập, có thể giảm trọng số.
- `ARCHIVED`: Đóng băng, không đưa vào RAG nhưng vẫn giữ lịch sử.
- `DEPRECATED`: Bị thay thế bởi Fact mới.
- `DELETED`: Đã xóa (Soft delete).

### `ConflictAction`
- Khai báo hành động xử lý xung đột:
- `SKIP`, `CREATE`, `UPDATE`, `MERGE`, `DEPRECATE_AND_CREATE`, `DELETE`.

---

## 2. Cấu Trúc Bảng `user_memories`

Sử dụng SQLAlchemy 2.0 style (`Mapped`, `mapped_column`).

| Cột (Column) | Kiểu Dữ Liệu | Ràng buộc | Mô tả |
|---|---|---|---|
| `id` | `Integer` | Primary Key, Auto Increment | Khóa chính nội bộ DB. |
| `memory_id` | `String(36)` | Unique, Index | UUID. Dùng làm định danh (stable ID) để sync với ChromaDB. |
| `user_id` | `Integer` | Foreign Key (users.id), Index | Người dùng sở hữu Memory. |
| `memory_type` | `String(20)` | Not Null | Map với `MemoryType`. |
| `fact_type` | `String(30)` | Not Null | Map với `FactType`. |
| `fact_key` | `String(100)` | Not Null, Index | Chủ đề của Fact (VD: `user_preference_food`). Dùng để Deduplication. |
| `content` | `Text` | Not Null | Nội dung text của Memory (VD: `"Thích ăn hải sản, đặc biệt là tôm"`). |
| `status` | `String(20)` | Default="candidate" | Map với `MemoryStatus`. |
| `version` | `Integer` | Default=1 | Optimistic Versioning (Quan trọng cho Async Sync). |
| `importance` | `Float` | Default=0.5 | Điểm quan trọng (0.0 - 1.0) dùng khi Ranking. |
| `confidence` | `Float` | Default=1.0 | Độ tự tin của LLM khi trích xuất. |
| `confirmation_count` | `Integer` | Default=0 | Đếm số lần user xác nhận lại fact này (Promotion). |
| `source_session_id` | `String(36)` | Nullable | ID của phiên chat tạo ra fact này (Traceability). |
| `superseded_by` | `String(36)` | Nullable | Lưu `memory_id` của bản ghi mới thay thế nó (nếu status=DEPRECATED). |
| `last_accessed_at` | `DateTime(UTC)` | Nullable | Dùng để tính toán Memory Decay (STALE). |
| `last_confirmed_at` | `DateTime(UTC)` | Nullable | Thời điểm gần nhất user nhắc lại fact. |
| `created_at` | `DateTime(UTC)` | Default=Now | Thời điểm tạo. |
| `updated_at` | `DateTime(UTC)` | Default=Now, OnUpdate=Now | Thời điểm cập nhật cuối. |

---

## 3. Các Ràng Buộc & Quy Tắc Thiết Kế (Constraints)

1. **UUID cho `memory_id`**: Bắt buộc. Vì PostgreSQL và ChromaDB nằm ở 2 hệ thống khác nhau, việc dùng Integer ID (autoincrement) dễ dẫn đến sai lệch khi migrate hoặc crash. UUID đảm bảo ID là duy nhất trên cả 2 hệ thống.
2. **Không bao giờ XÓA CỨNG (Hard Delete)**: Nếu user muốn xóa memory, chỉ chuyển `status` thành `DELETED`. Điều này giúp giữ vẹn toàn dữ liệu để train/đánh giá AI sau này.
3. **Cập nhật Version (Version Bump)**: Bất cứ khi nào bản ghi được sửa đổi nội dung (`content`, `status`, `importance`), cột `version` PHẢI được cộng thêm 1 (`version = version + 1`). Quy tắc này phục vụ cho cơ chế xử lý Race Condition khi đẩy vào Redis Queue.
