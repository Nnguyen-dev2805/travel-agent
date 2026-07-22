# Tổng Quan Hệ Thống Và Pipeline RAG Du Lịch Việt Nam

Tài liệu này dùng để onboarding collaborator vào dự án Chatbot Du lịch Việt Nam sử dụng Agentic AI + RAG. Mục tiêu là giúp người mới hiểu nhanh hệ thống hiện tại đã làm gì, dữ liệu đi qua các tầng nào, mỗi module nằm ở đâu, và các task đã hoàn thành phục vụ mục tiêu gì.

## 1. Mục Tiêu Hệ Thống

Hệ thống hướng tới một AI Assistant có khả năng trả lời câu hỏi du lịch Việt Nam dựa trên knowledge base đã crawl và xử lý sạch. Trọng tâm hiện tại chưa phải Agent nhiều bước hoàn chỉnh, mà là xây nền RAG đủ tốt:

- Làm sạch HTML từ nguồn du lịch.
- Chuyển HTML thành document sạch.
- Chunk dữ liệu theo baseline Standard RAG.
- Tạo embedding và lưu FAISS index.
- Xây retriever baseline: dense, BM25, hybrid.
- Tạo test set và đánh giá retrieval.
- Xây prompt cho `gpt-4o-mini`.
- Xây notebook pipeline VI -> EN retrieval -> answer.
- Xây giao diện Streamlit chatbot để demo.

Quan điểm kỹ thuật chính của dự án là: chất lượng dữ liệu và retrieval quan trọng hơn việc tối ưu sớm model generation.

## 2. Pipeline Tổng Thể

Pipeline hiện tại có thể hiểu theo luồng sau:

```text
Raw Crawl Data / Clean Documents
        ↓
Standard RAG Preprocessing
        ↓
Standard Documents
        ↓
Fixed-size Chunking Baseline
        ↓
Chunks JSONL
        ↓
Embedding Model
        ↓
FAISS Index + Metadata
        ↓
Retriever
   ├── Dense FAISS
   ├── BM25
   └── Hybrid BM25 + Dense
        ↓
Prompt Builder
        ↓
gpt-4o-mini / OpenAI-compatible API
        ↓
Vietnam Travel Answer
        ↓
Notebook Pipeline / Streamlit Chatbot
```

## 3. Dữ Liệu Chính

Các file dữ liệu quan trọng:


| File                                                                            | Vai trò                                         |
| ------------------------------------------------------------------------------- | ----------------------------------------------- |
| `data/clean_documents_full.jsonl`                                               | Dữ liệu document sạch ban đầu sau cleaning HTML |
| `data/processed/standard_rag_documents.jsonl`                                   | Document đầu vào cho baseline Standard RAG      |
| `data/chunks/chunks_standard_rag.jsonl`                                         | Chunks fixed-size baseline                      |
| `data/indexes/paraphrase-multilingual-MiniLM-L12-v2_standard_rag/index.faiss`   | FAISS vector index                              |
| `data/indexes/paraphrase-multilingual-MiniLM-L12-v2_standard_rag/metadata.json` | Metadata sidecar cho từng vector/chunk          |
| `data/evaluation/document_user_query_testset.jsonl`                             | Test set query sinh theo document               |
| `data/evaluation/traveler_need_queries_500.jsonl`                               | 500 query nhu cầu người đi du lịch              |


Lưu ý: FAISS chỉ lưu vector để search nhanh. Nội dung text, URL, title, document id, chunk id nằm trong `metadata.json`. Khi retrieval, FAISS trả về id vector, sau đó hệ thống map ngược sang metadata để lấy text/context.

## 4. Cấu Trúc Backend RAG

```text
backend/rag/
├── preprocessing/
│   └── standard_preprocessor.py
├── chunking/
│   └── standard_chunker.py
├── embedding/
│   ├── embedding_model_registry.py
│   └── faiss_embedding_pipeline.py
├── retrieval/
│   └── baseline_retrievers.py
├── generation/
│   └── prompt_builder.py
├── evaluation/
│   ├── generate_document_user_query_testset.py
│   ├── generate_traveler_need_queries.py
│   ├── llm_judge_retrieval.py
│   └── run_llm_judge_three_retrievers.py
└── notebooks/
    └── vi_to_en_retrieval_gpt4o_mini_pipeline.ipynb
```

Vai trò từng nhóm:

- `preprocessing`: chuẩn hóa dữ liệu document cho baseline.
- `chunking`: tạo chunk fixed-size baseline.
- `embedding`: cấu hình model embedding, tạo embedding, ghi FAISS.
- `retrieval`: dense FAISS, BM25, hybrid BM25 + Dense.
- `generation`: build prompt cho `gpt-4o-mini`.
- `evaluation`: sinh test set và đánh giá retrieval.
- `notebooks`: pipeline chạy thử end-to-end bằng notebook.

## 5. Retrieval Hiện Tại

Module chính:

```text
backend/rag/retrieval/baseline_retrievers.py
```

Retriever hiện có:


