# RAG Candidate v0.1 — Báo cáo So sánh D5 (Task 7)

**Ngày:** 2026-09-04 · **Trạng thái tổng thể:** PASS · **Báo cáo bởi:** Coding agent (chờ repository-owner review — Step 10)

## Tóm tắt điều hành

Candidate `structured_runtime_v1` (Task 6 — tách `RAGService` thành `KnowledgeRetriever` / `ContextAssembler` / `LLMGenerator`) cho kết quả **không hồi quy hoàn toàn** so với baseline `current_runtime`: Hit@5 chung và cả 5 mandatory slices đều có delta **0.0**; 25/25 example có ranked evidence **giống hệt từng cặp** với baseline. Kết quả so sánh D5: **PASS** (`All applicable D5 gates pass on valid evidence`), `failed_gates=[]`.

## Runs

| | Baseline | Candidate |
| --- | --- | --- |
| Run ID | `rag-rag-current-runtime-v0.1-20260903T111946Z-6076d9e` | `rag-rag-structured-candidate-v0.1-20260904T011315Z-359a2ab` |
| Config ID | `rag-current-runtime-v0.1` | `rag-structured-candidate-v0.1` |
| Runtime adapter | `current_runtime` | `structured_runtime_v1` |
| Prompt ID | `legacy-rag-service-inline-prompt-v1` | `rag-structured-prompt-v1` |
| `code_revision` | `6076d9e` | `359a2ab` |
| `dirty_working_tree` | `true` (đã disclosed trong baseline report) | `false` |
| Dataset | `travel-agent-rag-benchmark` v0.1 | cùng |
| Eligible | 25/25 | 25/25 |
| `failure_counts` | `retrieval_miss`: 19 | `retrieval_miss`: 19 |
| `judge_config` / `answer_metrics` | `null` / `null` | `null` / `null` |

> **Provenance note:** có một candidate run trước đó `rag-rag-structured-candidate-v0.1-20260904T010932Z-359a2ab` bị compare là **INVALID** vì `run.json` không khai báo `baseline_run_id` (lệnh canonical ở plan Step 2 chưa nêu cờ `--baseline-run-id`, dù CLI đã hỗ trợ). Kết quả chính thức dùng run `011315Z` được chạy lại với cờ này; run INVALID đầu được giữ nguyên làm bằng chứng. Đây là ràng buộc sử dụng harness về provenance, **không phải** thay đổi hợp đồng so sánh.

## Phương pháp

Cùng dataset/benchmark v0.1 frozen, cùng 25 eligible examples, so sánh paired qua `python -m backend.rag.evaluation.cli compare --baseline <baseline-run-dir> --candidate <candidate-run-dir> --output <candidate-run-dir>/comparison.json`. K=5 là primary (K=1/3/10/20 để chẩn đoán).

## Overall paired deltas

| Metric | Baseline | Candidate | Delta |
| --- | --- | --- | --- |
| hit@5 | 0.24 | 0.24 | 0.0 |
| mrr@5 | 0.104667 | 0.104667 | 0.0 |
| ndcg@5 | 0.128175 | 0.128175 | 0.0 |
| hit@1 | 0.04 | 0.04 | 0.0 |
| hit@10 | 0.28 | 0.28 | 0.0 |
| hit@20 | 0.56 | 0.56 | 0.0 |

## Mandatory slices (hit@5)

| Slice | Baseline | Candidate | Delta |
| --- | --- | --- | --- |
| single_source_factual | 0.2 | 0.2 | 0.0 |
| multi_evidence_synthesis | 0.2 | 0.2 | 0.0 |
| ambiguous_underspecified | 0.0 | 0.0 | 0.0 |
| source_citation_sensitive | 0.0 | 0.0 | 0.0 |
| long_tail_difficult | 0.8 | 0.8 | 0.0 |

## Gates và final state

- `failed_gates`: `[]`
- Final state: **PASS**
- Uncertainty: `not_applicable_n_lt_30` (`paired_n=25`; benchmark v0.1 chưa mở rộng ≥ 30)
- `candidate_changes` (thông tin, không phải regression): `runtime_adapter`, `prompt_id`, `config_id`

## Failures (failure taxonomy)

19/25 examples `retrieval_miss` — giống hệt baseline. Thực tế **0/25** example có `ranked_chunk_ids` khác biệt so với baseline (spot-check toàn bộ từ `examples.jsonl`). Danh sách 19 example miss (hit@5 = 0): `rag-bench-001, rag-bench-002, rag-bench-004, rag-bench-005, rag-bench-006, rag-bench-007, rag-bench-008, rag-bench-010, rag-bench-011, rag-bench-012, rag-bench-013, rag-bench-014, rag-bench-015, rag-bench-016, rag-bench-017, rag-bench-018, rag-bench-019, rag-bench-020, rag-bench-025`.

Đây là đặc tính tồn tại từ trước của baseline (retrieval không trúng expected document với ingestion hiện tại), **không phải** regression do refactor gây ra — giữa 2 bên không có thay đổi nào về retrieval.

## Step 5 — Full answer evaluation

Chưa đánh giá. Không có protocol-valid full baseline (baseline `answer_metrics=null` do thiếu provider prerequisites ở Task 5). Theo plan Step 5: **không tuyên bố bất kỳ answer-quality promotion nào**.

## Step 6 — Regression versioning

**Không tạo** `data/evaluation/regression/`. Các `retrieval_miss` là failure tồn tại từ baseline, không phải failure bền vững mới do change gây ra; plan yêu cầu review của repository owner trước khi tạo version regression mới. Nếu owner muốn bảo vệ các trường hợp này, thực hiện theo lifecycle (reproduce → duyệt → manifest mới) ở một task riêng.

## Claim boundary

> **this R1 refactor is a no-regression candidate; no quality-improvement claim is made unless D5's separate improvement criterion is predeclared and met.**

## Artifacts

- Candidate run: `data/evaluation/runs/rag-rag-structured-candidate-v0.1-20260904T011315Z-359a2ab/{run.json,examples.jsonl,comparison.json}`
- Baseline run: `data/evaluation/runs/rag-rag-current-runtime-v0.1-20260903T111946Z-6076d9e/`
- Configs: `data/evaluation/configs/rag-structured-candidate-v0.1.json`, `data/evaluation/configs/rag-current-runtime-v0.1.json`

## Limitations

1. N=25 → uncertainty `not_applicable_n_lt_30`; không có confidence interval dùng được.
2. Không có answer layer trên cả 2 phía → không đánh giá được chất lượng sinh câu trả lời (Step 5).
3. File test `backend/tests/unit/test_evaluation_cli.py` không tồn tại trong cây (chỉ còn nodeid cũ trong `.pytest_cache`) — ghi nhận cho owner; không nằm trong phạm vi Task 7 để tạo mới.
4. Lệnh canonical plan Step 2 thiếu cờ `--baseline-run-id`; đã ghi nhận và dùng đúng cờ khi chạy.

## Review checkpoint (Step 10)

Trình repository owner: báo cáo này + per-example evidence (`examples.jsonl`) + `comparison.json`. Owner xác nhận lý do PASS và trace được aggregate → per-example trước khi chấp nhận chuyển sang Task 8.