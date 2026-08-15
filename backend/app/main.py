import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.database import Base, engine
from backend.app.api.health import router as health_router
from backend.app.api.chat import router as chat_router, get_rag_service
from backend.app.api.auth import router as auth_router
from backend.app.api.memory_routes import router as memory_router

import os

# Ensure data directory exists for logs
os.makedirs("data", exist_ok=True)

# Configure logging
log_format = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(
    level=logging.INFO, 
    format=log_format,
    handlers=[
        logging.FileHandler("data/debug.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("travel_agent_main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler to initialize database schema, pre-warm RAG service and embedding models."""
    logger.info("Initializing database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully!")
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}")

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
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(memory_router, prefix=settings.API_V1_STR)


