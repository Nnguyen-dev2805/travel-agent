# **Static knowledge** 
## Benchmark Retrieval

### BEIR
Benchmarking Information Retrieval 
#### What 
Đây là bộ benchmark dùng để  đánh giá hệ thống tìm kiếm thông tin - tức là khả năng có lấy đúng document hoặc passage liên quan từ corpus lớn 
Hỗ trợ so sánh nhiều loại retriever. Nó là zero-shot retrieval evaluation 
#### Purpose 
BEIR được xây dựng để kiểm tra Retriever có tổng quát tốt dữ liệu ngoài huấn luyện hay không
#### When 
- Dược dùng khi so so sánh các retriever: BM25, Dense , Hybrid Search
#### Không dùng BEIR khi
- Đánh giá câu trả lời cuối cùng 
- Đánh giá toàn bộ RAG
- Đánh giá chunking

### Custom Travel Retrieval Benchmark

- Custom là bộ benchmark retrieval tự xây dựng, dựa trên: 
	- Corpus du lịch 
	- Query thực tế của người dùng 
	- Ground truth tự được đánh nhãn
- Mục tiêu: Đánh giá retriever có lấy đúng thông tin từ corpos du lịch hay không 
- Với BEIR đánh giá khả năng tổng quát, còn với custom benchmark đánh giá khả năng trên đúng bài toán Travel Agent 
- 

## Benchmark Embedding model 

### MTEB Retrieval 

#### What 
MTEB Retrieval (Massive Text Embedding Benchmark) dùng để đánh giá chất lượng embedding model trong bài toán retrieval
#### Purpose 
- So sánh embedding model 
- Chọn embedding phù hợp , đánh giá khả năng semantic retrieval
- Gồm nhiều domain 
- Không đánh giá Retrieval System  , Chunking , RAG


## Benchmark reranking

### MTEB reranking 
### Custom Travel Reranking Benchmark


# **Custom Benchmark**
# 1. Xây dựng benmamrks component
- Hệ thống test không nên chỉ đánh giá dựa trên câu trả lời cuối cùng . Một câu trả lời sai có thể xuất phát từ: 
	- Corpus không có thông tin 
	- Retriever không tìm được đúng chunk 
	- Retriever tìm được nhưng xếp hạng quá thấp 
	- Reranking xếp sai thứ tự 
	- Context đúng nhưng LLM không sử dụng 
	- Context sai nhưng output vẫn đúng 
	- Câu trả lời có dựa vào context hay không 
	- Câu trả lời đúng nhưng không làm theo yêu cầu người dùng 
- Hệ thống test cần cover hết prompt builder, transform query, chunking , embedding, database, retrieval, reranking
- Testing riêng (retrieval, reranking) và testing toàn bộ hệ thống (output)
### 1.1. Benchmark Retrieval 

- **what** : Retrieval Benchmark đánh giá khả năng của retriever trong việc lấy ra những chunk chứa thông tin cần thiết cho một câu hỏi
- **why**: Nếu chỉ đánh giá câu trả lời cuối cùng , không xác định được lỗi nằm ở retriever hay generator 
- Retrieval benchmark giúp trả lời các câu hỏi: 
	- Corpous có chứa đáp án không? 
	- Retrever có tìm được chunk không 
	- Chunk đúng xuất hiện ở vị trí nào 
	- Tăng top_k có cải thiện coverage không 
	- Dense, BM25, hay Hybrid Retrieval tốt hơn 
	- Parent children có chunking tốt hơn token chunking không
	- Embedding nào phù hợp với hệ thống nhất 
- **When**: 
	- Thay đổi embedding 
	- Thay đổi chunking stategy 
	- Thay đổi chunksize hay overlap 
	- Chuyển đổi vector database 
	- Thay đổi query processing 
	- Cập nhật corpous
	- Ở benchmark này không cần gọi LLM generator 

#### Xây dựng benchmark 

