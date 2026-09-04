import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.api.health import router as health_router
from backend.app.api.chat import router as chat_router, get_rag_service
from backend.app.api.workspaces import router as workspaces_router

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("travel_agent_main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler to pre-warm RAG service and embedding models on startup."""
    logger.info("Pre-warming RAG Service & Embedding Model on server boot...")
    try:
        get_rag_service()
        logger.info("RAG Service & Embedding Model successfully pre-warmed!")
    except Exception as e:
        logger.warning(f"RAG Service pre-warming notice: {str(e)}")
    yield
    logger.info("Shutting down application...")


# Initialize FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="FastAPI Backend for Travel Agent Chatbot",
    version=settings.VERSION,
    lifespan=lifespan,
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(health_router)
app.include_router(chat_router, prefix=settings.API_V1_STR)
app.include_router(workspaces_router, prefix=settings.API_V1_STR)
