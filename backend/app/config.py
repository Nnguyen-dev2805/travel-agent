import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, model_validator

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
dotenv_path = ROOT_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)


class Settings(BaseModel):
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    PROJECT_NAME: str = "Vietnam Travel Agent API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # CORS
    CORS_ORIGINS: list[str] = [
        origin.strip() 
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") 
        if origin.strip()
    ]

    # LLM & Google Gemini API Configuration
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")

    # Multi-model Configuration (fallback to LLM_MODEL if not explicitly set)
    MAIN_LLM_MODEL: str = os.getenv("MAIN_LLM_MODEL", LLM_MODEL)
    ROUTER_MODEL: str = os.getenv("ROUTER_MODEL", LLM_MODEL)
    MEMORY_EXTRACTION_MODEL: str = os.getenv("MEMORY_EXTRACTION_MODEL", LLM_MODEL)
    CONFLICT_RESOLUTION_MODEL: str = os.getenv("CONFLICT_RESOLUTION_MODEL", LLM_MODEL)
    EVALUATION_MODEL: str = os.getenv("EVALUATION_MODEL", LLM_MODEL)

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
    ENABLE_CONTEXT_ROUTER: bool = os.getenv("ENABLE_CONTEXT_ROUTER", "true").lower() == "true"

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.ENVIRONMENT.lower() == "production" and self.SECRET_KEY == "dev-secret-key-change-in-production-12345":
            raise ValueError("BẢO MẬT NGHIÊM TRỌNG: SECRET_KEY phải được thiết lập khi chạy trên môi trường production!")
        return self


settings = Settings()
