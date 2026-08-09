

# Pipeline data
![[Pasted image 20260802101750.png]]


# Pipeline RAG
![[Pasted image 20260802155853.png]]
# 1. Dữ liệu cào về và cách clean  dữ liệu

- Với dữ liệu được về từ vietnam.travel, có 281 document được crawl về (tưng ứng với 281 bài báo). Phần lớn các bài viết đươc viết bằng tiếng anh. Các nội dung của bài báo khá đa dạng bao gồm :

|                             |             |                                                               |
| --------------------------- | ----------- | ------------------------------------------------------------- |
| Nhóm URL                    | Số document | Đặc điểm                                                      |
| `things-to-do`              | 212         | Bài gợi ý trải nghiệm, ẩm thực, văn hóa, hoạt động, nightlife |
| `places-to-go`              | 22          | Trang điểm đến, tỉnh/thành, khu vực                           |
| `plan-your-trip`            | 13          | Lịch trình, hướng dẫn lên kế hoạch, itinerary                 |
| URL tin tức tiếng Việt 2025 | 34          | Tin tức, sự kiện, kích cầu, xúc tiến du lịch địa phương       |
- Trong đó phần lớn dữ liệu trong thing-to-do và space-to-go là dữ liệu dạng cây. Phần lần text sẽ giải thích và bổ nghĩa cho Heading phía trên

![[Pasted image 20260730135410.png]]

- Đồng thời phần lớn các bài báo ở phía trên đầu bài viết đều có sumary text về bài báo (dữ liệu này là context cho parent và các ý nhỏ trong bài báo sẽ bám vào chủ đề nhỏ hơn trong bài báo sẽ được dùng cho chunk children ), 
- Hình ảnh hay video đang bỏ qua (chưa tìm cách xử lý)

- Vì phần lớn dữ liệu theo dạng cây  và các Heading có ý nghĩa nên cấu trúc này được giữ nguyên phục vụ cho RAG.


# 2. Xây dựng chunking
- Ý tưởng mỗi bài báo sẽ có 1 parent và bao gồm nhiều chunk children. Tuy nhiên chunk parent chỉ lưu sumary của bài báo đó, không lưu toàn bộ nội dung. Mỗi children là các đoạn nội dung nhỏ trong bài viết đó
## 2.1. Xây dựng parent
- Sumary papper để phục vụ cung cấp thêm context cho children chunk như: 
	- Cùng là chunk bún bò nhưng ở mỗi bài báo sẽ nói về 1 địa danh và sumary parent sẽ cung cấp context đó
**Chunk parent**
```json 
{
  "parent_id": "doc_001:parent:document",
  "document_id": "doc_001",
  "record_type": "parent",

  "title": "Best food in Hue | Vietnam Tourism",
  "clean_title": "Best food in Hue",
  "url": "https://vietnam.travel/...",
  "language": "en",
  "source_domain": "vietnam.travel",

  "context_summary": "This article introduces Hue as a food destination, covering local dishes such as bun bo Hue, royal cuisine, street food, and markets.",

  "metadata": {
    "primary_location": "Hue",
    "locations": ["Hue", "Central Vietnam"],
    "region": "Central Vietnam",
    "categories": ["food", "culture"],
    "article_type": "travel_guide",
    "total_children": 12,
    "chunker_version": "parent_child_v1"
  },

  "child_ids": [
    "doc_001:child:0000:00",
    "doc_001:child:0001:00"
  ]
}
```

## 2.2. Xây dựng children 
- Với các bài báo có cấu trúc: 
	- Xác định các cấp heading của bài toán . Đưa heading vào path và gắn tag heading 
	- Split các đoạn paragraph trong heading đó 
	- Split paragraph thành các sentence  hoặc thành các unit nhỏ
	- Gộp dữ liệu lại theo chunk size
- Đối với bài báo dạng viết không có cấu trúc heading
	- Heading thường rỗng
	- Split và gom theo chunk size 


