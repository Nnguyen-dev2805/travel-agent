"""Giao diện Streamlit đơn giản cho chatbot RAG du lịch Việt Nam."""

from __future__ import annotations

import json
import importlib.util
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import streamlit as st
from openai import OpenAI


def find_project_root(start: Path) -> Path:
    """Tìm thư mục gốc project để import backend và đọc data ổn định."""

    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "backend" / "rag").exists() and (candidate / "data").exists():
            return candidate
    raise RuntimeError("Không tìm thấy project root. Hãy chạy app trong repo travel-agent.")


PROJECT_ROOT = find_project_root(Path(__file__).resolve())
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Embedding baseline dùng PyTorch, không dùng TensorFlow.
# Thiết lập trước khi import sentence-transformers để tránh lỗi Keras 3.
os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["USE_TF"] = "0"


def ensure_import(package_name: str, pip_name: str | None = None, version: str | None = None) -> None:
    """Đảm bảo package cần thiết đã cài nhưng không import quá sớm."""

    if importlib.util.find_spec(package_name) is not None:
        return

    install_name = pip_name or package_name
    if version:
        install_name = f"{install_name}=={version}"
    subprocess.check_call([sys.executable, "-m", "pip", "install", install_name])
    if importlib.util.find_spec(package_name) is None:
        raise ModuleNotFoundError(f"Đã cài {install_name} nhưng vẫn chưa tìm thấy {package_name}.")


# Hai dependency này bắt buộc cho retriever baseline: đọc FAISS index và embed query.
ensure_import("faiss", pip_name="faiss-cpu", version="1.8.0.post1")
ensure_import("sentence_transformers", pip_name="sentence-transformers", version="3.2.1")


from backend.rag.generation.prompt_builder import PromptBuilderConfig, TravelRAGPromptBuilder
from backend.rag.retrieval.baseline_retrievers import RetrieverConfig, build_retrievers


DEFAULT_MODEL = "openai/gpt-4o-mini"


def load_env_file(env_path: Path) -> None:
    """Đọc file .env nếu có, không ghi đè biến môi trường hiện tại."""

    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_api_config_from_test_model_notebook(notebook_path: Path) -> None:
    """Fallback lấy GITHUB_TOKEN/base_url/model từ backend/test_model.ipynb."""

    if not notebook_path.exists():
        return
    try:
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    except Exception:
        return

    code_text = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook.get("cells", [])
        if cell.get("cell_type") == "code"
    )

    token_match = re.search(r"os\.environ\[[\"']GITHUB_TOKEN[\"']\]\s*=\s*[\"']([^\"']+)[\"']", code_text)
    if token_match:
        os.environ.setdefault("GITHUB_TOKEN", token_match.group(1))

    base_url_match = re.search(r"base_url\s*=\s*[\"']([^\"']+)[\"']", code_text)
    if base_url_match:
        os.environ.setdefault("GITHUB_MODELS_BASE_URL", base_url_match.group(1))

    model_match = re.search(r"model\s*=\s*[\"']([^\"']+)[\"']", code_text)
    if model_match:
        os.environ.setdefault("CHAT_MODEL", model_match.group(1))


def split_keys(value: str | None) -> list[str]:
    """Tách danh sách API key từ chuỗi phân cách bằng dấu phẩy hoặc xuống dòng."""

    if not value:
        return []
    return [item.strip() for item in re.split(r"[,\n]+", value) if item.strip()]


def resolve_api_config(api_keys_text: str, provider: str, api_base_url: str) -> tuple[str, list[str]]:
    """Lấy endpoint và key cho OpenAI-compatible API."""

    inline_keys = split_keys(api_keys_text)
    if inline_keys:
        first_key = inline_keys[0]
        if first_key.startswith("sk-or-v1-"):
            provider = "openrouter"
        elif first_key.startswith("ghp_") or first_key.startswith("github_pat_"):
            provider = "github"

        if provider == "openrouter":
            return api_base_url or "https://openrouter.ai/api/v1", inline_keys
        if provider == "openai":
            return api_base_url or "https://api.openai.com/v1", inline_keys
        return api_base_url or "https://models.github.ai/inference", inline_keys

    openrouter_keys = split_keys(os.getenv("OPENROUTER_API_KEYS"))
    if openrouter_keys:
        return os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"), openrouter_keys

    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        return os.getenv("GITHUB_MODELS_BASE_URL", "https://models.github.ai/inference"), [github_token]

    openai_keys = split_keys(os.getenv("OPENAI_API_KEYS")) or split_keys(os.getenv("OPENAI_API_KEY"))
    if openai_keys:
        return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"), openai_keys

    raise RuntimeError("Chưa có API key. Hãy cấu hình key ở sidebar, .env hoặc backend/test_model.ipynb.")


