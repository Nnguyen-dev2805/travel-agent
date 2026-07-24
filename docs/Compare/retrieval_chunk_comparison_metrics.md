# Tổng Hợp Đánh Giá Retrieval Cho Standard Chunk Và Semantic Parent-Child Chunk

## Phạm Vi Đánh Giá

- Testset: `data/evaluation/document_user_query_testset_en.json`
- Số query đánh giá: **1405**
- Ground truth chính: `expected_document_id`
- Cách chấm: một retrieved chunk được xem là đúng nếu `chunk.document_id == expected_document_id`.
- K được dùng: `1, 3, 5, 10, 20`
- Các retriever được so sánh: `bm25, dense, hybrid`

## Ý Nghĩa Chỉ Số

- `hit@k` / `recall@k`: trong top-k có ít nhất một chunk thuộc đúng document hay không. Vì mỗi query có một expected document nên hai chỉ số này tương đương.
- `mrr@k`: document đúng xuất hiện càng sớm thì điểm càng cao.
- `ndcg@k`: đánh giá chất lượng ranking, có thưởng cho việc nhiều chunk đúng nằm ở vị trí cao.
- `precision@k`: tỷ lệ chunk trong top-k thuộc đúng document.
- `relevant_chunks@k`: số chunk đúng document trong top-k.
- `unique_docs@k`: số document khác nhau xuất hiện trong top-k.
- `source_url_hit@k`: top-k có URL đúng với `expected_source_url` hay không.
- `miss_count@k`: số query không retrieve được document đúng trong top-k.

## Kết Luận Nhanh

- Run tốt nhất theo `hit@20`: **semantic_parent_child / hybrid** với `0.6918`.
- Run tốt nhất theo `mrr@20`: **semantic_parent_child / dense** với `0.5449`.
- Run tốt nhất theo `ndcg@20`: **semantic_parent_child / dense** với `0.5625`.
- Nhìn tổng thể, semantic parent-child cải thiện rõ nhất với dense retrieval, nhưng BM25 trên semantic child yếu hơn BM25 trên standard chunk.
- Hybrid retriever trên semantic parent-child có `hit@20` cao nhất toàn bộ, nhưng `mrr@20` thấp hơn standard hybrid, nghĩa là thường tìm được document đúng trong top-20 nhưng document đúng không luôn nằm thật sớm.

## Bảng Tổng Hợp Theo Run


| retriever | chunk_strategy        | hit@1  | hit@5  | hit@10 | hit@20 | mrr@20 | ndcg@20 | precision@20 | miss@20 | first_rank_avg |
| --------- | --------------------- | ------ | ------ | ------ | ------ | ------ | ------- | ------------ | ------- | -------------- |
| bm25      | semantic_parent_child | 0.2512 | 0.4128 | 0.4747 | 0.5246 | 0.3261 | 0.35    | 0.0628       | 668     | 3.7151         |
| bm25      | standard              | 0.3893 | 0.5153 | 0.5594 | 0.6078 | 0.447  | 0.4503  | 0.0546       | 551     | 2.9707         |
| dense     | semantic_parent_child | 0.5103 | 0.5851 | 0.6206 | 0.6626 | 0.5449 | 0.5625  | 0.1706       | 474     | 2.4586         |
| dense     | standard              | 0.4612 | 0.5573 | 0.6014 | 0.6434 | 0.505  | 0.5229  | 0.0825       | 501     | 2.708          |
| hybrid    | semantic_parent_child | 0.4078 | 0.5665 | 0.637  | 0.6918 | 0.4765 | 0.4946  | 0.1409       | 433     | 3.3148         |
| hybrid    | standard              | 0.4498 | 0.5623 | 0.6249 | 0.6847 | 0.5032 | 0.51    | 0.0802       | 443     | 3.183          |





|     |
| --- |


## Run Tốt Nhất Theo Từng Metric


| metric       | best_run                       | value  |
| ------------ | ------------------------------ | ------ |
| hit@1        | semantic_parent_child / dense  | 0.5103 |
| hit@5        | semantic_parent_child / dense  | 0.5851 |
| hit@10       | semantic_parent_child / hybrid | 0.637  |
| hit@20       | semantic_parent_child / hybrid | 0.6918 |
| mrr@20       | semantic_parent_child / dense  | 0.5449 |
| ndcg@20      | semantic_parent_child / dense  | 0.5625 |
| precision@20 | semantic_parent_child / dense  | 0.1706 |


## Best Run Theo URL Group