Chunk Children 
```json 
{
  "child_id": "doc_001:child:0001:00",
  "parent_id": "doc_001:parent:document",
  "document_id": "doc_001",
  "record_type": "child",

  "heading": "Bun bo Hue",
  "heading_level": 2,
  "heading_path": [
    "Best food in Hue",
    "Bun bo Hue"
  ],

  "source_text": "Bun bo Hue is one of the most famous dishes from Hue...",
  "retrieval_text": "Article: Best food in Hue\nSection: Bun bo Hue\nHeading path: Best food in Hue > Bun bo Hue\nLocation: Hue\nCategory: food\nLanguage: en\n\nBun bo Hue is one of the most famous dishes from Hue...",

  "metadata": {
    "title": "Best food in Hue",
    "url": "https://vietnam.travel/...",
    "language": "en",
    "source_domain": "vietnam.travel",

    "primary_location": "Hue",
    "region": "Central Vietnam",
    "category": ["food"],
    "topic": "bun bo hue",
    "entity_type"=["dish"], 
    "content_type":"travel_guide", 

    "section_index": 1,
    "chunk_index": 0,
    "word_count": 180,
    "char_length": 920,
    "chunker_version": "parent_child_v1"
  }
}
```

## Lưu vào Chorma 

Schema Chorma
```json 
{
  "id": "doc_001:child:0001:00",

  "document": "Article: Best food in Hue\nSection: Bun bo Hue\nHeading path: Best food in Hue > Bun bo Hue\nLocation: Hue\nCategory: food\nLanguage: en\n\nBun bo Hue is one of the most famous dishes from Hue...",

  "embedding": [0.012, -0.034, 0.088],

  "metadata": {
    "record_type": "child",
    "child_id": "doc_001:child:0001:00",
    "parent_id": "doc_001:parent:document",
    "document_id": "doc_001",

    "title": "Best food in Hue",
    "url": "https://vietnam.travel/...",
    "language": "en",
    "source_domain": "vietnam.travel",

    "heading": "Bun bo Hue",
    "heading_level": 2,
    "heading_path": "Best food in Hue > Bun bo Hue",

    "primary_location": "Hue",
    "region": "Central Vietnam",
    "category": "food",
    "topic": "bun bo hue",
    "entity_type"=["dish"], 
    "content_type":"travel_guide", 
    
    "section_index": 1,
    "chunk_index": 0,
    "word_count": 180,
    "char_length": 920
  }
}
```


## Xử lý duplicate chunk 
- **what** : Duplicate chunk là hiện tượng nhiều document hoặc chunk chứa  nội dung giống hệt hoặc gần như giống nhau. 
	- Có thể xuất hiệ ở nhiều mức: 
		- Trùng URL
		- Trùng toàn bộ bài viết 
		- Trùng một phần nội dung
		- Trùng chunk sau khi chia nhỏ dữ liệu 
		- Trùng parent context sau khi retrieval 
- **when**
	- Khi cào dữ liệu
		- Cùng bài nhưng khác URL tracking 
		- bài category và bài chi tiết chứa lại cùng nội dung 
		- menu , footer,đoạn giới thiệu được lặp ở nhiều trang
		- Crawler chạy lại nhiều lần
	- Sau khi chunking và retrieval: 
		- Do overlap hoặc do lỗi HTML tạo ra 
		- Có content gần như giống nhau
		- Khi retrieval có thể lấy nhiều children trong cùng 1 bài viết dẫn đến context parent bị duplicate, nên kiểm tra trước khi cung cấp context parent
- **why**: Duplicate ảnh hưởng trực tiếp đến chất lượng và chi phí của hệ thống RAG
	- Lãng phí bộ nhớ và không gian vector 
	- Giảm độ đa dạng của kết quả retrieval 
	- Làm context của LLM bị lặp 
	- Có thể làm sai lệch tầm quan trọng của thông tin 
- **how**
	- Kiểm tra URL và heading path
	- Loại bỏ các nội dung trùng lặp trước khi chunking
	- Embedding và so sánh cosine similarity. Nếu > 0.9 thì loại bỏ (nhưng kiểm tra theo địa điểm , intant hoặc bài báo). Không so sánh tất tả toàn bộ dataset
	- kiểm soát overlap 
	- Kiểm tra dupliacte context parent trước khi cung cấp thông tin
