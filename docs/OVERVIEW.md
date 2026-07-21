# Vietnam Travel Recommendation Agent — Implementation Plan

## 1. Tổng quan dự án (Project Overview)

### Mục tiêu
Xây dựng một **AI Agent** hỗ trợ khách du lịch tìm kiếm và gợi ý các địa điểm **ăn uống / vui chơi tại Việt Nam**. Agent sử dụng kiến trúc **RAG (Retrieval-Augmented Generation)** kết hợp với **Google Maps API** để cung cấp thông tin chính xác, phong phú và cập nhật.

### Đối tượng người dùng
- Khách du lịch (trong nước và quốc tế) đang hoặc sắp đến Việt Nam

### Phạm vi MVP (Phase 1)
- **Chức năng**: Gợi ý địa điểm ăn uống / vui chơi (chưa lên lịch trình)
- **Địa lý**: 3 thành phố lớn — Hà Nội, TP.HCM, Đà Nẵng/Hội An
- **Ngôn ngữ**: Tiếng Việt (mở rộng tiếng Anh ở phase sau)

---

## 2. Kiến trúc hệ thống (System Architecture)

### Lộ trình phát triển tổng thể

```
Phase 1: Naive RAG                    ← BẠN ĐANG Ở ĐÂY
├── Xây pipeline RAG từ đầu (không dùng framework)
├── Dữ liệu tĩnh từ vietnam.travel
├── ChromaDB (local vector store)
├── LLM open-source (Qwen 2.5 qua Ollama)
└── Giao diện: Terminal / Notebook

Phase 2: Advanced RAG
├── Tối ưu chunking strategy
├── Re-ranking kết quả tìm kiếm
├── Query transformation
└── Hybrid Search (keyword + semantic)

Phase 3: Agentic RAG
├── Agent tự quyết định khi nào search RAG vs gọi Google Maps
├── Tích hợp Google Maps Places API làm Tool
├── Multi-step reasoning
├── Sử dụng framework (LangChain / LlamaIndex)
└── Giao diện: Web UI (chat-based)

Phase 4: Multi-Agent System
├── Chuyên biệt hóa: Food Agent, Activity Agent, Transport Agent
├── Planning Agent điều phối tổng thể
├── Memory Bank (nhớ sở thích user qua nhiều phiên)
└── Tích hợp thêm: Weather API, Google Search Grounding
```

### Kiến trúc Phase 1 — Naive RAG

```
┌─────────────────────────────────────────────────────┐
│                    USER QUERY                       │
│         "Hà Nội có quán phở nào ngon?"              │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              EMBEDDING MODEL (local)                │
│         Query → Vector (384/768 dimensions)         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              CHROMADB (Vector Store)                 │
│    Similarity Search → Top-K relevant chunks        │
│                                                     │
│  Chunk 1: "Phở Hà Nội nổi tiếng với nước dùng..."  │
│  Chunk 2: "Old Quarter street food guide..."        │
│  Chunk 3: "Must-try noodles in Vietnam..."          │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│                 LLM (Qwen 2.5 - Ollama)             │
│                                                     │
│  System: "Bạn là trợ lý du lịch Việt Nam..."       │
│  Context: [Retrieved chunks]                        │
│  Query: "Hà Nội có quán phở nào ngon?"              │
│                                                     │
│  → Tổng hợp câu trả lời từ context + knowledge     │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│                   RESPONSE                          │
│  "Phở là linh hồn ẩm thực Hà Nội! Nước dùng       │
│   truyền thống được ninh từ xương bò với hồi..."   │
└─────────────────────────────────────────────────────┘
```

### Kiến trúc Phase 3 — Agentic RAG (Tương lai)

```
┌──────────────┐
│  USER QUERY  │
└──────┬───────┘
       ▼
┌──────────────────────────────┐
│      AGENT (LLM + ReAct)     │
│  "Tôi cần search RAG trước, │
│   rồi gọi Maps để lấy       │
│   địa chỉ cụ thể"           │
└──────┬───────────────────────┘
       │
       ├──── Tool 1: RAG Search ──────► ChromaDB
       │     (kiến thức tổng quan)       "Phở Hà Nội đặc trưng bởi..."
       │
       ├──── Tool 2: Google Maps ─────► Places API
       │     (data thời gian thực)       "Phở Thìn: 4.5⭐, 13 Lò Đúc..."
       │
       └──── Tool 3: Weather API ─────► OpenWeather
             (ngữ cảnh thời tiết)        "Hà Nội: 28°C, trời nắng"
```

