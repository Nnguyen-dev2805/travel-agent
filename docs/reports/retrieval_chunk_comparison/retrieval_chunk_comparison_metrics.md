# Báo Cáo Đánh Giá Chi Tiết Retrieval RAG: Baseline vs Parent-Child Strategy

## 1. Kết Quả Đo Đạc Tổng Thể (7 Chỉ Số trên các Mức K)

Tập dữ liệu kiểm thử: `retrieval_benchmark_1405_testset.json` (2 test queries)

### 📌 1.1. Bảng So Sánh Hit Rate & MRR

| Mức K | Hit Rate (Baseline) | Hit Rate (Parent-Child) | Hit Rate Gain | MRR (Baseline) | MRR (Parent-Child) | MRR Gain |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **K=1** | 50.00% | **50.00%** | **+0.0%** | 0.5000 | **0.5000** | **+0.0000** |
| **K=3** | 50.00% | **100.00%** | **+50.0%** | 0.5000 | **0.6667** | **+0.1667** |
| **K=5** | 100.00% | **100.00%** | **+0%** | 0.6000 | **0.6667** | **+0.0667** |
| **K=10** | 100.00% | **100.00%** | **+0%** | 0.6000 | **0.6667** | **+0.0667** |
| **K=20** | 100.00% | **100.00%** | **+0%** | 0.6000 | **0.6667** | **+0.0667** |

### 📌 1.2. Bảng So Sánh NDCG & Precision

| Mức K | NDCG (Baseline) | NDCG (Parent-Child) | NDCG Gain | Precision (Baseline) | Precision (Parent-Child) | Precision Gain |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **K=1** | 0.5000 | **0.5000** | **+0.0000** | 50.00% | **50.00%** | **+0.0%** |
| **K=3** | 0.3520 | **0.6173** | **+0.2653** | 33.33% | **66.67%** | **+33.34%** |
| **K=5** | 0.3730 | **0.5976** | **+0.2246** | 30.00% | **60.00%** | **+30.0%** |
| **K=10** | 0.5852 | **0.6627** | **+0.0775** | 30.00% | **50.00%** | **+20.0%** |
| **K=20** | 0.6251 | **0.7583** | **+0.1332** | 17.50% | **30.00%** | **+12.5%** |

## 2. Báo Cáo Xuất CSV Chi Tiết

Tất cả các file báo cáo CSV chi tiết đã được tự động lưu vào thư mục: `/Users/tnhatnguyendev2805/Documents/Projects/travel-agent/docs/reports/retrieval_chunk_comparison`

1. **`summary_by_run.csv`**: Bảng tổng hợp đầy đủ 7 metric trên 5 mức K.
2. **`summary_by_category.csv`**: Phân tích hiệu năng theo từng danh mục bài viết (`Nightlife`, `Food`, `Beach`...).
3. **`summary_by_url_group.csv`**: Phân tích hiệu năng theo nhóm đường dẫn (`things-to-do`, `plan-your-trip`...).
4. **`top_failures_at_20.csv`**: Danh sách các câu hỏi bị thất bại (Hit@20 = 0) để phục vụ công tác audit dữ liệu.