- **ưu điểm**
	- Giảm kích thước dataset 
	- Giảm chi phí embedding
	- Tăng độ đa dạng của top-k retrieval
	- Giảm thiểu token context 
	- Hạn chế Lost in the Middle
- **nhược điểm**
	- Có nguy cơ  xóa nhầm dữ liệu 
	- Semantic dedup khá tốn tài nguyên 
	- khó chọn ngưỡng similarity 
	- Có thể làm mất đa dạng nguồn 

# 3. Embedding 

## Các loại embedding phổ biến
- BAAI/bge-m3
- multilingual-e5-large
- multilingual-e5-base
- gte-multilingual-base
- jina-embeddings-v3
- paraphrase-multilingual-MiniLM
- OpenAI embedding API
### BAAI/bge-m3 
M3: 
- Multi-Linguality: đa ngôn ngữ
- Multi-functionality: đa chức năng retrieval 
- Multi-Granularity: xử lý văn bản từ câu ngắn đến câu dài
Model hỗ trợ hơn 100 ngôn ngữ, đầu vào tối đa 8192 token và dense vector có 1024 chiều 

**Why**
- Dense retrieval mạnh về semantic nhưng đôi khi yếu về các keyword, từ viết tắt , .....
- Sparse retrieval mạnh khi query và document có matching nhưng yếu với các từ cùng ngữ nghĩa nhưng lại không cùng từ
- Một vector duy nhất có thể làm mất thông tin duy nhất
- Hệ thống đa ngôn ngữ phù hợp với bài toán

**How**
- BGE-M3 dựa trên một multilingual Transformer encoder mở rộng context lên 8192 token. Quá trình gồm long-context pretraining , contrastive learning và fine tuning cho 3 chế độ retrieval : Dense retrieval , Sparse retrieval , multivector retrieval
**Ưu điểm**
- Một model có 3 loại retrieval. Có thể dùng base, hybrid mà không cần thiết thay thế backbone
- Phù hợp với hệ thống đa ngôn ngữ
- Có context length lớn 
**Nhược điểm**
- Model tương đối nặng
- Encode có thể làm CPU chậm ,  tốn RAM
- Vector 1024 chiều làm tăng storage
- Context dài làm tăng latency tăng 

### Multilingual-e5-large

**what**
- Multilingual-E5-Large là 1 một bi-encoder embedding model. Model tạo ra 1 representation duy nhất cho toàn đoạn văn. Nó thuộc nhóm single-vector embedding model 
- Phiên bản hỗ trợ đa ngôn ngữ
**Purpose**
- Mục đích chính là tìm document dựa trên ý nghĩa, thay vì chỉ dựa vào các từ khóa trùng nhau
- Hỗ trợ đa ngôn ngữ nhưng tốn ít tài nguyên hơn M3
- Có thể được dùng làm input cho Cluster, recomendation , .... 
**Why**
- Keyword không hiểu toàn bộ ngữ cảnh. Keyword chỉ mạnh khi query và document có các từ giống nhau
- Hỗ trợ đa ngôn ngữ 
- Hướng tới representation tổng quát cho nhiều loại nhiệm vụ: Retrieval , similarity, Classification , Clustering 
- Giúp retrieval có thể scale 
**Ưu điểm**
- Có hỗ trợ đa ngôn ngữ
- Dense retrieval đơn giản và nhẹ hơn M3
**Nhược điểm**
- Context chỉ 512 token 
- Dense only 
- Single-vector
- Model vẫn khá lớn và nặng 
### gte-multilingual-base 

