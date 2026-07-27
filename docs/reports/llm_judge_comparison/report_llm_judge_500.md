# Báo Cáo Đánh Giá RAG Bằng LLM-as-a-Judge (500 Câu Hỏi Thực Tế - 6 Tiêu Chí)

## 1. Bảng Điểm Tổng Hợp 6 Tiêu Chí (Score Summary)

Tổng số câu hỏi du lịch thực tế: **2 queries**
Tỷ lệ thắng (Win Rate) Parent-Child: **100.0%** (2 thắng / 0 thua / 0 hòa)

| Tiêu chí (Metric) | Baseline Mean | Parent-Child Mean | Delta (Parent - Baseline) | Baseline Median | Parent-Child Median |
|---|:---:|:---:|:---:|:---:|:---:|
| `correctness` | 4.0 | **5.0** | **+1.0** | 4.0 | **5.0** |
| `faithfulness` | 3.0 | **4.0** | **+1.0** | 3.0 | **4.0** |
| `relevance` | 4.0 | **5.0** | **+1.0** | 4.0 | **5.0** |
| `completeness` | 3.0 | **5.0** | **+2.0** | 3.0 | **5.0** |
| `practical_usefulness` | 4.0 | **5.0** | **+1.0** | 4.0 | **5.0** |
| `clarity` | 4.0 | **5.0** | **+1.0** | 4.0 | **5.0** |
| `overall_score` | 22.0 | **29.0** | **+7.0** | 22.0 | **29.0** |

## 2. Ý Nghĩa 6 Tiêu Chí Đánh Giá

| Tiêu chí | Ý nghĩa | Thang điểm |
|---|---|:---:|
| **1. Correctness** | Thông tin có chính xác không? Có sai sự thật không? | 1–5 |
| **2. Faithfulness (Groundedness)** | Câu trả lời/context có hoàn toàn dựa trên retrieved text không? Có bịa đặt không? | 1–5 |
| **3. Relevance** | Có trả lời đúng trọng tâm câu hỏi của người dùng không? | 1–5 |
| **4. Completeness** | Có bao phủ đầy đủ các yêu cầu trong câu hỏi không? | 1–5 |
| **5. Practical Usefulness** | Có đưa ra lời khuyên/thông tin hữu ích để người dùng áp dụng khi đi du lịch không? | 1–5 |
| **6. Clarity** | Trình bày rõ ràng, mạch lạc, dễ đọc, cấu trúc tốt không? | 1–5 |

## 3. Chi Tiết Theo Danh Mục Du Lịch (Category Breakdown)

| Danh Mục (Category) | Số Câu | Parent-Child Thắng | Baseline Thắng |
|---|:---:|:---:|:---:|
| `accommodation` | 1 | **1** | 0 |
| `attraction` | 1 | **1** | 0 |

## 4. Nhận Xét & Phân Tích Kỹ Thuật
- **Practical Usefulness & Completeness tăng mạnh**: Nhờ Summary Parent cung cấp bức tranh toàn cảnh cho chuyến đi.
- **Faithfulness & Relevance cần theo dõi**: Tránh mang nhiễu khi retrieval nhầm chunk.