---

## 3. Tech Stack

| Thành phần | Công nghệ | Lý do chọn |
|---|---|---|
| **Language** | Python 3.11+ | Hệ sinh thái AI/ML phong phú nhất |
| **LLM** | Qwen 2.5 (7B) qua Ollama | Open-source, tiếng Việt tốt nhất, chạy local miễn phí |
| **Embedding Model** | `sentence-transformers/all-MiniLM-L6-v2` hoặc `BAAI/bge-m3` | Nhẹ, hỗ trợ multilingual (cả tiếng Việt) |
| **Vector Database** | ChromaDB | Đơn giản, không cần server, `pip install` là xong |
| **Framework (Phase 1)** | Không dùng — xây từ đầu | Học sâu RAG pipeline, hiểu từng bước |
| **Framework (Phase 3+)** | LangChain hoặc LlamaIndex | Orchestration agent, tool routing, memory management |
| **Data Source 1** | vietnam.travel (crawl → Markdown) | Nguồn chính thức, nội dung chất lượng cao |
| **Data Source 2** | Google Maps Places API | Data real-time: tên quán, địa chỉ, rating, review |
| **Evaluation** | RAGAS framework | Đánh giá tự động chất lượng RAG |

---

## 4. Nguồn dữ liệu (Data Strategy)

### 4.1. Nguồn chính: vietnam.travel (Crawl → RAG)

Đây là **trang chính thức của Tổng cục Du lịch Việt Nam**. Nội dung chất lượng cao, có cấu trúc rõ ràng.

**Các section cần crawl:**

| Nhóm | URL Pattern | Nội dung | Số trang |
|---|---|---|---|
| **Places** | `/places-to-go/{region}/{city}` | Tổng quan thành phố, weather, transport, hotels | ~18 |
| **Food** | `/things-to-do/food/*` | Bài viết ẩm thực chi tiết | ~50 |
| **Activities** | `/things-to-do/{culture,nature,adventure,beaches,cities}/*` | Hoạt động vui chơi | ~30 |

**Quy trình xử lý dữ liệu:**

```
Crawl HTML ─► Parse & Clean ─► Chunk ─► Embed ─► Store (ChromaDB)
   │              │              │          │           │
   │         Loại bỏ:       500-1000    Model:     Collection:
   │         - Menu/Nav      tokens    bge-m3     "vietnam_travel"
   │         - Footer        mỗi       hoặc
   │         - CSS/JS       chunk     MiniLM
   │         - Duplicates
   │
   └── ~100 trang HTML
```

**Lưu ý quan trọng:**
- Nội dung vietnam.travel là **tiếng Anh** → Giữ nguyên tiếng Anh trong RAG, LLM sẽ tự dịch sang tiếng Việt khi trả lời (tránh mất thông tin do dịch sai)
- Trang web không có API → Cần viết scraper parse HTML

### 4.2. Nguồn bổ sung: Google Maps Places API (Phase 3)

| Vai trò | Chi tiết |
|---|---|
| **Mục đích** | Cung cấp thông tin real-time về địa điểm cụ thể |
| **Data trả về** | Tên quán, địa chỉ, rating, reviews, giờ mở cửa, số điện thoại, link Maps |
| **API cần dùng** | Places API (New) — `textSearch`, `nearbySearch`, `getPlaceDetails` |
| **Auth** | Google Maps API Key |
| **Chi phí** | Free $200/tháng (đủ cho prototype) |

### 4.3. Bảng so sánh vai trò 2 nguồn dữ liệu

```
vietnam.travel (RAG)              Google Maps API (Tool)
─────────────────────             ──────────────────────
• Tổng quan thành phố            • Tên quán cụ thể
• Đặc sản vùng miền              • Địa chỉ chính xác
• Mùa du lịch tốt nhất           • Rating + Reviews mới nhất
• Hoạt động văn hóa              • Giờ mở cửa
• Lịch sử, câu chuyện            • Số điện thoại
• Tips di chuyển                  • Link Google Maps
• Lễ hội / sự kiện

→ TRẢ LỜI: "Hà Nội có gì hay?"  → TRẢ LỜI: "Quán phở nào ngon ở Q.1?"
→ Kiến thức nền, context         → Thông tin cụ thể, real-time
```