class RotatingChatClient:
    """Client chat có retry và đổi key khi gặp rate limit."""

    def __init__(self, base_url: str, api_keys: list[str], model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_keys = api_keys
        self.model = model
        self.key_index = 0

    def _client(self) -> OpenAI:
        return OpenAI(base_url=self.base_url, api_key=self.api_keys[self.key_index])

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 900) -> str:
        """Gọi chat completion với retry nhẹ."""

        retry_terms = ["too many requests", "rate", "quota", "limit", "429", "insufficient"]
        last_error: Exception | None = None
        max_attempts = max(1, len(self.api_keys) * 3)
        for attempt in range(max_attempts):
            try:
                response = self._client().chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content or ""
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()
                can_retry = any(term in message for term in retry_terms)
                if can_retry and attempt < max_attempts - 1:
                    if len(self.api_keys) > 1:
                        self.key_index = (self.key_index + 1) % len(self.api_keys)
                    time.sleep(min(20, 2 * (attempt + 1)))
                    continue
                raise
        raise RuntimeError(f"Không gọi được chat model: {last_error}")


def extract_json_object(text: str) -> dict[str, Any]:
    """Trích JSON từ output LLM khi dịch query."""

    clean_text = text.strip()
    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```(?:json)?", "", clean_text).strip()
        clean_text = re.sub(r"```$", "", clean_text).strip()
    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean_text, re.DOTALL)
        if not match:
            return {"english_query": text, "intent": "general", "detected_locations": []}
        return json.loads(match.group(0))


VIETNAMESE_CHAR_PATTERN = re.compile(
    r"[ăâđêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]",
    re.IGNORECASE,
)
VIETNAMESE_HINT_WORDS = {
    "ở", "đi", "đến", "nên", "gì", "món", "ăn", "chơi", "lịch", "trình",
    "khách", "sạn", "địa", "điểm", "tham", "quan", "bao", "nhiêu", "ngày",
    "buổi", "sáng", "tối", "mùa", "nào", "đẹp", "tiện", "gợi", "ý",
}
ENGLISH_HINT_WORDS = {
    "what", "where", "when", "which", "how", "best", "travel", "trip", "food",
    "restaurant", "hotel", "stay", "itinerary", "attraction", "visit", "things",
    "to", "do", "in", "near", "around", "recommend", "guide",
}


def detect_query_language(query: str) -> str:
    """Detect nhanh ngôn ngữ query để tránh dịch lại query tiếng Anh."""

    text = query.strip().lower()
    if not text:
        return "unknown"
    if VIETNAMESE_CHAR_PATTERN.search(text):
        return "vi"

    tokens = re.findall(r"[a-zA-ZÀ-ỹ]+", text)
    if not tokens:
        return "unknown"

    vi_hits = sum(1 for token in tokens if token in VIETNAMESE_HINT_WORDS)
    en_hits = sum(1 for token in tokens if token in ENGLISH_HINT_WORDS)
    if vi_hits > en_hits:
        return "vi"
    if en_hits > 0:
        return "en"
    return "en"


def prepare_retrieval_query(question: str, client: RotatingChatClient) -> dict[str, Any]:
    """Chuẩn bị query retrieval: tiếng Anh thì dùng thẳng, tiếng Việt thì dịch."""

    detected_language = detect_query_language(question)
    if detected_language == "en":
        return {
            "retrieval_query": question,
            "retrieval_query_language": "en",
            "translation_status": "skipped",
            "translation_metadata": {
                "english_query": question,
                "detected_locations": [],
                "intent": "general",
                "reason": "Input đã được detect là tiếng Anh nên bỏ qua bước dịch.",
            },
        }

    translation = translate_query_to_english(question, client)
    return {
        "retrieval_query": str(translation.get("english_query") or question),
        "retrieval_query_language": "en",
        "translation_status": "success",
        "translation_metadata": translation,
    }


