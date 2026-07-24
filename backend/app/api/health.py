from fastapi import APIRouter
from backend.app.config import settings

router = APIRouter()

@router.get("/health")
def health_check():
    """Health check endpoint for monitoring & CI/CD."""
    return {"status": "ok", "service": settings.PROJECT_NAME}