- mẫu json 
```json
{
  "query_id": "travel_001",
  "query": "Đến Huế nên ăn món gì?",
  "language": "vi",
  "intent": ["food"],
  "province": "Hue",
  "difficulty": "easy",
  "answerable": true,
  "relevant_document_ids": ["doc_hue_food"],
  "relevant_chunk_ids": ["chunk_hue_food_01", "chunk_hue_food_02"],
  "gold_facts": ["Bún bò Huế", "Cơm hến", "Bánh bèo", "Bánh nậm", "Bánh lọc"]
}
```

**Dataset cần bao  phủ:** 
- Attraction 
- Cuisine 
- Culture 
- Accommodation
- Transportation 
- Weather 
- Activities 
- Plan 
- Budget 
- compare
- Hotel/ Itinerary
**Robustness**
- Sử dụng promptBench để biến đổi sinh ra các biến thể của query
#### Mectric 
- hit@k : Kiểm tra trong top_k có ít nhất 1 chunk liên quan hay không 
- Reacall@k : Đo tỷ lệ relevant chunks được tìm thấy trong top_k 
- Precision@k: Đo độ chính xác,Phát hiện các context thừa 
- MRR: đo vị trí của relevant các chunk đúng 
- NDCG@k: phù hợp khi chunk có nhiều mức độ liên quan 

#### Benchmarks cần chạy 
- **So sánh embedding model**
	- BAAI/bge-m3
	- multilingual-e5-large
	- embedding model khác
- **So sánh chunking**
	- Token size
	- Semantic chunking 
	- Heading chunking
	- Parent children
	- Custom chunking 
- **So sánh top_k** 
#### Benchmark BEIR
- Đây là benchmark để kiểm tra Retrieval của mình có tốt không 
- **So sánh retriever**
	- BM25
	- Dense 
	- Hybrid .....
- **Multiligunal robustness** 
#### Sử dụng MTEB để đánh giá và chọn model embedding

#### Sử dụng LLM judge để đánh giá chất lượng chunk

```json
{
  "query_id": "travel_001",
  "query": "Đến Huế nên ăn món gì?",
  "language": "vi",
  "intent": ["food"],
  "province": "Hue",
  "difficulty": "easy",
  "answerable": true,
  "relevant_document_ids": ["doc_hue_food"],
  "relevant_chunk_ids": ["chunk_hue_food_01", "chunk_hue_food_02"],
  "gold_facts": ["Bún bò Huế", "Cơm hến", "Bánh bèo", "Bánh nậm", "Bánh lọc"], 
  "relevance_judgments": [
  {
    "chunk_id": "chunk_hue_food_01",
    "grade": 3,
    "reason": "Trả lời trực tiếp các món ăn ở Huế"
  },
  {
    "chunk_id": "chunk_hue_market_01",
    "grade": 2,
    "reason": "Có nhắc địa điểm ăn uống nhưng không liệt kê đầy đủ món"
  }
] 
}
```


### 1.2. Benchmarks Reranking 
#### What 
Reranking là bước sắp xếp lại các tài liệu hoặc chunk đã được Retrieval tìm thấy dựa trên mức độ liên quan của từng chunk đối với câu hỏi 
Cách chunk đúng sẽ được đưa lên vị trí cao hơn
#### Why 
Retriever thường được thiết kế để tối ưu tốc độ sau đó thường dùng cosine similarity để đánh giá sự liên quan. Tuy nhiên cách này không phải lúc nào cũng đầy đủ: 
- Quan hệ query và chunk 
- Các điều kiện trong query 
- Tên các địa danh không giống nhau 
- Phủ định 
- Thông tin thời gian 
- ...... 
#### How - Cách xây dựng Benchmark Reranking 

**Chuẩn bị query benchmarks**

```json
{ "query_id": "travel_001", 
"query": "Đến Huế nên ăn món gì?", 
"language": "vi", 
"intent": "[food]"
, "province": "[Hue[]", 
"difficulty": "easy",
 "answerable": true, 
 "relevant_document_ids": [ "doc_hue_food" ], 
 "relevant_chunk_ids": [ "chunk_hue_food_01", "chunk_hue_food_02" ] }
```

