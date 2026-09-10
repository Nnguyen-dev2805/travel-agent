import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr, field_validator

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
dotenv_path = ROOT_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

logger = logging.getLogger("travel_agent_config")


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment flag, defaulting when unset."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() == "true"


class Settings(BaseModel):
    PROJECT_NAME: str = "Vietnam Travel Agent API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    GITHUB_MODELS_URL: str = "https://models.inference.ai.azure.com"

    # Authentication credentials
    LOCAL_AUTH_TOKENS_JSON: SecretStr = SecretStr(
        os.getenv("LOCAL_AUTH_TOKENS_JSON", "{}")
    )
    MAX_REQUEST_BODY_BYTES: int = int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576"))
    ALLOWED_ORIGINS: str = os.getenv(
        "ALLOWED_ORIGINS",
        os.getenv(
            "ALLOWED_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ),
    )
    ALLOWED_CORS_ORIGINS: str = os.getenv(
        "ALLOWED_CORS_ORIGINS",
        os.getenv(
            "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ),
    )

    @field_validator("ALLOWED_ORIGINS", "ALLOWED_CORS_ORIGINS", mode="after")
    @classmethod
    def validate_no_wildcard(cls, v: str) -> str:
        origins = [part.strip() for part in v.split(",") if part.strip()]
        if "*" in origins:
            raise ValueError("Wildcard CORS origin '*' is prohibited.")
        return v

    # PostgreSQL configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    PG_HOST: str = os.getenv("PG_HOST", "localhost")
    PG_PORT: int = int(os.getenv("PG_PORT", "5433"))
    PG_DB: str = os.getenv("PG_DB", "travel_agent")
    PG_USER: str = os.getenv("PG_USER", "travel_agent")
    PG_PASSWORD: SecretStr = SecretStr(os.getenv("POSTGRES_PASSWORD", ""))

    # Basic semantic memory write pipeline feature gates (ADR 0016 / ADR 0017)
    MEMORY_WRITE_PIPELINE_ENABLED: bool = _env_flag(
        "MEMORY_WRITE_PIPELINE_ENABLED", False
    )
    MEMORY_SHADOW_EXTRACT_ENABLED: bool = _env_flag(
        "MEMORY_SHADOW_EXTRACT_ENABLED", False
    )
    MEMORY_WRITE_EVAL_FIXTURES_PATH: str = os.getenv(
        "MEMORY_WRITE_EVAL_FIXTURES_PATH",
        "docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1",
    )


def pg_dsn(password: str, host: str, port: int, db: str, user: str) -> str:
    """Build a psycopg DSN from explicit parts."""
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


settings = Settings()


def get_settings() -> Settings:
    """Return the global Settings instance."""
    return settings
