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
