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

    # LLM & Google Gemini API Configuration
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")

    # Security & Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production-12345")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://travel_user:travel_pass@localhost:5432/travel_agent_db"
    )

    # Memory Engine
    MEMORY_WINDOW_SIZE: int = int(os.getenv("MEMORY_WINDOW_SIZE", "10"))
    MEMORY_EXTRACTION_ENABLED: bool = os.getenv("MEMORY_EXTRACTION_ENABLED", "true").lower() == "true"


settings = Settings()