| url_group            | query_count | best_run                      | best_hit@20 | best_mrr@20 | best_ndcg@20 |
| -------------------- | ----------- | ----------------------------- | ----------- | ----------- | ------------ |
| places-to-go         | 110         | semantic_parent_child / dense | 0.6909      | 0.3571      | 0.424        |
| plan-your-trip       | 65          | standard / hybrid             | 0.8615      | 0.587       | 0.6311       |
| things-to-do         | 1060        | standard / bm25               | 0.6906      | 0.5478      | 0.538        |
| vietnamese_news_2025 | 170         | semantic_parent_child / dense | 0.8         | 0.6631      | 0.6983       |


## File Chi Tiết

- `summary_by_run.csv`: toàn bộ metric trung bình theo chunk strategy và retriever.
- `strategy_comparison_by_query.csv`: so sánh standard vs semantic parent-child trên từng query.
- `summary_by_query_type.csv`: metric theo query type.
- `summary_by_category.csv`: metric theo category.
- `summary_by_url_group.csv`: metric theo nhóm URL.
- `top_failures_at_20.csv`: các query miss ở top-20, nếu file này được sinh trong lần chạy evaluator.

## Nhận Xét Kỹ Thuật

### 1 Đánh giá ảnh hưởng của chiến lược chunking và phương pháp truy xuất

#### 1.1. So sánh tổng quan 

Kết quả cho thấy hiệu quả của chiến lược chunking phụ thuộc đáng kể vào phương pháp truy xuất được sử dụng.

Trong ba phương pháp truy xuất, **Dense Retrieval kết hợp với Semantic Parent–Child Chunking đạt hiệu năng tốt nhất trên hầu hết các chỉ số quan trọng**, bao gồm Hit@1, MRR@20, NDCG@20 và Precision@20. Trong khi đó, **Hybrid Retrieval kết hợp với Semantic Parent–Child Chunking đạt Hit@20 cao nhất và có số lượng truy vấn không tìm thấy tài liệu liên quan thấp nhất (Miss Count thấp nhất)**.

Ngược lại, **BM25 suy giảm đáng kể khi kết hợp với Semantic Parent–Child Chunking**, đặc biệt ở các chỉ số phản ánh chất lượng xếp hạng như Hit@1, MRR@20 và NDCG@20.

Điều này cho thấy Semantic Parent–Child Chunking phát huy hiệu quả rõ rệt khi sử dụng các phương pháp truy xuất dựa trên biểu diễn ngữ nghĩa (Dense Retrieval), nhưng chưa thực sự phù hợp với phương pháp truy xuất dựa trên từ khóa như BM25.



#### 1.2. Phân tích standard Chunking 

- Đây là baseline khá hiệu quả
- Các chỉ số đạt được:
  - Hit@1 = **46.12%**
  - Hit@20 = **64.34%**
  - MRR@20 = **0.505**
  - NDCG@20 = **0.523**
- Tuy nhiên, Precision@20 chỉ đạt **0.082**, cho thấy mặc dù hệ thống thường tìm được tài liệu đúng, nhưng trong top 20 vẫn tồn tại khá nhiều tài liệu không liên quan. Điều này làm tăng lượng nhiễu đưa vào LLM trong giai đoạn sinh câu trả lời.



#### 1.3. Phân tích Semantic Parent - Children Chunking 




| Metric       | Standard | Parent–Child |
| ------------ | -------- | ------------ |
| Hit@1        | 46.12%   | **51.03%**   |
| MRR          | 0.505    | **0.545**    |
| NDCG         | 0.523    | **0.562**    |
| Precision@20 | 0.082    | **0.171**    |


- Kết quả đáng chú ý: Precision@20 tăng mạnh gần nhưu là gấp đôi. Điều này cho thấy trong top 20 dữ liệu lấy về có nhiều dữ liệu liên qyan hơn. 

Nguyên nhân là Child Chunk có tính chuyên biệt cao hơn Standard Chunk. Embedding của Child ít bị ảnh hưởng bởi các chủ đề khác trong cùng tài liệu nên khoảng cách vector giữa Query và Child chính xác hơn

#### 1.4. Tổng quan 

Khi sử dụng Dense Retrieval, Semantic Parent–Child vượt trội hơn Standard Chunking trên tất cả các chỉ số.

Điều này chứng minh rằng việc chia tài liệu theo cấu trúc ngữ nghĩa giúp embedding biểu diễn nội dung chính xác hơn, từ đó nâng cao chất lượng truy xuất.

Ngược lại, khi sử dụng BM25, Parent–Child lại làm giảm hiệu năng.

Nguyên nhân là Child Chunk quá ngắn và thiếu các từ khóa quan trọng mà BM25 cần để tính toán mức độ liên quan.

Đối với Hybrid Retrieval, Parent–Child giúp tăng khả năng bao phủ tài liệu (Hit@20 cao hơn và Miss Count thấp hơn), nhưng đồng thời làm giảm chất lượng xếp hạng ở các vị trí đầu do ảnh hưởng từ thành phần BM25.