**what**
- gte-multilingual base có nhiệm vụ biến văn bản thành vector đo mức độ liên quan và tương đồng. Model encode 2 hai đầu vào, sau đó tính toán độ tương đồng. 
- Model có tạo hybrid retrieval Dense + Sparse
**why**
- Được thiết kế xử lý long context với context 8192 token 
- Model sử dụng encoder-only architecture với 305M , nhẹ hơn rất nhiều với các model trên, tốc độ cao hơn
- Có thể hybrid retrieval
- Có hỗ trợ đa ngôn ngữ 
- Đơn giản hơn E5, không cần bắt buộc prefix 
**Ưu điểm**
- Có chất lượng và model nhẹ hơn rất nhiều
- Context 8192 token 
- Vector chỉ 768 chiều 
- Hỗ trợ hybrid retrieval 
**Nhược điểm**
- Long input vẫn có khả năng dẫn đến latency cao 
- Entity confustion vẫn tồn tại ở dense mode 
- Giảm dimension có thể làm mất thông tin 

## **Thử với 3 model embedding trên.**

## 3.1. Inference Service 
### what
Inference Service là lớp dịch vụ chịu trách nhiệm nhận resquest từ ứng dụng, đưa input vào mô hình đã được huấn luyện và trả ra kết quả dự đoán hoặc nội dung được sinh ra 
Inference Service không chỉ là một API. Trong production , nó còn phải quản lý: 
- load model vào CPU/GPU 
- tokenization
- request queue 
- batching 
- giới hạn tài nguyên
- authentication 
- timeout và retry
- ....... 
### Purpose 
Biến một mô hình AI thành dịch vụ ổn định, có thể được nhiều ứng dụng và ngừi dùng gọi đồng thời
Nhờ đó, frontend , backend hoặc các agent không cần biết
- model được lưu ở đâu 
- model chạy trên ao nhiêu GPU
- GPU nào xử lý request 
- request được batch như thế nào 
- ...... 
### why 
- Model quá nặng để load cho từng request 
- GPU cần được sử dụng hiệu quả 
- KV cache rất lớn và thay đổi rộng 
### How
**Request lifecycle**
- Client gửi request 
- API xác thực và validate 
- Tokenizer chuyển text thành token IDs 
- Admission control kiểm tra tài nguyên 
- Scheduler đưa request vào queue 
- Batcher ghép các request 
- Prefill xử lý prompt 
- KV cache được tạo 
- Decode sinh từng token 
- Request hoàn thành , giải phóng cache 
- Ghi metrics và logs 
### Ưu điểm 
- Chuẩn hóa truy cập model 
- Tăng hiệu suấ GPU
- Scale độc lập 
- Tách bisiness logic khỏi model serving 
### Nhược điểm 
- Chi phí cao 
- Cold start chậm 
- network overhead 

```
FastAPI RAG
   │
   ├──► TEI + BGE-M3
   │        └── tạo embedding
   │
   ├──► ChromaDB
   │        └── vector search
   │
   └──► vLLM + Qwen/Llama
            └── sinh câu trả lời
```
## 3.2. TEI
### What
TEI (Text Embeddings Inference), là một inference server mã nguồn mở của Hugging Face, chuyên dùng để triển khai và phục vụ các mô hình: 
- Text embedding 
- reranker 
- sequence classification 
TEI biến embedding model thành một dịch vụ HTTP có thể được nhiều người gọi đồng thời, thay vì mỗi ứng dụng phải tự load model. 
### Purpose 
Biến embedding model thành dịch vụ inference có hiệu suất cao ổn định và có khả năng phục vụ nhiều request
### Why 
- Tránh load model nhiều lần (lãng phí bộ nhớ, startup chậm, dễ hết VRAM, .......)
- Tận dụng tốt batching 
- Tach RAG logic khỏi model serving 
- Chuẩn hóa API 
### Trade off 
Batch lớn
- Throughput tăng 
- GPU utilization tăng 
- Tuy nhiên : 
	- Queue latency tăng 
	- VRAM usage có thể tăng 
Batch nhỏ: 
- Latency thấp hơn 
- Request được xử lý sớm hơn 
- Tuy nhiên: 
	- GPU utilization thấp 
	- Through giảm 
	- Chi phí trên mỗi vector tăng 