@st.cache_resource(show_spinner="Đang nạp FAISS index và embedding model...")
def load_retriever_resources(device: str) -> tuple[Any, Any, Any]:
    """Nạp retrievers một lần để app phản hồi nhanh hơn."""

    config = RetrieverConfig(
        registry_path=PROJECT_ROOT / "configs" / "embedding_models.json",
        model_id="paraphrase-multilingual-MiniLM-L12-v2",
        index_dir=PROJECT_ROOT / "data" / "indexes" / "paraphrase-multilingual-MiniLM-L12-v2_standard_rag",
        device=device,
    )
    return build_retrievers(config)


@st.cache_resource(show_spinner=False)
def load_prompt_builder(max_context_chars: int, max_chunk_chars: int) -> TravelRAGPromptBuilder:
    """Nạp prompt builder dùng chung cho các lượt chat."""

    return TravelRAGPromptBuilder(
        PromptBuilderConfig(
            prompt_config_path=PROJECT_ROOT / "configs" / "rag_generation_prompts.json",
            max_context_chars=max_context_chars,
            max_chunk_chars=max_chunk_chars,
        )
    )


def normalize_messages_for_endpoint(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Đổi role developer sang system để tương thích các OpenAI-compatible endpoint."""

    normalized = []
    for message in messages:
        role = message.get("role", "user")
        normalized.append({"role": "system" if role == "developer" else role, "content": message.get("content", "")})
    return normalized


def translate_query_to_english(question_vi: str, client: RotatingChatClient) -> dict[str, Any]:
    """Dịch query tiếng Việt sang query tiếng Anh tối ưu cho retrieval."""

    messages = [
        {
            "role": "system",
            "content": (
                "Bạn là bộ chuyển đổi truy vấn cho retrieval du lịch Việt Nam. "
                "Chuyển câu hỏi tiếng Việt thành query tiếng Anh ngắn, giàu keyword, giữ đúng địa danh và intent. "
                "Chỉ trả về JSON hợp lệ."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Câu hỏi tiếng Việt: {question_vi}\n\n"
                "Schema JSON:\n"
                '{"english_query":"...","detected_locations":["..."],"intent":"..."}'
            ),
        },
    ]
    raw = client.chat(messages, temperature=0.0, max_tokens=250)
    data = extract_json_object(raw)
    data.setdefault("english_query", question_vi)
    data.setdefault("detected_locations", [])
    data.setdefault("intent", "general")
    return data


def search_with_retriever(query: str, retriever_name: str, top_k: int, candidate_k: int) -> list[dict[str, Any]]:
    """Chạy retrieval theo lựa chọn trên giao diện."""

    dense, bm25, hybrid = load_retriever_resources(device=os.getenv("RAG_EMBEDDING_DEVICE", "cpu"))
    if retriever_name == "dense":
        return dense.search(query, top_k=top_k)
    if retriever_name == "bm25":
        return bm25.search(query, top_k=top_k)
    return hybrid.search(query, top_k=top_k, candidate_k=candidate_k)


def answer_question(question_vi: str, chunks: list[dict[str, Any]], client: RotatingChatClient, detail_level: str) -> str:
    """Sinh câu trả lời tiếng Việt dựa trên retrieved context."""

    prompt_builder = load_prompt_builder(max_context_chars=11000, max_chunk_chars=2200)
    messages = normalize_messages_for_endpoint(prompt_builder.build_messages(question_vi, chunks))
    detail_instruction = {
        "Gọn": "Trả lời gọn nhưng vẫn đủ ý chính, khoảng 3-5 bullet hoặc đoạn ngắn.",
        "Chuẩn": "Trả lời chuyên nghiệp, đủ chi tiết, khoảng 5-8 bullet hoặc đoạn ngắn.",
        "Chi tiết": "Trả lời kỹ hơn như tư vấn viên du lịch, có phân tích lý do, lưu ý thực tế và nguồn.",
    }.get(detail_level, "Trả lời chuyên nghiệp, đủ chi tiết.")
    messages.append(
        {
            "role": "user",
            "content": (
                "YÊU CẦU BỔ SUNG VỀ ĐỘ DÀI VÀ PHONG CÁCH:\n"
                f"- {detail_instruction}\n"
                "- Không trả lời cụt một đoạn nếu context có đủ thông tin.\n"
                "- Trình bày có tiêu đề nhỏ hoặc bullet rõ ràng."
            ),
        }
    )
    max_tokens = {"Gọn": 900, "Chuẩn": 1500, "Chi tiết": 2200}.get(detail_level, 1500)
    return client.chat(messages, temperature=0.25, max_tokens=max_tokens).strip()


def is_rate_limit_error(error: Exception) -> bool:
    """Nhận diện lỗi rate limit/quota từ API model."""

    message = str(error).lower()
    return any(term in message for term in ["too many requests", "rate", "quota", "limit", "429"])


def build_retrieval_fallback_answer(question: str, retrieval_query: str, chunks: list[dict[str, Any]], error: Exception | None = None) -> str:
    """Tạo câu trả lời extractive khi chưa dùng được LLM generation."""

    lines = [
        "Dựa trên các nguồn liên quan nhất trong knowledge base, mình có thể tóm tắt nhanh như sau:",
        "",
        f"**Nhu cầu của bạn:** {question}",
        "",
        "**Gợi ý chính từ dữ liệu tìm được:**",
    ]

    for index, item in enumerate(chunks[:4], 1):
        title = item.get("document_title") or "Không rõ tiêu đề"
        url = item.get("source_url") or ""
        preview = " ".join(str(item.get("source_text") or "").split())[:850]
        lines.append(f"{index}. **{title}**")
        if url:
            lines.append(f"   Nguồn: {url}")
        if preview:
            lines.append(f"   Nội dung liên quan: {preview}...")

    lines.extend(
        [
            "",
            "**Nhận xét thực tế:**",
            "Các gợi ý trên được rút trực tiếp từ retrieved chunks. Bạn nên xem đây là bản tóm tắt định hướng; khi API LLM ổn định, chatbot sẽ tổng hợp lại mạch lạc hơn theo lịch trình, món ăn, khu vực hoặc tiêu chí cụ thể.",
            "",
            f"**Query dùng để retrieval:** {retrieval_query}",
        ]
    )

    if error:
        lines.extend(
            [
                "",
                "Ghi chú: model generation đang bị rate limit, nên câu trả lời này là bản extractive từ context thay vì bản tổng hợp đầy đủ bởi LLM.",
            ]
        )
    return "\n".join(lines)


def render_source_card(source: dict[str, Any]) -> None:
    """Hiển thị một nguồn retrieved trong expander."""

    title = source.get("document_title") or "Không rõ tiêu đề"
    url = source.get("source_url") or ""
    st.markdown(f"**#{source.get('rank')} - {title}**")
    st.caption(f"Score: {source.get('score')} | Retriever: {source.get('retriever')} | Language: {source.get('language')}")
    if url:
        st.markdown(f"[Mở nguồn]({url})")
    preview = " ".join(str(source.get("source_text") or "").split())[:900]
    st.write(preview + ("..." if len(preview) >= 900 else ""))


def main() -> None:
    """Điểm vào Streamlit app."""

    st.set_page_config(page_title="Travel RAG Chatbot", page_icon="🇻🇳", layout="wide")
    load_env_file(PROJECT_ROOT / ".env")
    load_api_config_from_test_model_notebook(PROJECT_ROOT / "backend" / "test_model.ipynb")

    st.title("Chatbot Du lịch Việt Nam")
    st.caption("Query tiếng Việt -> dịch sang tiếng Anh để retrieval -> trả lời tiếng Việt bằng gpt-4o-mini.")

    with st.sidebar:
        st.header("Cấu hình")
        retriever_name = st.selectbox("Retriever", ["hybrid", "dense", "bm25"], index=0)
        top_k = st.slider("Top K chunks", min_value=1, max_value=10, value=5)
        candidate_k = st.slider("Candidate K cho hybrid", min_value=10, max_value=50, value=20, step=5)
        model = st.text_input("Chat model", value=os.getenv("CHAT_MODEL", DEFAULT_MODEL))
        default_provider = "openrouter" if os.getenv("OPENROUTER_API_KEYS") else "github"
        provider_options = ["github", "openrouter", "openai"]
        provider = st.selectbox("API provider", provider_options, index=provider_options.index(default_provider))
        api_base_url = st.text_input("API base URL tuỳ chọn", value="")
        api_keys_text = st.text_area(
            "API key tuỳ chọn",
            value="",
            height=90,
            help="Có thể nhập nhiều OpenRouter key, mỗi key một dòng. Để trống nếu .env hoặc backend/test_model.ipynb đã có key.",
        )
        translate_vi_query = st.checkbox(
            "Dịch query tiếng Việt sang tiếng Anh bằng LLM",
            value=False,
            help="Tắt mặc định để giảm rate limit. Embedding hiện tại là multilingual nên vẫn search được query tiếng Việt.",
        )
        answer_mode = st.selectbox(
            "Chế độ trả lời",
            ["Tự động: LLM, fallback extractive", "Chỉ extractive, không gọi LLM"],
            index=0,
        )
        detail_level = st.selectbox("Độ chi tiết câu trả lời", ["Chuẩn", "Chi tiết", "Gọn"], index=0)
        st.divider()
        show_sources = st.checkbox("Hiện nguồn retrieved", value=True)
        show_query_en = st.checkbox("Hiện query tiếng Anh", value=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("query_en") and show_query_en:
                st.caption(f"{message.get('query_label') or 'Query retrieval'}: {message['query_en']}")
                if message.get("retrieval_query_language") or message.get("translation_status"):
                    st.caption(
                        f"Ngôn ngữ query retrieval: {message.get('retrieval_query_language', 'unknown')} "
                        f"| Trạng thái dịch: {message.get('translation_status', 'unknown')}"
                    )
            if message.get("sources") and show_sources:
                with st.expander("Nguồn retrieved"):
                    for source in message["sources"]:
                        render_source_card(source)

    question = st.chat_input("Hỏi về địa điểm, lịch trình, món ăn, trải nghiệm du lịch Việt Nam...")
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        try:
            base_url, api_keys = resolve_api_config(api_keys_text, provider, api_base_url)
            client = RotatingChatClient(base_url=base_url, api_keys=api_keys, model=model)

            with st.status("Đang xử lý RAG...", expanded=False) as status:
                st.write("Đang kiểm tra ngôn ngữ và chuẩn bị query retrieval...")
                translation_error = None
                try:
                    detected_language = detect_query_language(question)
                    if translate_vi_query and detected_language == "vi":
                        query_payload = prepare_retrieval_query(question, client)
                        retrieval_query = str(query_payload["retrieval_query"])
                        retrieval_query_language = str(query_payload["retrieval_query_language"])
                        translation_status = str(query_payload["translation_status"])
                        query_label = "Query retrieval tiếng Anh"
                    else:
                        retrieval_query = question
                        retrieval_query_language = detected_language
                        translation_status = "skipped"
                        query_label = "Query retrieval gốc"
                except Exception as exc:
                    translation_error = exc
                    retrieval_query = question
                    retrieval_query_language = detect_query_language(question)
                    translation_status = "failed"
                    query_label = "Query retrieval fallback"
                    st.warning("Bước chuẩn bị/dịch query bị lỗi, app sẽ dùng query gốc để retrieval.")

                st.write(f"Đang retrieval bằng `{retriever_name}`...")
                chunks = search_with_retriever(retrieval_query, retriever_name, top_k, candidate_k)

                if answer_mode.startswith("Chỉ extractive"):
                    st.write("Đang tạo câu trả lời extractive từ retrieved chunks...")
                    answer = build_retrieval_fallback_answer(question, retrieval_query, chunks)
                else:
                    st.write("Đang sinh câu trả lời bằng gpt-4o-mini...")
                    try:
                        answer = answer_question(question, chunks, client, detail_level)
                    except Exception as exc:
                        if chunks and is_rate_limit_error(exc):
                            st.warning("Bước sinh câu trả lời bị rate limit. App chuyển sang câu trả lời extractive từ retrieval.")
                            answer = build_retrieval_fallback_answer(question, retrieval_query, chunks, exc)
                        else:
                            raise

                if translation_error and answer:
                    answer = (
                        "Lưu ý: bước dịch query sang tiếng Anh bị rate limit nên mình đã dùng query gốc tiếng Việt để retrieval.\n\n"
                        + answer
                    )
                status.update(label="Hoàn tất", state="complete")

            placeholder.markdown(answer)
            if show_query_en:
                st.caption(f"{query_label}: {retrieval_query}")
                st.caption(f"Ngôn ngữ query retrieval: {retrieval_query_language} | Trạng thái dịch: {translation_status}")
            if show_sources:
                with st.expander("Nguồn retrieved", expanded=True):
                    for source in chunks:
                        render_source_card(source)

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": answer,
                    "query_en": retrieval_query,
                    "query_label": query_label,
                    "retrieval_query_language": retrieval_query_language,
                    "translation_status": translation_status,
                    "sources": chunks,
                }
            )
        except Exception as exc:
            error_message = f"Lỗi khi chạy chatbot: {exc}"
            placeholder.error(error_message)
            st.session_state.messages.append({"role": "assistant", "content": error_message})


if __name__ == "__main__":
    main()