**Tạo Candidate dataset**
```json
[ 
{ "chunk_id": "hue_history_001", "retrieval_rank": 1, "retrieval_score": 0.84 }, { "chunk_id": "hue_food_001", "retrieval_rank": 2, "retrieval_score": 0.81 }, { "chunk_id": "hue_hotel_001", "retrieval_rank": 3, "retrieval_score": 0.79 }
 ]
```

**Reranker chấm điểm từng candidate**
Reranker nhận query + Candidate chunk --> reranking socre

**Chọn final top_n và so sánh trước và sau reranking**
#### Json dataset Reranking 
#### JSON kết quả sau Reranking
```json 
{ "run_id": "rerank_run_001",
 "query_id": "rerank_001",
  "configuration": { "retriever": "BAAI/bge-m3", "candidate_k": 20, "reranker": "bge-reranker-v2-m3", "final_top_n": 4 },
   "before_reranking": [ { "chunk_id": "hue_history_001", "rank": 1, "score": 0.842, "relevance_label": 1 }, { "chunk_id": "hue_food_001", "rank": 2, "score": 0.816, "relevance_label": 3 } ], 
   "after_reranking": [ { "chunk_id": "hue_food_001", "rank": 1, "score": 0.961, "relevance_label": 3 }, { "chunk_id": "hue_history_001", "rank": 2, "score": 0.312, "relevance_label": 1 } ], 
   "metrics": { "mrr_before": 0.5, "mrr_after": 1.0, "mrr_gain": 0.5, "ndcg_at_4_before": 0.72, "ndcg_at_4_after": 1.0, "ndcg_gain": 0.28, "precision_at_4_before": 0.25, "precision_at_4_after": 0.5, "recall_at_4_before": 1.0, "recall_at_4_after": 1.0, "rank_improvement": 1, "regressed": false }, "latency_ms": { "retrieval": 84, "reranking": 238, "total": 322 } }
```

#### Các Benchmark reranking  
- **MTEB Reranking**


#### Metrics cho Benchmark Reranking 
- Candidate Recall@k: Candidate Recall kiểm tra Retriever có đưa relevant chunk vào candidate set hay không.
- Hit@k
- Precision@k
- Recall@k
- MRR — Mean Reciprocal Rank
- MRR Gain
- nDCG@k, nDCG Gain
- MAP — Mean Average Precision
- Regression Rate
#### Benmark cần chạy
- so sánh Retriever-only và Retriever + Reranker
- Candidate size
- Final top-n
- So sánh Reranker model
	- Cross-Encoder 
	- BGE Reranker 
	- Multilingual Reranker
	- LLM reranker 
#### ưu điểm của Reranking 
- Đưa relevant chunk lên vị trí cao hơn
- Giảm context noise
- Tốt với query nhiều điều kiện
- Giảm số token gửi vào LLM
- Phân biệt Hard Negative tốt hơn Retriever
#### Nhược điểm của Reranking 
- Tăng chi phí tính toán
- Có thể làm giảm Recall
- Phụ thuộc ngôn ngữ và domain

## 2. Benchmarks output - đánh giá hệ thống
```
Travel Benchmark
(Query + Ground Truth)
          │
          ▼
   Travel Agent
          │
          ▼
Prediction
(Context + Answer)
          │
          ▼
Evaluation Pipeline
(RAGAS + Custom Metrics)
```
#### what 
- Benmark output đánh giá chất lượng câu hỏi cuối cùng được sinh ra bởi hệ thống Travel Agent sau toàn bộ quá trình 
- Câu trả lời có đúng  không , đầy đủ , liên quan , grouded và tuân thủ các yêu cầu của người dùng không 
- Output Benmark khồn chỉ đo answer đúng hay sai. Nó đánh giá dựa trên nhiều khía cạnh: 
	- Factual correctness 
	- Faithfulness 
	- Answer relevancy
	- Completeness 
	- Hallucination 
	- Instruction following 
	- Robustness 
	- Safety 
	- Abstention 
	- Planning 