Do đó, có hai kiểu workload: 
- Offiline indexing: batch lớn , throughput , tận dụng GPU
- Online query : Latency thấp, trả query vector nhanh , batch vừa và nhỏ 
### Ưu điểm
- Chuyên dụng cho Embedding 
- Dynamic batching theo token 
- Startup và deployment đơn giản 
- Hỗ trợ nhiều phần cứng 
### Nhược điểm
- Không miễn phí về hạ tầng 
- Custom pipeline khó hơn 
- Network overhead 


## 3.3. vLLM 

### what 
Là một inference service và model-serving framework mã nguồn mở, được thiết kế để chạy các lớn mô hình lớn: 
- throughput cao 
- quản lý GPU memory hiệu quả 
- batching nhiều request 
- streaming token  
- API , chạy model trên một hoặc nhiều GPU 

```
Qwen / Llama / Gemma / Mistral
= model

vLLM
= phần mềm chạy và phục vụ model
```
Không dùng vLLM : 
```
FastAPI
  │
  ├── load tokenizer
  ├── load model
  ├── model.generate()
  ├── tự quản lý request queue
  ├── tự batching
  ├── tự stream token
  └── tự xử lý GPU memory
```
Dùng vLLM : 
```
FastAPI RAG
    │ HTTP
    ▼
vLLM Server
    ├── tokenizer
    ├── scheduler
    ├── continuous batching
    ├── KV-cache manager
    ├── model executor
    ├── sampling
    └── streaming
```
### Purpose 
Biến một LLM mã nguồn mở trở thành một dịch vụ inference có khả năng phục vụ nhiều request đồng thời với hiệu suất GPU tốt 
Giúp giải quyết vấn đề khi request mới không cần phải đợi request cũ sinh xong 
 

cần **PagedAttention** để quản lý KV cache, bởi vì: 
- LLM sinh token tuần tự. Mỗi request có prompt length khác nhau, output length khác nhau, thời điểm bắt đầu khắc nhau, ....... 
- KV cache chiếm rất nhiều GPU memory 

# 4. Metadata Filtering 
### What 
Metadata là dữ liệu mô tả tài liệu hoặc chunk, nhưng không nhất thiết phải là nội dung chính để được dùng embedding 

**Chunk parent**
```json 
{
  "parent_id": "doc_001:parent:document",
  "document_id": "doc_001",
  "record_type": "parent",

  "title": "Best food in Hue | Vietnam Tourism",
  "clean_title": "Best food in Hue",
  "url": "https://vietnam.travel/...",
  "language": "en",
  "source_domain": "vietnam.travel",

  "context_summary": "This article introduces Hue as a food destination, covering local dishes such as bun bo Hue, royal cuisine, street food, and markets.",

  "metadata": {
    "primary_location": "Hue",
    "locations": ["Hue", "Central Vietnam"],
    "region": "Central Vietnam",
    "categories": ["food", "culture"],
    "entity_type"=["dish"], 
    "article_type": "travel_guide",
    "total_children": 12,
    "chunker_version": "parent_child_v1"
  },

  "child_ids": [
    "doc_001:child:0000:00",
    "doc_001:child:0001:00"
  ]
}
```

Chunk Children 
```json 
{
  "child_id": "doc_001:child:0001:00",
  "parent_id": "doc_001:parent:document",
  "document_id": "doc_001",
  "record_type": "child",

  "heading": "Bun bo Hue",
  "heading_level": 2,
  "heading_path": [
    "Best food in Hue",
    "Bun bo Hue"
  ],

  "source_text": "Bun bo Hue is one of the most famous dishes from Hue...",
  "retrieval_text": "Article: Best food in Hue\nSection: Bun bo Hue\nHeading path: Best food in Hue > Bun bo Hue\nLocation: Hue\nCategory: food\nLanguage: en\n\nBun bo Hue is one of the most famous dishes from Hue...",

  "metadata": {
    "title": "Best food in Hue",
    "url": "https://vietnam.travel/...",
    "language": "en",
    "source_domain": "vietnam.travel",

    "primary_location": "Hue",
    "region": "Central Vietnam",
    "category": "food",
    "topic": "bun bo hue",
    "entity_type"=["dish"], 
    "content_type":"travel_guide", 

    "section_index": 1,
    "chunk_index": 0,
    "word_count": 180,
    "char_length": 920,
    "chunker_version": "parent_child_v1"
  }
}
```