---

## 5. Các bước triển khai chi tiết (Implementation Steps)

### Phase 1: Naive RAG (4-6 tuần)

#### Bước 1.1: Chuẩn bị môi trường (1-2 ngày)

```bash
# Cài đặt Ollama + Pull model
brew install ollama        # hoặc curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b     # hoặc qwen2.5:14b nếu máy đủ RAM

# Tạo Python virtual environment
cd ~/Documents/Projects/travel-agent
python -m venv .venv
source .venv/bin/activate

# Cài dependencies
pip install chromadb sentence-transformers requests beautifulsoup4 ollama
```

**Cấu trúc thư mục dự kiến:**

```
travel-agent/
├── .agents-cli-spec.md          # Đặc tả project (đã tạo)
├── data/
│   ├── raw/                     # HTML thô từ vietnam.travel
│   ├── processed/               # Markdown đã clean
│   └── chunks/                  # Chunks đã chia (JSON)
├── src/
│   ├── scraper/
│   │   ├── crawl.py             # Crawl HTML từ vietnam.travel
│   │   └── parse.py             # Parse HTML → clean Markdown
│   ├── rag/
│   │   ├── chunker.py           # Chia document thành chunks
│   │   ├── embedder.py          # Tạo embeddings
│   │   ├── store.py             # Lưu/truy vấn ChromaDB
│   │   └── pipeline.py          # RAG pipeline chính
│   ├── llm/
│   │   └── client.py            # Wrapper gọi Ollama
│   └── main.py                  # Entry point
├── notebooks/
│   └── 01_rag_prototype.ipynb   # Notebook thử nghiệm
├── tests/
│   └── test_rag.py
├── eval/
│   ├── dataset.json             # Bộ test đánh giá
│   └── evaluate.py              # Script chạy RAGAS
├── requirements.txt
└── README.md
```

#### Bước 1.2: Thu thập dữ liệu — Crawl vietnam.travel (2-3 ngày)

**Mục tiêu:** Crawl ~80-100 trang → Parse thành Markdown sạch

**Danh sách URL cần crawl:**

```python
# Places to go (18 cities)
places_urls = [
    "/places-to-go/northern-vietnam/ha-noi",
    "/places-to-go/northern-vietnam/ha-giang",
    "/places-to-go/northern-vietnam/ha-long",
    "/places-to-go/northern-vietnam/mai-chau",
    "/places-to-go/northern-vietnam/ninh-binh",
    "/places-to-go/northern-vietnam/sapa",
    "/places-to-go/central-vietnam/da-nang",
    "/places-to-go/central-vietnam/dalat",
    "/places-to-go/central-vietnam/hoi-an",
    "/places-to-go/central-vietnam/hue",
    "/places-to-go/central-vietnam/nha-trang",
    "/places-to-go/central-vietnam/phong-nha",
    "/places-to-go/southern-vietnam/ho-chi-minh-city",
    "/places-to-go/southern-vietnam/con-dao",
    "/places-to-go/southern-vietnam/binh-thuan",
    "/places-to-go/southern-vietnam/can-tho",
    "/places-to-go/southern-vietnam/chau-doc",
    "/places-to-go/southern-vietnam/phu-quoc",
]

# Food articles (crawl listing page, extract article links)
food_listing = "/things-to-do/food"

# Activity articles
activity_listings = [
    "/things-to-do/culture",
    "/things-to-do/nature",
    "/things-to-do/adventure",
    "/things-to-do/cities",
    "/things-to-do/beaches",
]
```

**Quy trình:**
1. Crawl HTML thô → Lưu vào `data/raw/`
2. Parse HTML: Extract phần `#overview`, loại bỏ nav/footer/script
3. Convert sang clean Markdown → Lưu vào `data/processed/`
4. Thêm metadata vào mỗi file (city, category, source_url)

#### Bước 1.3: Xây dựng RAG Pipeline (1-2 tuần)

**Đây là phần học quan trọng nhất.** Xây từ đầu để hiểu từng bước:

**a) Chunking (`src/rag/chunker.py`)**
- Input: Markdown files từ `data/processed/`
- Strategy: **Recursive character splitting** — chia theo heading → paragraph → sentence
- Chunk size: 500-1000 tokens
- Overlap: 100-200 tokens (để không mất context ở ranh giới chunk)
- Output: JSON array với mỗi chunk kèm metadata (source, city, category)