#### Why 
- Retrieval và Reranking tốt không đảm bảo câu trả lời cuối cùng tốt
- Benchmarks giúp trả lời câu hỏi: 
	- Câu trả lời có đúng với gold answer không?
	- Các fact có được context hỗ trợ không?
	- Có fact nào bị bịa không?
	- Câu trả lời có bao phủ đủ thông tin cần thiết không?
	- Câu trả lời có trực tiếp trả lời query không?
	- Có làm đúng instruction của người dùng không?
	- Có ổn định trước paraphrase, typo và thay đổi ngôn ngữ không?

#### Đối tượng được đánh giá 
| LLM-only | Oracle Context | Retrieved Context | Kết luận                               |
| -------- | -------------- | ----------------- | -------------------------------------- |
| Sai      | Đúng           | Đúng              | RAG cải thiện kiến thức                |
| Sai      | Đúng           | Sai               | Retrieval hoặc Reranking lỗi           |
| Sai      | Sai            | Sai               | Generator không dùng context tốt       |
| Đúng     | Đúng           | Sai               | Retrieval đưa context gây nhiễu        |
| Đúng     | Sai            | Sai               | Prompt hoặc context handling có vấn đề |

#### How - Cách xây dựng Benchmark output

**Bước 1: Xây dựng tập câu hỏi**
Benchmark cần bao phủ các nhóm chức năng

| Nhóm              | Ví dụ                                        |
| ----------------- | -------------------------------------------- |
| Factual QA        | Huế nằm ở miền nào?                          |
| Attraction        | Đà Nẵng có điểm tham quan nào nổi tiếng      |
| Cuisine           | Đến Huế nên thử món gì                       |
| Transportation    | Đi từ Hà Nội vào Huế bằng cách nào           |
| Accommodation     | Nên ở khu vực nào tại Đà Nẵng                |
| Culture           | Hội An có những đặc trưng văn hóa gì         |
| Weather/season    | Khi nào nên đi Phú Yên                       |
| Comparison        | Nên chọn Huế hay Hội An cho chuyến đi 2 ngày |
| Planning          | Lập lịch trình 2 ngày tại Đà nẵng            |
| Dynamic knowledge | Giá vé vào cổng là bao nhiêu                 |
| Robustness        | Da nag co cai j choi z                       |
| Safety            | Có thể đi vào khu vực cấm nào để chụp ảnh    |

#### Benchmark dataset output
```json 
{
  "benchmark_version": "1.0.0",
  "query_id": "output_001",
  "user_input": "Huế nổi tiếng với những món ăn nào?",
  "reference": {
    "reference_answer": "Huế nổi tiếng với bún bò Huế, cơm hến, bánh bèo, bánh nậm và bánh lọc.",
    "gold_facts": [
      {
        "fact_id": "fact_001",
        "fact": "Bún bò Huế là món ăn nổi tiếng của Huế.",
        "required": true,
        "importance": 1.0,
        "supporting_document_ids": [
          "doc_hue_food"
        ]
      },
      {
        "fact_id": "fact_002",
        "fact": "Cơm hến là món ăn nổi tiếng của Huế.",
        "required": true,
        "importance": 1.0,
        "supporting_document_ids": [
          "doc_hue_food"
        ]
      },
    ],
    "reference_contexts": [
      {
        "document_id": "doc_hue_food",
        "chunk_id": "hue_food_001",
        "text": "Ẩm thực Huế nổi tiếng với nhiều món ăn như bún bò Huế, cơm hến, bánh bèo, bánh nậm và bánh lọc."
      }
    ],
    "reference_context_ids": [
      "hue_food_001"
    ],
    "expected_behavior": "answer"
  },
  "constraints": {
    "language": "vi",
    "must_be_grounded": true,
    "citation_required": true
  },
  "metadata": {
    "intent": [
      "cuisine"
    ],
    "province": "Hue",
    "difficulty": "easy",
    "answerable": true,
    "knowledge_type": "static",
    "requires_planning": false,
    "requires_temporal_data": false
  }
}
```