Schema Chorma
```json 
{
  "id": "doc_001:child:0001:00",

  "document": "Article: Best food in Hue\nSection: Bun bo Hue\nHeading path: Best food in Hue > Bun bo Hue\nLocation: Hue\nCategory: food\nLanguage: en\n\nBun bo Hue is one of the most famous dishes from Hue...",

  "embedding": [0.012, -0.034, 0.088],

  "metadata": {
    "record_type": "child",
    "child_id": "doc_001:child:0001:00",
    "parent_id": "doc_001:parent:document",
    "document_id": "doc_001",

    "title": "Best food in Hue",
    "url": "https://vietnam.travel/...",
    "language": "en",
    "source_domain": "vietnam.travel",

    "heading": "Bun bo Hue",
    "heading_level": 2,
    "heading_path": "Best food in Hue > Bun bo Hue",

    "primary_location": "Hue",
    "region": "Central Vietnam",
    "category": "food",
    "topic": "bun bo hue",
    "entity_type"=["dish"], 
    "content_type":"travel_guide", 
    
    "section_index": 1,
    "chunk_index": 0,
    "word_count": 180,
    "char_length": 920
  }
}
```

**Metadata filtering là việc áp dụng điều kiện có cấu trúc lên metadata để giới hạn phạm vi tìm kiếm**

```
Toàn bộ vector database
        ↓
Lọc các chunk thuộc Đà Nẵng
        ↓
Lọc các chunk về ẩm thực
        ↓
Vector similarity search
        ↓
Top-k kết quả
```

- Medata khác với keyword filtering . Bời vì Keywork sẽ tìm kiếm trong nội dung còn metadata mô tả thông tin về chunk đó. Ví dụ nội dung không có keyword (Đà Nẵng) nhưng trong metadata children có từ đó nhờ context đến từ parent.

### Why
- Vector similarity không hiểu ràng buộc cứng. Như khi tra cứu Huế nhưng nó sẽ tính similarity trên toàn bộ data thay vì lọc ra tài liệu liên quan đến Huế 
- Giảm false postive trong retrieval 
- Tăng precision của retrieval 
- Giảm chi phí reraking và generation 
- Hỗ trợ query planning và agentic retrieval 
### When - Khi nào nên dùng metadata filtering 
- Khi query chứa  rằng buộc rõ ràng 
	- địa điểm , loại dịch vụ , thời gian , loại hoạt động, mùa, ..... 
- Khi một điều kiện là hard constraint
	- Hard constraint là điều kiện mà nếu vi phạm thì kết quả gần như vô dụng 
	- Ví dụ như : món ăn ở Huế, hay cho tui các quán đồ ăn chay 
- Khi corpous lớn và nhiều nội dung tương đồng 
- Khi cần kiểm tra độ mới của dữ liệu hay thời gian dữ liệu 
- Khi có nhiều nguồn dữ liệu 
### khi nào không nên dùng query cứng
- Query khám phá rộng . 
- Metadata không đáng tin cậy 
- Soft preferences. các yêu cầu như: đẹp , lãng mạn , ngon , yên bình , ..... thường mang tính chủ quan và cảm xúc 

### How 
#### Pre-filtering 
- Lọc medata trước khi vector search
```
Metadata filter
      ↓
Candidate subset
      ↓
Vector similarity search
      ↓
Top-k
```

- Ưu điểm: 
	- Kết quả ít phạm vi sai phạm 
	- Giảm search space 
	- nhanh nếu vector DB có metadata tốt 
	- phù hợp với hard constraints 
- Nhược điểm:
	- metadata sai có thể làm mất tài liệu đúng 
	- filter quá chặt làm giảm recall 
	- có thể không đủ top k
	- hiệu năng phù thuộc vào cách vector database thực thi 

#### Post-filtering 
- Vector search trước, rồi loại kết quả không thỏa metadata

```
Vector search top-N
      ↓
Metadata filter
      ↓
Top-k hợp lệ
```