**b) Embedding (`src/rag/embedder.py`)**
- Model gợi ý: `BAAI/bge-m3` (multilingual, hỗ trợ tiếng Việt + Anh)
- Hoặc nhẹ hơn: `sentence-transformers/all-MiniLM-L6-v2`
- Chạy local qua `sentence-transformers` library

**c) Vector Store (`src/rag/store.py`)**
- Sử dụng ChromaDB
- Collection: `vietnam_travel`
- Lưu: embedding + metadata (source, city, category, chunk_index)
- Query: similarity search, top-k = 3-5

**d) LLM Client (`src/llm/client.py`)**
- Gọi Qwen 2.5 qua Ollama API (localhost:11434)
- System prompt:
  ```
  Bạn là một trợ lý du lịch thông minh chuyên về Việt Nam.
  Hãy trả lời bằng tiếng Việt, thân thiện và hữu ích.
  Chỉ trả lời dựa trên thông tin được cung cấp trong context.
  Nếu không có đủ thông tin, hãy nói rõ.
  ```

**e) Pipeline (`src/rag/pipeline.py`)**
- Kết nối tất cả: Query → Embed → Search → Build Prompt → LLM → Response

#### Bước 1.4: Thử nghiệm & Đánh giá (1 tuần)

**a) Test thủ công:**
```python
# Các câu hỏi test mẫu
test_queries = [
    "Hà Nội có đặc sản gì nổi tiếng?",
    "Tôi đang ở Đà Nẵng, có gì vui chơi ở đây?",
    "Khi nào là thời điểm tốt nhất để đi Sapa?",
    "Hội An có món gì phải thử?",
    "TP.HCM có khu phố ăn uống nào nổi tiếng?",
]
```

**b) Đánh giá tự động bằng RAGAS:**

| Metric | Ý nghĩa | Mục tiêu Phase 1 |
|---|---|---|
| **Faithfulness** | Câu trả lời có đúng với context không? (Không hallucinate) | ≥ 0.8 |
| **Answer Relevancy** | Câu trả lời có liên quan đến câu hỏi không? | ≥ 0.7 |
| **Context Precision** | Các chunks tìm được có chính xác không? | ≥ 0.7 |
| **Context Recall** | Có bỏ sót thông tin quan trọng không? | ≥ 0.6 |

#### Bước 1.5: Iterative Improvement (1 tuần)

Dựa trên kết quả đánh giá, lặp lại và cải thiện:
- Điều chỉnh chunk size / overlap
- Thử embedding model khác
- Tối ưu system prompt
- Bổ sung dữ liệu ở các vùng yếu

---

### Phase 2: Advanced RAG (2-3 tuần)

| Kỹ thuật | Mô tả | Vấn đề giải quyết |
|---|---|---|
| **Query Transformation** | Viết lại câu hỏi trước khi search (HyDE, Multi-Query) | User hỏi mơ hồ → search không chính xác |
| **Re-ranking** | Dùng cross-encoder để re-rank kết quả sau semantic search | Top-K có chunk không liên quan |
| **Hybrid Search** | Kết hợp BM25 (keyword) + Semantic search | "Phở Thìn" là tên riêng → semantic search yếu |
| **Metadata Filtering** | Filter theo city/category trước khi search | Giảm noise khi user đã nói rõ thành phố |

---

### Phase 3: Agentic RAG (3-4 tuần)

| Bước | Mô tả |
|---|---|
| **3.1** | Chuyển sang framework (LangChain/LlamaIndex) |
| **3.2** | Tích hợp Google Maps Places API làm Tool |
| **3.3** | Implement ReAct loop — Agent tự quyết định dùng tool nào |
| **3.4** | Xây Web UI (chat interface) |
| **3.5** | Thêm context: vị trí user, thời gian, thời tiết |

**Agent Decision Flow:**
```
User: "Gợi ý quán phở ngon gần Hồ Gươm"

Agent suy nghĩ:
  → Bước 1: Search RAG → Hiểu về phở Hà Nội (context)
  → Bước 2: Gọi Google Maps → textSearch("phở", near="Hồ Gươm, Hà Nội")
  → Bước 3: Kết hợp RAG context + Maps data → Trả lời
```

---

### Phase 4: Multi-Agent System (4-6 tuần)