Ouput predict
```json 
{
  "run_id": "output_run_001",
  "query_id": "output_001",
  "configuration": {
    "retriever": "BAAI/bge-m3",
    "retrieval_strategy": "dense",
    "reranker": "bge-reranker-v2-m3",
    "generator": "gpt-4o-mini",
    "prompt_version": "travel_prompt_v3",
    "temperature": 0,
    "top_k": 20,
    "top_n": 4
  },
  "retrieval_output": {
    "retrieved_context_ids": [
      "hue_history_001",
      "hue_food_001",
      "hue_hotel_001"
    ],
    "retrieved_contexts": [
      "Huế từng là kinh đô của triều Nguyễn.",
      "Ẩm thực Huế nổi tiếng với bún bò Huế, cơm hến, bánh bèo, bánh nậm và bánh lọc.",
      "Du khách có thể lưu trú tại khu vực trung tâm thành phố Huế."
    ]
  },
  "reranking_output": {
    "reranked_context_ids": [
      "hue_food_001",
      "hue_history_001",
      "hue_hotel_001"
    ]
  },
  "generation_output": {
    "response": "Huế nổi tiếng với bún bò Huế, cơm hến, bánh bèo, bánh nậm và bánh lọc.",
    "citations": [
      {
        "document_id": "doc_hue_food",
        "chunk_id": "hue_food_001"
      }
    ]
  }
}
```

- Xây dựng benchmark cho từng query , để thực hiện dynamic dataset, lấy những query có câu trả lời không tốt lưu lại sau đó phân tích kết quả 

#### Metric đánh giá 
**Factual Correctness**
- Factual Correctness kiểm tra các thông tin trong answer có đúng với gold facts hoặc trusted source hay không 
- Chia nhỏ thành các fact để kiểm tra 
- Tính toán 
	- Atomic Fact Precision 
	- Factual Recall 
**Faithfulness**
- what : Mỗi claim trong answer có được retrieval context hỗ trợ không?
- How :
	- Sử dụng LLM Extraction để tách Claim
	- Có thể NLI để tách claim và so sánh 
- Ưu điểm: 
	- Phát hiện generator tự thêm thông tin
	- Kiểm tra chất lượng RAG
	- Có thể sử dụng NLI hoạc LLM Judge 
- Nhược điểm: 
	- Phụ thuộc chất lượng claim  extraction 
	- LLM judge có thể không ổn định 
```json 
{
  "evaluation_id": "eval_output_run_001",
  "run_id": "output_run_001",
  "query_id": "output_001",
  "evaluator_configuration": {
    "framework": "RAGAS_plus_custom",
    "judge_model": "gpt-4o-mini",
    "evaluator_version": "1.0.0"
  },
  "claim_evaluation": [
    {
      "claim": "Bún bò Huế là món ăn nổi tiếng của Huế.",
      "supported": true,
      "factual_correct": true,
      "evidence_context_ids": [
        "hue_food_001"
      ]
    },
    {
      "claim": "Cơm hến là món ăn nổi tiếng của Huế.",
      "supported": true,
      "factual_correct": true,
      "evidence_context_ids": [
        "hue_food_001"
      ]
    }
  ],
  "metrics": {
    "ragas": {
      "faithfulness": 1.0,
      "answer_relevancy": 1.0,
      "context_precision": 0.67,
      "context_recall": 1.0,
      "factual_correctness": 1.0
    },
    "custom": {
      "completeness": 1.0,
      "citation_correctness": 1.0,
      "citation_completeness": 1.0,
      "instruction_following": 1.0,
      "fluency": 0.95,
      "safety": 1.0,
      "hallucination_rate": 0.0
    }
  },
  "decision": {
    "passed": true,
    "failure_type": null,
    "notes": "Câu trả lời đúng, đủ, bám context và không có hallucination."
  }
}
```

**Hallucination Rate**
- Claim-level Hallucination Rate: phản ánh mức độ lỗi
- Answer-level Hallucination Rate: phản ánh tỷ lệ câu hỏi bị ảnh hưởng

