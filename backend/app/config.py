import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
dotenv_path = ROOT_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

logger = logging.getLogger("travel_agent_config")

# Shared local application store per ADR 0004. One SQLite file holds every
# relational product record for the prototype, with schema versions tracked per
# module. SQLite is a local development adapter; it is not production storage
# readiness.
DEFAULT_APP_DB_PATH = ROOT_DIR / "data" / "app" / "travel_agent.sqlite3"

# The R3 default, retained only so the deprecated alias keeps its original
# meaning for a local environment that still sets it.
DEPRECATED_WORKSPACE_DB_PATH = (
    ROOT_DIR / "data" / "workspaces" / "travel_agent_workspaces.sqlite3"
)


def _resolve_app_db_path() -> Path:
    """Resolve the shared application database path, honoring the R3 alias.

    `APP_DB_PATH` takes precedence. When it is unset and the deprecated
    `WORKSPACE_DB_PATH` is set, the alias value is used and exactly one warning
    is logged naming the variable without its value, so an existing local
    environment keeps working instead of being silently ignored.

    This runs once, when `Settings` is defined, so the warning cannot repeat.
    """
    configured = os.getenv("APP_DB_PATH")
    if configured:
        return Path(configured)

    alias = os.getenv("WORKSPACE_DB_PATH")
    if alias:
        logger.warning(
            "WORKSPACE_DB_PATH is deprecated and will be removed; set APP_DB_PATH "
            "instead. Honoring the deprecated variable for this run."
        )
        return Path(alias)

    return DEFAULT_APP_DB_PATH


class Settings(BaseModel):
    PROJECT_NAME: str = "Vietnam Travel Agent API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    GITHUB_MODELS_URL: str = "https://models.inference.ai.azure.com"
    # Shared local application store for trip workspaces and conversations per
    # ADR 0004. SQLite is a local development adapter per ADR 0003; it is not
    # production storage readiness.
    APP_DB_PATH: Path = _resolve_app_db_path()
    # Deprecated R3 alias. Product code resolves `APP_DB_PATH`; this field exists
    # so a local environment that still sets `WORKSPACE_DB_PATH` is not broken by
    # the rename.
    WORKSPACE_DB_PATH: Path = Path(
        os.getenv("WORKSPACE_DB_PATH", str(DEPRECATED_WORKSPACE_DB_PATH))
    )


settings = Settings()