| Retriever                  | Ý tưởng                                          | Khi dùng                                 |
| -------------------------- | ------------------------------------------------ | ---------------------------------------- |
| `DenseFaissRetriever`      | Embed query rồi search vector trong FAISS        | Query ngữ nghĩa, diễn đạt tự nhiên       |
| `BM25Retriever`            | Search lexical theo token và IDF                 | Query có keyword rõ, tên địa điểm/món ăn |
| `HybridBM25DenseRetriever` | Kết hợp BM25 + Dense bằng Reciprocal Rank Fusion | Baseline mạnh nhất hiện tại              |


Mặc định nên dùng `hybrid`, vì dữ liệu du lịch vừa có semantic intent vừa có entity rõ như Huế, Đà Nẵng, Hội An, Phú Quốc, món ăn, địa điểm.

## 6. Embedding Và FAISS

Embedding model baseline hiện tại:

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

Lý do dùng baseline này:

- Nhẹ, chạy được CPU.
- Hỗ trợ multilingual, có thể search cả tiếng Việt và tiếng Anh.
- Phù hợp giai đoạn baseline trước khi so sánh các model mạnh hơn.

Các model đã được đưa vào định hướng so sánh:

- `BAAI/bge-m3`
- `multilingual-e5-large`
- `text-embedding-3-small`
- `jina-embeddings-v3`
- `Voyage-3`

Hiện tại FAISS index chính được lưu ở:

```text
data/indexes/paraphrase-multilingual-MiniLM-L12-v2_standard_rag/
├── index.faiss
└── metadata.json
```

## 7. Query Flow Trong Chatbot

Luồng hỏi đáp hiện tại:

```text
User query
    ↓
Detect language
    ↓
Nếu tiếng Anh:
    dùng query gốc để retrieval
Nếu tiếng Việt:
    mặc định dùng query gốc để retrieval vì embedding multilingual
    có thể bật tùy chọn dịch VI -> EN bằng LLM
    ↓
Retrieve top-k chunks
    ↓
Build prompt RAG
    ↓
Gọi gpt-4o-mini
    ↓
Trả lời tiếng Việt
```

Điểm quan trọng: do GitHub Models bị rate limit thường xuyên, Streamlit hiện có fallback:

- Nếu LLM bị rate limit, app vẫn hiển thị câu trả lời extractive từ retrieved chunks.
- Có thể chọn chế độ `Chỉ extractive, không gọi LLM` để test retrieval mà không phụ thuộc API.
- Nên dùng OpenRouter/OpenAI key nếu muốn demo generation ổn định hơn.

## 8. Prompt Generation

Prompt config:

```text
configs/rag_generation_prompts.json
```

Prompt hiện tại yêu cầu:

- Trả lời tiếng Việt có dấu.
- Chỉ dùng context retrieved, không bịa thêm.
- Nếu thiếu dữ liệu hoặc sai intent, phải nói rõ.
- Ưu tiên thông tin thực tế cho người đi du lịch.
- Câu trả lời có cấu trúc chuyên nghiệp hơn: nhận định, gợi ý chính, lý do/lưu ý, nguồn tham khảo.

Module build prompt:

```text
backend/rag/generation/prompt_builder.py
```

## 9. Notebook End-to-End

Notebook chính:

```text
backend/rag/notebooks/vi_to_en_retrieval_gpt4o_mini_pipeline.ipynb
```

Chức năng:

- Đọc query từ `data/evaluation/traveler_need_queries_500.jsonl`.
- Detect ngôn ngữ query.
- Nếu query tiếng Anh thì bỏ qua dịch.
- Nếu query tiếng Việt thì có thể dịch sang tiếng Anh bằng `gpt-4o-mini`.
- Retrieval bằng dense/BM25/hybrid.
- Đưa context vào `gpt-4o-mini`.
- Xuất JSON gồm query, retrieval query, answer, sources.

Output:

```text
report/evaluate/vi_to_en_retrieval_gpt4o_mini_answers.json
```

Các field quan trọng trong output:


| Field                      | Ý nghĩa                          |
| -------------------------- | -------------------------------- |
| `question_vi`              | Câu hỏi gốc                      |
| `query_en`                 | Query tiếng Anh nếu có           |
| `retrieval_query`          | Query thực sự dùng để retrieval  |
| `retrieval_query_language` | Ngôn ngữ query retrieval         |
| `translation_status`       | `skipped`, `success`, `failed`   |
| `answer_vi`                | Câu trả lời tiếng Việt           |
| `sources`                  | Các chunks/sources được retrieve |


## 10. Streamlit Chatbot

Frontend demo:

```text
frontend/streamlit_chatbot.py
```

Chạy app:

```powershell
python -m streamlit run frontend/streamlit_chatbot.py --server.port 8501
```

Tắt app:

```powershell
Ctrl + C
```

Các tùy chọn trên sidebar:


| Tùy chọn                                        | Ý nghĩa                                            |
| ----------------------------------------------- | -------------------------------------------------- |
| `Retriever`                                     | Chọn `hybrid`, `dense`, hoặc `bm25`                |
| `Top K chunks`                                  | Số chunk cuối đưa vào context                      |
| `Candidate K cho hybrid`                        | Số ứng viên lấy từ mỗi retriever trước khi fuse    |
| `Chat model`                                    | Mặc định `openai/gpt-4o-mini`                      |
| `API provider`                                  | `github`, `openrouter`, `openai`                   |
| `API key tuỳ chọn`                              | Có thể nhập nhiều OpenRouter key, mỗi key một dòng |
| `Dịch query tiếng Việt sang tiếng Anh bằng LLM` | Tắt mặc định để giảm rate limit                    |
| `Chế độ trả lời`                                | LLM + fallback hoặc extractive only                |
| `Độ chi tiết câu trả lời`                       | `Gọn`, `Chuẩn`, `Chi tiết`                         |


Khuyến nghị khi demo:

- Nếu GitHub Models bị rate limit: dùng `API provider = openrouter`.
- Nếu chỉ muốn test retrieval: chọn `Chỉ extractive, không gọi LLM`.
- Nếu muốn câu trả lời tốt hơn: chọn `Độ chi tiết câu trả lời = Chi tiết`.



## 12. Các Vấn Đề Hiện Tại

### 12.1. GitHub Models bị rate limit

Hiện GitHub Models thường trả:

```text
Too many requests
```

Ảnh hưởng:

- Không ổn định cho demo generation.
- Dễ làm bước dịch query hoặc sinh answer bị fail.

Giải pháp tạm:

- Dùng OpenRouter hoặc OpenAI API chính thức.
- Tắt dịch query VI -> EN bằng LLM.
- Dùng chế độ extractive để test retrieval.

### 12.2. Query tiếng Việt không nhất thiết phải dịch

Embedding baseline là multilingual, nên query tiếng Việt vẫn search được. Vì vậy trong Streamlit hiện mặc định không dịch query tiếng Việt để giảm API call.

Dịch VI -> EN chỉ nên bật khi:

- Corpus retrieval chủ yếu tiếng Anh.
- API ổn định.
- Muốn đánh giá riêng hiệu quả query translation.

### 12.3. Standard RAG chỉ là baseline

Fixed-size chunking không phải hướng cuối cùng. Dữ liệu du lịch có cấu trúc entity/section rõ, nên hướng tốt hơn là semantic chunking theo:

- Province.
- Category.
- Heading.
- Entity.
- Day/Route đối với itinerary.

Tài liệu liên quan:

```text
docs/ke_hoach_chunking_hybrid_vs_standard_rag.md
docs/bao_cao_trien_khai_chunking_rag_du_lich.md
```

## 13. Hướng Phát Triển Tiếp Theo

Các bước nên làm tiếp:

1. Đánh giá retrieval với full 500 query.
2. So sánh retrieval khi dùng query tiếng Việt trực tiếp và query dịch sang tiếng Anh.
3. Nâng cấp chunking từ fixed-size sang semantic/heading/entity chunking.
4. Thử embedding model mạnh hơn như BGE-M3 hoặc multilingual E5.
5. Tách service layer cho RAG pipeline thay vì để logic nằm trong Streamlit/notebook.
6. Thêm conversation memory để trả lời theo ngữ cảnh hội thoại.
7. Thêm reranker sau retrieval nếu top-k còn nhiễu.
8. Chuẩn hóa metadata: province, category, heading, source, url, language, document_id.
9. Xây evaluation dashboard cho retrieval và answer generation.

## 14. Cách Collaborator Nên Bắt Đầu

Nếu collaborator muốn hiểu nhanh hệ thống, nên đọc theo thứ tự:

1. `docs/he_thong_pipeline_va_tong_quan_task.md`
2. `docs/clean_documents_full_data_report.md`
3. `docs/ke_hoach_chunking_hybrid_vs_standard_rag.md`
4. `report/task_04_embedding_va_luu_faiss.md`
5. `report/task_05_dense_vs_hybrid_retrieval_baseline.md`
6. `report/task_06_xay_prompt_cho_gpt_4o_mini.md`
7. `frontend/streamlit_chatbot.py`

Nếu muốn chạy demo:

```powershell
python -m streamlit run frontend/streamlit_chatbot.py --server.port 8501
```

Nếu muốn test retriever bằng CLI:

```powershell
python -m backend.rag.retrieval.baseline_retrievers --query "Huế nên ăn gì?" --top-k 5
```

Nếu muốn chạy notebook end-to-end:

```text
backend/rag/notebooks/vi_to_en_retrieval_gpt4o_mini_pipeline.ipynb
```

## 15. Kết Luận

Hệ thống hiện tại đã có đủ baseline RAG end-to-end: dữ liệu sạch, chunking baseline, embedding, FAISS, retriever, prompt generation, evaluation, notebook pipeline và Streamlit demo. Điểm mạnh hiện tại là pipeline có thể kiểm tra từng tầng rõ ràng. Điểm cần cải thiện tiếp theo là chất lượng chunking, chất lượng embedding, reranking và độ ổn định API generation.

Với collaborator mới, điều quan trọng nhất là hiểu rằng đây là hệ thống đang đi theo hướng data-centric RAG: muốn chatbot tốt thì trước hết phải làm dữ liệu, chunk, metadata và retrieval tốt.