- Ưu điểm: 
	- Không làm mất ứng viên quá sớm 
	- Phù hợp với vector DB không hỗ trợ filter mạnh 
	- Có thể kiểm ttra nhiều chiến lược filtering linh hoạt 
- Nhược điểm
	- phải retrieval trên dữ liệu lớn 
	- Tăng letency 
	- không tốt với data lớn 

#### Hybrid Filtering 

# 5. Query Transformation và Intent Routing 

### Query Transformation 
#### What
Là quá trình biến đổi query ban đầu của người dùng thành một hoặc nhiều query phù hợp hơn với: 
- embedding model 
- retriever 
- metadata schema 
- loại câu hỏi , cấu trúc cần tìm 

#### Why
- Query người dùng thường ngắn và thiếu ngữ cảnh 
- Vocabulary của người dùng khác với của document hay corpus 
- Một query có thể chứa nhiều yêu cầu 

#### Các loại Query Transformation 
**Query rewriting**: Chuyển query thành phiên bản rõ ràng hơn nhưng vẫn giữ nguyên một intent 
- VD: Huế ăn gì --> Các món ăn ngon tại Huế
- Phù hợp khi: 
	- Query ngắn, không đủ ngữ cảnh , sai chính tả, không dấu , thiếu từ khóa chính, .....
- Ưu điểm: 
	- đơn giản
	- chỉ cần 1 retrieval 
	- tăng semantic context 
	- latency thấp hơn multi-query
- Nhược điểm: 
	- LLM có thể thay đổi ý nghĩa 
	- có thể bịa đặt  hoặc thêm ràng buộc ngừi dung không nói 
	- rewrite sai khiến toàn bộ retrieval sai 
**Multi-query generation**: Sinh nhiều câu hỏi khác nhau cho cùng 1 nhu cầu 
```
Original:
“What should a family do in Da Nang?”

Queries:
1. Family-friendly attractions in Da Nang
2. Activities for children in Da Nang
3. Safe outdoor experiences for families in Da Nang
4. Da Nang sightseeing suitable for parents and kids
```

- Sử dụng RAG-fusion : hướng kết hợp multi-query generation với Reciprocal Rank Funsion để hợp nhất các danh sách kết quả
- Ưu điểm: 
	- Tăng recalll 
	- giảm sự phụ thuộc vào 1 cách diễn đạt 
	- tìm được tài liệu dùng từ ngữ khác 
	- hữu ích với query mơ hồ và cung cấp nhiều góc nhìn 
- Nhược điểm 
	- nhiều lần retrieval 
	- candidate pool lớn 
	- Tăng latency 
	- Tăng chi phí 
	- Query sinh ra có thể trùng nhau 
**Query decomposition**
- Tách query phức tạp thành nhiều query nhỏ hơn có mục tiêu khác nhau 
	- Vd: Lập lịch trình 3 ngày ở Huế cho gia đình , thích văn hoá, mua sắm đồ ăn và không muốn di chuyển nhiều 
```json
{
  "global_constraints": {
    "location": "Hue",
    "duration_days": 3,
    "audience": "couple",
    "mobility_preference": "low_travel_distance"
  },
  "subqueries": [
    {
      "intent": "attraction_search",
      "query": "Cultural attractions in Hue suitable for couples"
    },
    {
      "intent": "food_search",
      "query": "Local dishes and food experiences in Hue"
    },
    {
      "intent": "transport_search",
      "query": "Travel times and transportation between Hue attractions"
    },
    {
      "intent": "itinerary_examples",
      "query": "Three-day itinerary in Hue"
    }
  ]
}
```

- Khi nào nên dùng: 
	- Nhiều task 
	- Nhiều intant , nhiều category 
	- Câu hỏi cần tổng hợp từ nhiều nguồn
- Nhược điểm: 
	- Khó giữ được context chính 
	- Có thể tách quá nhỏ 
	- Tăng số retrieval call 
	- kết quả có thể gặp nhiều mâu thuẫn do dựa vào query người dùng 


