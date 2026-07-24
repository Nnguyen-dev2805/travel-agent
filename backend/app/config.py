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
    GITHUB_MODELS_URL: str = "https://models.inference.ai.azure.com"

settings = Settings()