```
                    ┌─────────────────────┐
                    │   Planning Agent     │
                    │ (Điều phối tổng thể) │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
     ┌────────────┐  ┌────────────┐  ┌────────────────┐
     │ Food Agent │  │ Activity   │  │ Transport      │
     │            │  │ Agent      │  │ Agent          │
     │ • Ẩm thực  │  │ • Vui chơi │  │ • Di chuyển    │
     │ • Nhà hàng │  │ • Văn hóa  │  │ • Phương tiện  │
     │ • Quán ăn  │  │ • Thiên    │  │ • Lộ trình     │
     │            │  │   nhiên    │  │                │
     └────────────┘  └────────────┘  └────────────────┘
```

---

## 6. Ràng buộc & Quy tắc an toàn (Constraints & Safety)

| Quy tắc | Chi tiết |
|---|---|
| **Phạm vi địa lý** | Chỉ gợi ý địa điểm tại Việt Nam |
| **Phạm vi chủ đề** | Chỉ trả lời về du lịch, ẩm thực, vui chơi, di chuyển |
| **Không bịa đặt** | Không fabricate địa chỉ, rating, số điện thoại — chỉ dùng dữ liệu từ RAG hoặc API |
| **Không giao dịch** | Không xử lý thanh toán hoặc đặt phòng — chỉ gợi ý |
| **Minh bạch** | Nói rõ khi không có đủ thông tin thay vì đoán |

---

## 7. Tiêu chí đánh giá (Evaluation Criteria)

### Phase 1 — RAG Quality

| Metric | Mục tiêu | Tool |
|---|---|---|
| Faithfulness | ≥ 0.8 | RAGAS |
| Answer Relevancy | ≥ 0.7 | RAGAS |
| Context Precision | ≥ 0.7 | RAGAS |
| Context Recall | ≥ 0.6 | RAGAS |

### Phase 3 — Agent Quality

| Metric | Mục tiêu |
|---|---|
| Tool Selection Accuracy | ≥ 85% chọn đúng tool |
| Task Completion Rate | ≥ 80% trả lời được câu hỏi |
| Geographic Accuracy | 100% gợi ý đúng khu vực user yêu cầu |

---

## 8. Chi phí ước tính

| Phase | Thành phần | Chi phí |
|---|---|---|
| Phase 1 | LLM (Ollama local) | $0 |
| Phase 1 | ChromaDB (local) | $0 |
| Phase 1 | Embedding model (local) | $0 |
| Phase 3 | Google Maps API | Free $200/tháng |
| Phase 3+ | Cloud hosting (nếu deploy) | Tùy chọn |

> **Tổng chi phí Phase 1: ~$0** (chỉ cần máy tính đủ RAM 8-16GB)

---

## 9. Rủi ro & Giải pháp (Risks & Mitigations)

| Rủi ro | Xác suất | Giải pháp |
|---|---|---|
| LLM open-source trả lời tiếng Việt kém | Trung bình | Thử nhiều model (Qwen → Gemma → Llama), tối ưu prompt |
| vietnam.travel thay đổi cấu trúc HTML | Thấp | Lưu data đã crawl, có script re-crawl |
| ChromaDB không đủ performance khi scale | Thấp (Phase 1) | Chuyển sang Qdrant/Weaviate ở phase sau |
| Chunk size không phù hợp → search kém | Cao | Thử nhiều kích thước, đánh giá bằng RAGAS |
| Hallucination (Agent bịa thông tin) | Trung bình | System prompt chặt, Faithfulness metric trong eval |

---

## 10. Câu hỏi mở cần quyết định (Open Questions)

> [!IMPORTANT]
> Các câu hỏi dưới đây cần được quyết định trước khi bắt đầu code:

1. **Scraper**: Bạn muốn tự viết scraper để học thêm, hay tôi hỗ trợ crawl sẵn thành Markdown files?
2. **Ngôn ngữ data**: Giữ nguyên tiếng Anh trong RAG (LLM tự dịch khi trả lời), hay dịch toàn bộ sang tiếng Việt trước khi lưu?
3. **Embedding model**: Dùng `bge-m3` (multilingual, nặng hơn) hay `all-MiniLM-L6-v2` (nhẹ, nhanh hơn)?
4. **Máy bạn có bao nhiêu RAM?** (Ảnh hưởng đến việc chọn model 7B hay 14B)
5. **Bạn đã cài Ollama và Python chưa?**
