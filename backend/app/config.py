import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
dotenv_path = ROOT_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

class Settings(BaseModel):
    PROJECT_NAME: str = "Vietnam Travel Agent API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    GITHUB_MODELS_URL: str = os.getenv("GITHUB_MODELS_BASE_URL", "https://models.inference.ai.azure.com")

    RETRIEVER_MODE: str = os.getenv("RETRIEVER_MODE", "dense").lower()
    RAG_COLLECTION_NAME: str = os.getenv("RAG_COLLECTION_NAME", "vietnam_travel_parent_child")
    HYBRID_CANDIDATE_K: int = int(os.getenv("HYBRID_CANDIDATE_K", "30"))
    HYBRID_DENSE_WEIGHT: float = float(os.getenv("HYBRID_DENSE_WEIGHT", "0.65"))
    HYBRID_BM25_WEIGHT: float = float(os.getenv("HYBRID_BM25_WEIGHT", "0.35"))
    HYBRID_RRF_K: int = int(os.getenv("HYBRID_RRF_K", "60"))

    ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    ELASTICSEARCH_INDEX: str = os.getenv("ELASTICSEARCH_INDEX", "travel_child_chunks_v1")
    ELASTICSEARCH_USERNAME: str = os.getenv("ELASTICSEARCH_USERNAME", "")
    ELASTICSEARCH_PASSWORD: str = os.getenv("ELASTICSEARCH_PASSWORD", "")
    ELASTICSEARCH_API_KEY: str = os.getenv("ELASTICSEARCH_API_KEY", "")
    ELASTICSEARCH_VERIFY_CERTS: bool = os.getenv("ELASTICSEARCH_VERIFY_CERTS", "false").lower() == "true"
    ELASTICSEARCH_REQUEST_TIMEOUT: int = int(os.getenv("ELASTICSEARCH_REQUEST_TIMEOUT", "30"))

    RERANKER_ENABLED: bool = os.getenv("RERANKER_ENABLED", "false").lower() == "true"
    RERANKER_PROVIDER: str = os.getenv("RERANKER_PROVIDER", "tei").lower()
    TEI_RERANK_URL: str = os.getenv("TEI_RERANK_URL", "")
    RERANKER_TIMEOUT_SECONDS: float = float(os.getenv("RERANKER_TIMEOUT_SECONDS", "120"))
    RERANKER_CANDIDATE_K: int = int(os.getenv("RERANKER_CANDIDATE_K", "20"))
    RERANKER_BATCH_SIZE: int = int(os.getenv("RERANKER_BATCH_SIZE", "8"))
    RERANKER_MAX_TEXT_CHARS: int = int(os.getenv("RERANKER_MAX_TEXT_CHARS", "2000"))
    RERANKER_RAW_SCORES: bool = os.getenv("RERANKER_RAW_SCORES", "false").lower() == "true"

settings = Settings()
