# 🤖 MASTER AGENTIC CODING DIRECTIVES & STANDARDS

Bản Hiến pháp Quy tắc Kỹ thuật (System Directives) bắt buộc mọi AI Coding Agent phải tuân thủ 100% trong toàn bộ các tác vụ lập trình, phân tích và kiến trúc.

---

## 🏛️ 1. CÁC NGUYÊN TẮC THIẾT KẾ CỐT LÕI (CORE DESIGN PRINCIPLES)

- **S.O.L.I.D**:
  - **Single Responsibility (SRP)**: Mỗi file/module chỉ có một trách nhiệm duy nhất.
  - **Open/Closed (OCP)**: Mở cho việc mở rộng, đóng cho việc sửa đổi.
  - **Liskov Substitution (LSP)**: Lớp con thay thế được lớp cha mà không gây crash.
  - **Interface Segregation (ISP)**: Không ép module triển khai các hàm không dùng.
  - **Dependency Inversion (DIP)**: Tầng cao phụ thuộc vào Abstraction, không phụ thuộc chi tiết.
- **K.I.S.S (Keep It Simple, Stupid)**: Giữ giải pháp đơn giản nhất, không over-engineer.
- **Y.A.G.N.I (You Aren't Gonna Need It)**: Chỉ viết code cần thiết cho hiện tại.
- **D.R.Y (Don't Repeat Yourself)**: Không copy-paste code trùng lặp.

---

## 🎮 2. CƠ CHẾ ĐIỀU KHIỂN AGENT (AGENTIC OPERATING DIRECTIVES)

1. **Spec & Plan First**: Luôn nghiên cứu và lập file `implementation_plan.md` cho người dùng duyệt trước khi đụng vào mã nguồn.
2. **Incremental Task Slicing**: Chia nhỏ công việc thành các lát cắt nhỏ (Walking Skeleton), kiểm thử được ngay.
3. **Test-Driven Verification**: Sau khi sửa code, BẮT BỘC tự chạy unit tests (`pytest`) chứng minh bằng log thực tế trước khi báo hoàn thành.
4. **Log Inspection (No Guessing)**: Khi gặp lỗi, BẮT BỘC đọc log/traceback thực tế trước khi chẩn đoán. Cấm đoán mò hoặc giấu lỗi bằng `try/except: pass`.
5. **No Hardcoded Variables**: Không bao giờ hardcode đường dẫn tuyệt đối hay API Keys. Dùng `pathlib.Path` và `.env`.
6. **Structured Logging**: Sử dụng module `logging` chuẩn. KHÔNG DÙNG `print()`.
7. **Type Hints & Docstrings**: 100% hàm Python phải khai báo Type Hints và Docstrings rõ ràng.

---

## 🌿 3. QUY TRÌNH GIT & THÔNG ĐIỆP COMMIT

- **Branch Rules**: Không push trực tiếp lên `main`. Tạo branch `feature/...`, `fix/...`, `eval/...`.
- **Conventional Commits**:
  - `feat`: Tính năng mới.
  - `fix`: Sửa lỗi bug.
  - `docs`: Tài liệu/README.
  - `eval`: Đánh giá RAGAS/Benchmark.
  - `refactor`: Tối ưu code.
  - `chore`: Cấu hình Docker/CI.

---

## 🏗️ 4. KIẾN TRÚC DỰ ÁN ARCHITECTURE
- **Pattern**: Modular Monolith + Layered DDD (`app/`, `rag/`, `agent/`, `evaluation/`).
- **Tech Stack**: FastAPI (Backend) + React.js (Frontend) + ChromaDB (Vector Store) + Docker Compose + GitHub Actions CI.


## 🐍 5. PYTHON & FASTAPI BEST PRACTICES

### 5.1 Type Hinting & Pydantic (Strict Mode)
- **100% Type Hints**: Bắt buộc phải có type hints cho tham số đầu vào và đầu ra của TẤT CẢ các hàm/method.
- **Pydantic v2**: Sử dụng syntax của Pydantic v2 (`model_config = ConfigDict(from_attributes=True)`, `model_dump()`, `model_validate()`). Không dùng cú pháp cũ của v1 (`class Config: orm_mode = True`, `dict()`).
- **Optional & Union**: Rõ ràng khi biến có thể là `None` (dùng `Optional[T]` hoặc `T | None`).

### 5.2 SQLAlchemy 2.0 Style
- **Khai báo Model**: Bắt buộc sử dụng `Mapped` và `mapped_column` cho Declarative Models (SQLAlchemy 2.0+). Tránh dùng kiểu khai báo cũ `Column(String)`.
- **Querying**: Bắt buộc dùng 2.0 style query: `stmt = select(Model).where(...)` và `db.scalars(stmt).all()`. TÚYỆT ĐỐI KHÔNG sử dụng legacy query style `db.query(Model).filter(...)`.
- **Unit of Work**: Hạn chế số lần gọi `db.commit()` trong một request. Gom các thao tác thay đổi dữ liệu và gọi commit 1 lần duy nhất cuối transaction.

### 5.3 Lỗi & Exception Handling
- **Custom Exceptions**: Kế thừa `HTTPException` cho các lỗi API API (trả về 400, 401, 403, 404). Các lỗi business logic ở tầng Service (như `ValueError`) phải được catch ở tầng API/Router và map sang HTTP status code tương ứng.
- **Không bao giờ dùng "catch-all"**: Không được viết `except Exception:` mà không log ra lỗi kèm traceback. Tối thiểu phải là `logger.error(f"Error details: {e}", exc_info=True)`.

---

## 🏗️ 6. KIẾN TRÚC & DEPENDENCY INJECTION

### 6.1 Dependency Injection (DI)
- Tầng Router/API **KHÔNG** chứa logic nghiệp vụ phức tạp. Nhiệm vụ của Router là: Validate request → Gọi Service (qua DI) → Format response.
- Khởi tạo Service nên thông qua FastAPI `Depends()`. Tránh việc gọi cứng `_service = MyService()` ở global scope của file route.

### 6.2 Abstraction & Interfaces (Đặc biệt cho Memory AI)
- Đối với các component có thể thay thế trong tương lai (Ví dụ: Memory Storage, Embedder, LLM Client), hãy dùng **Abstract Base Class (ABC)** hoặc **Protocols**.
- Code tầng logic phải dựa vào Interface, không dựa vào implementation cụ thể (Dependency Inversion).
  *Ví dụ:* `MemoryStore(ABC)` → `PostgresMemoryStore(MemoryStore)` / `RedisMemoryStore(MemoryStore)`.

---

## ⚡ 7. PERFORMANCE & ASYNC RULES

- **Không Block Event Loop**: FastAPI là asynchronous framework. Tuyệt đối không gọi các hàm đồng bộ chặn I/O dài (như LLM call, external API requests) trong hàm `async def` mà không đưa vào threadpool (dùng `run_in_threadpool`).
- **Sync vs Async**: Nếu dùng SQLAlchemy Sync (`Session`), endpoint phải là `def` (không có `async`). Nếu đổi sang SQLAlchemy Async (`AsyncSession`), endpoint phải là `async def`.
- **Background Tasks**: Với các tác vụ tốn thời gian nhưng không yêu cầu response ngay (như Fact Extraction, Vector Indexing), **bắt buộc** phải dùng FastAPI `BackgroundTasks` hoặc Celery. Không bắt user chờ HTTP request hoàn thành.

---

## 🧪 8. TESTING MÀ AI PHẢI TUÂN THỦ

- **Test Độc Lập (Isolated)**: Unit tests không được gọi đến DB thật hay API thật. Phải mock LLM responses và External APIs.
- **Cấu trúc Arrange - Act - Assert**: Mọi test case phải chia làm 3 phần rõ ràng: chuẩn bị dữ liệu (Arrange), thực thi hành động (Act), và kiểm tra kết quả (Assert).
- **Test Edge Cases**: Phải có test cho failure path (thất bại khi LLM trả về JSON sai định dạng, ChromaDB bị timeout, user không có quyền truy cập).

---

## 💡 Hướng dẫn cho AI: "Chain of Thought" trước khi code
Mỗi khi bắt đầu code một tính năng mới cho Memory AI, Agent **phải tự trả lời 3 câu hỏi**:
1. *Cái này có block luồng chính (I/O blocking) không? Nếu có, đẩy sang BackgroundTask/Celery chưa?*
2. *Lỗi có thể xảy ra ở đâu và đã bắt (catch) đúng cách chưa?*
3. *Đã query DB hiệu quả chưa (giảm N+1 query, dùng SQLAlchemy 2.0)?*