### Intent Routing 
Intent Routing là quá trình xác định : Người dùng muốn hệ thống làm nhiệm vụ gì 
- Retriever phù hợp 
- tool phù hợp 
- prompt phù hợp 
- ...... 
Metada cho biết điều kiện , còn Intent Routing cho biết nhiệm vụ

#### Why
- Không phải query nào cũng cần RAG giống nhau
- Mỗi intent có retrieval objective khác nhau
	- Factual QA : cần  precision cao
	- Recomendation : cần relevance + diversity
- Giảm chi phí không cần thiết 
- Tăng khả năng kiểm soát 

#### Các kiểu Intent Routing 
**Rule-based routing**
- Ưu điểm: nhanh, rẻm dễ debug, tốt với các intent rõ ràng
- Nhược điểm: 
	- khó với nhiều intent 
	- khó hiểu ngữ cảnh 
	- Query phức tạp 
**Embedding-based routing**
- Tạo mô tả cho mỗi route --> Embed query và route description --> chọn route gần nhất 
- Ưu điểm: 
	- Nhanh hơn LLM 
	- Semantic tốt hơn keyword 
	- không cần prompt dài 
	- dễ mở rộng route 
- Nhược điểm: 
	- Khó xử lý khi query có nhiều intent
	- Nhiều route có thể bị nhầm 
	- giải thích quyết định hạn chế 
**LLM based Routing ** 
- Cho LLM chọn Route 
VD output: 
```json 
{
  "task_intent": "plan",
  "domains": ["attraction", "food", "transportation"],
  "route": "itinerary_pipeline",
  "confidence": 0.94,
  "reason": "The user requests a three-day schedule..."
}
```

- Ưu điểm: 
	- hiểu context complex 
	- Xử lý multi-intent 
	- dễ dùng structure schema 
	- dễ bổ sung routing reasoning 
- Nhược điểm
	- Latency, chi phí 
	- Output không ổn định 
	- prompt có thể ảnh hưởng đến route 

### Query De-contextualization 
#### **Thiết kế bộ nhớ --> Nhất Nguyên đang triển khai**

- Mục tiêu: Conversation history + current query
# 6. Hybrid Search and Reranking 
## Hybrid Search 
### What 
Là kỹ thuật kết hợp hai hoặc nhiều phương pháp tìm kiếm thành 1 danh sách kết quả thống nhất 
```
Sparse/Lexical Retrieval
        +
Dense/Semantic Retrieval
```

Cụ thể
```
BM25
   +
Dense Vector Search
```

- BM25 tìm dựa trên sự trùng hợp từ khóa, còn Dense Search tìm dựa trên sự tương đồng về ngữ nghĩa. Hybrid Search gộp hai danh sách này lại 

### Purpose 
- Tăng candidate recall 
- Giảm điểm yếu riêng của từng retriever 
- Tăng robustness với nhiều lại query 

## Reranking 

### what 
Reranking là giai đoạn thứ 2  của Retrieval , nhận vào query+Candidate document và xuất ra Candidate documents được sắp xếp lại theo độ liên quan 
### Why 
Khi lấy được candidate documents , tuy nhiên lấy dựa trên simiularity. Cần tinh chỉnh lại để được kết quả tốt hơn. Hybrid Search giúp lọc để lấy bộ ứng cử viên , như chọn lọc sách Toán học trong thư viện. Sau đó reranking nhằm mục đích chọn  lọc lại trong danh sách toán học đó (Vd: Lấy sách giải tích vì hoc đại học thay vì sách cấp 1)
### How 
#### Cross - Encoder Reranker 
- Cross encoder : nó không encode riêng. Nó ghép 2 đoạn văn lại. Sau đó đưa toàn bộ vào Transformer 
- Nó sẽ trả lời cho câu hỏi: Document có thực sự trả lời Query này không ? chứ không phải Hai đoạn văn này có liên quan đến nhau không 
Tại sao không dùng Cross-encoder cho retrieval:
- Quá chậm và tốn tài nguyên. 
#### LLM reranker 
#### Rule-based reranking 
#### Hybrid reranking 
Ví dụ: 
```
FinalScore = 0.8 × CrossEncoder + 0.2 × Metadata
```
