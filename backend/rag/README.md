# RAG Backend Modules

Thư mục này chứa các module xử lý RAG cho dự án Chatbot Du lịch Việt Nam.

## Cấu Trúc

```text
backend/rag/
├── preprocessing/
│   └── standard_preprocessor.py
│
├── chunking/
│   └── standard_chunker.py
│
├── embedding/
│   ├── embedding_model_registry.py
│   └── faiss_embedding_pipeline.py
│
├── evaluation/
│   └── chunk_quality_evaluator.py
│   └── retrieval_baseline_comparator.py
│   └── generate_rag_testset.py
│   └── generate_user_query_testset.py
│   └── generate_document_user_query_testset.py
│   └── document_level_retrieval_evaluator.py
│   └── generate_traveler_need_queries.py
│   └── llm_judge_retrieval.py
│
├── retrieval/
│   └── baseline_retrievers.py
│
```

## Vai Trò Từng Nhóm

| Nhóm | Vai trò |
|---|---|
| `preprocessing` | Chuẩn hóa dữ liệu đầu vào cho RAG |
| `chunking` | Tạo chunks từ document |
| `embedding` | Quản lý model embedding, tạo vector và FAISS index |
| `retrieval` | Dense FAISS, BM25 và hybrid retrievers |
| `evaluation` | Đánh giá chất lượng chunk/retrieval |

Khi chạy CLI hoặc import code, dùng đường dẫn package con:

```python
from backend.rag.embedding.faiss_embedding_pipeline import run_embedding_pipeline
```

Ví dụ lệnh:

```powershell
python -m backend.rag.preprocessing.standard_preprocessor
python -m backend.rag.chunking.standard_chunker
python -m backend.rag.embedding.faiss_embedding_pipeline
python -m backend.rag.evaluation.chunk_quality_evaluator
python -m backend.rag.retrieval.baseline_retrievers --query "Sky 36 nằm ở đâu?"
python -m backend.rag.evaluation.retrieval_baseline_comparator
python -m backend.rag.evaluation.generate_rag_testset
python -m backend.rag.evaluation.generate_user_query_testset
python -m backend.rag.evaluation.generate_document_user_query_testset
python -m backend.rag.evaluation.document_level_retrieval_evaluator
python -m backend.rag.evaluation.generate_traveler_need_queries
python -m backend.rag.evaluation.llm_judge_retrieval --dry-run --limit 3
```

## Generation

Module prompt builder cho bước sinh câu trả lời:

```powershell
python -m backend.rag.generation.prompt_builder --question "Đà Nẵng có gì chơi trong 2 ngày?"
```

File prompt config:

```text
configs/rag_generation_prompts.json
```