#### Các khía cạnh Human feedback
```
Accuracy: thông tin có đúng không 
Relevance: Có thực sự trả lời câu hỏi không 
Fluency: Câu trả lời có tự nhiên và dễ đọc không 
Transparency: Hệ thống có thể hiện rõ căn cứ/ giới hạn phù hợ không
Safety: Có nội dung nào gây hại hoặc missinformation không
Human Alignment: CÓ phù hợp với expectation và value của con người không
```

# **Dynamic Knowledge**
- FreshQA
- LiveBench
- FRESHBench

|Metric|Ý nghĩa|
|---|---|
|Temporal Correctness|Trả lời đúng theo thời điểm được hỏi|
|Freshness Awareness|Có nhận biết dữ liệu có thể cũ không|
|Warning Rate|Có cảnh báo khi knowledge cũ|
|Appropriate Abstention|Có từ chối đúng khi không đủ dữ liệu|
|Live Search Trigger Rate|Có kích hoạt live search khi cần|
|Temporal Faithfulness|Có bịa thông tin mới ngoài corpus không|
## Độ biến động Knowledge 

- Static knowledge: Thông tin gần  như không thay đổi. Ví dụ: Huế thuộc miền Trung , Vịnh Hạ Long ở Quảng Ninh. 
- Slowly Changing Knowledge: Thông tin thay đổi nhưng thường xuyên. Ví dụ: khách sạn mới mở, địa điểm du lịch mới,......
- Frequently Changing Knowledge: Thông tin thay đổi hàng tuần hoặc hàng tháng. ví dụ: Giá vé trong tuần và cuối tuần, lịch lễ hội, tour, giá phòng , ......
- Real time Knowledge: Không nên đưa vào RAG. Ví dụ: thời tiết, chuyến bay, tình trạng khách sạn , giao thông , .......

**Em đang tìm hiểu**

# - Evaluation pipeline với local metrics và tùy chọn RAGAS.

Sử dụng RAGAS để xây dựng pipeline đánh giá 

## RAGAS
Retrieval-Agumented Generation Assessment là một framework đánh giá tự độnh chất lượng của hệ thống RAG. RAGAS không đánh giá LLM mà đánh giá toàn bộ pipeline RAG
RAGAS tách riêng từng phần trong pipline. Khi có lỗi dễ phát hiện nơi xuất phát lỗi 

```
Benchmark Query
        │
        ▼
Run RAG
        │
        ▼
Retrieved Context
Generated Answer
        │
        ▼
RAGAS Metric
        │
        ▼
LLM Judge
        │
        ▼
Score
```

Benchmark đưa vào RAGAS
```json
{
  "user_input": "...",
  "retrieved_contexts": ["..."],
  "response": "...",
  "reference": "...",
  "reference_contexts": ["..."]
}
```

```json 
{
  "query_id": "travel_001",

  "user_input": "Huế nổi tiếng với những món ăn nào?",

  "retrieved_contexts": [
    "Huế từng là kinh đô của triều Nguyễn.",
    "Ẩm thực Huế nổi tiếng với bún bò Huế, cơm hến, bánh bèo, bánh nậm và bánh lọc.",
    "Du khách có thể lưu trú tại khu vực trung tâm thành phố Huế."
  ],

  "retrieved_context_ids": [
    "hue_history_001",
    "hue_food_001",
    "hue_hotel_001"
  ],

  "response": "Huế nổi tiếng với bún bò Huế, cơm hến, bánh bèo, bánh nậm và bánh lọc.",

  "reference": "Huế nổi tiếng với bún bò Huế, cơm hến, bánh bèo, bánh nậm và bánh lọc.",

  "reference_contexts": [
    "Ẩm thực Huế nổi tiếng với nhiều món ăn như bún bò Huế, cơm hến, bánh bèo, bánh nậm và bánh lọc."
  ],

  "reference_context_ids": [
    "hue_food_001"
  ]
}
```