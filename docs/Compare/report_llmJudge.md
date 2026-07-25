
# 1. Score sumary

|                      |               |             |                                  |                 |               |
| -------------------- | ------------- | ----------- | -------------------------------- | --------------- | ------------- |
| metric               | standard_mean | hybrid_mean | mean_delta_hybrid_minus_standard | standard_median | hybrid_median |
| overall_score        | 3.262         | 3.4393      | 0.1773                           | 3.17            | 3.5           |
| correctness          | 3.13          | 3.8         | 0.67                             | 3.0             | 4.0           |
| faithfulness         | 2.02          | 1.52        | -0.5                             | 2.0             | 1.0           |
| relevance            | 3.92          | 3.19        | -0.73                            | 4.0             | 3.0           |
| completeness         | 2.97          | 3.8         | 0.83                             | 3.0             | 4.0           |
| practical_usefulness | 3.55          | 4.45        | 0.9                              | 3.5             | 5.0           |
| clarity              | 3.98          | 3.88        | -0.1                             | 4.0             | 4.0           |
|                      |               |             |                                  |                 |               |

# 2. Phương pháp đánh giá
- Sử dụng chat-gpt 5.5 đánh giá chất lượng câu hỏi dựa trên 6 tiêu chí

| Tiêu chí                           | Ý nghĩa                                                                                 | Thang điểm |
| ---------------------------------- | --------------------------------------------------------------------------------------- | ---------- |
| **1. Correctness**                 | Thông tin có chính xác không? Có sai sự thật không?                                     | 1–5        |
| **2. Faithfulness (Groundedness)** | Câu trả lời có hoàn toàn dựa trên context được retrieve không? Có hallucination không?  | 1–5        |
| **3. Relevance**                   | Có trả lời đúng trọng tâm câu hỏi của người dùng không?                                 | 1–5        |
| **4. Completeness**                | Có bao phủ đầy đủ các yêu cầu trong câu hỏi không?                                      | 1–5        |
| **5. Practical Usefulness**        | Có đưa ra lời khuyên hoặc thông tin hữu ích để người dùng áp dụng khi đi du lịch không? | 1–5        |
| **6. Clarity**                     | Trình bày rõ ràng, mạch lạc, dễ đọc, có cấu trúc tốt không?                             | 1–5        |
# 3. Nhận xét
- Mặc dù mức tăng chỉ 0.18 nhưng Hybrid thắng 58/100 query , trong khi token_chunk chỉ thằng 24/100 query
- Ở token chunking , mỗi chunk là 1 đơn vị độc lập. Khi retrieval lấy được 1 chunk thì LLM chỉ nhìn  thấy lượng thông tin hạn chế và rời rạc
- Ngươc lại với Parent-Children thì sau khi truy suất  children nó được rộng thêm context của sumary parent . Từ đó LLM nhận được nhiều ngữ cảnh truy vấn hơn. Và chunk children có được sự liên kết với chủ đề bài báo của nó 

## 3.1. Correctness : tăng 0.67
- Đo độ chính xác của câu trả lời
- Một câu trả lời có thể đúng theo kiến thức thực tế nhưng không xuất hiện trong context. Khi đó conrectness tăng nhưng failthless lại thấp 
- Tại sao parent-children lại tăng: 
	- Vì với tokenRAG không chứa đầy đủ context. Ví d: query : 'Lập lịch 2 ngày 1 đêm tại Đà Nẵng'. token RAG chỉ trả về các chunk rời rạc
	- Đối với chunk chidren + sumary parent . Nó được cung cấp thêm thông tin ngữ cảnh của toàn bài báo. Từ đó có cái nhìn tổng quan hơn
## 3.2. Faithfulness: giảm 0.5 
Chỉ số Faithfulness cũng rất thấp . Cho thấy model cũng phụ vào nội dung nội tại rất nhiều thay vì RAG. 
Tại sao parent - Children lại giảm: 
- Nếu chunk đúng thông tin việc bổ sung context sumary là ưu điểm . Tuy nhiên với baseline hiện tại khi truy vấn sai chunk + sumary parent làm cho có rất nhiều dữ liệu được đưa vào LLM và nó không hê có ích thậm chí còn làm giảm hiệu suất. --> Nên có 1 thành phần quản lý chất lượng truy vấn RAG trước khi đưa vào LLM generation. 
- Và sumary thường có thông tin tổng quan và nó có thể không chi tiết nếu query người dùng hỏi chi tiết cụ thể về 1 vấn đề . Ví dụ query "Mì quảng". Trong khi sumary là toàn bộ lĩnh vực đồ ăn Đà nẵng
- Parent quá rộng có thể làm mất bằng chứng

## 3.3. Relevance : giảm 0.73
## 3.4. Completeness : tăng 0.83
- Parent khôi phục phần context bị chia cắt. token RAG có thể retrieval một chunk nói về thời tiết nhưng với Hybrid nó có thể mở rộng thêm về phương tiện di chuyển . 

