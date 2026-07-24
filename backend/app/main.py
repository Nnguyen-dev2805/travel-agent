import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.api.health import router as health_router
from backend.app.api.chat import router as chat_router

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="FastAPI Backend for Travel Agent Chatbot",
    version=settings.VERSION,
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
