import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.errors import content_free_validation_error_handler
from backend.observability.context import reset_request_id, set_request_id
from backend.observability.events import emit_event
from backend.observability.models import (
    EventComponent,
    EventName,
    EventResult,
    EventSeverity,
    generate_request_id,
)
from backend.app.api.health import router as health_router
from backend.app.api.chat import router as chat_router, get_rag_service
from backend.app.api.workspaces import router as workspaces_router
from backend.app.api.conversations import router as conversations_router
from backend.app.api.memory import router as memory_router
from backend.app.api.ops import router as ops_router
from backend.app.api.planner import router as planner_router

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
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

# Answer request-schema rejections without echoing the submitted payload, so no
# error body can carry message content or a conversation title.
app.add_exception_handler(RequestValidationError, content_free_validation_error_handler)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_correlation_middleware(request: Request, call_next):
    """Bind a server-owned request id and emit a content-free event.

    The id travels in the `X-Request-ID` response header for local
    correlation only; it is never an authentication token. The completion
    event carries method, path, status code, and duration inside counters:
    bodies and query strings are never logged. `request.url.path` may hold
    governed resource identifiers, which are safe event fields, but never
    message content. Observability failures must not break the response,
    so emission errors stay inside this middleware.
    """
    request_id = generate_request_id()
    token = set_request_id(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as error:
        try:
            emit_event(
                EventName.API_REQUEST_COMPLETED,
                EventComponent.API,
                EventResult.FAILURE,
                counters={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                },
                failure_class=type(error).__name__,
                reason_code="unhandled_exception",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        finally:
            reset_request_id(token)
        raise
    status_code = response.status_code
    if status_code < 400:
        result, severity, reason = (
            EventResult.SUCCESS,
            EventSeverity.INFO,
            "ok",
        )
    elif status_code < 500:
        result, severity, reason = (
            EventResult.FAILURE,
            EventSeverity.WARNING,
            "http_client_error",
        )
    else:
        result, severity, reason = (
            EventResult.FAILURE,
            EventSeverity.ERROR,
            "http_server_error",
        )
    response.headers["X-Request-ID"] = request_id
    try:
        emit_event(
            EventName.API_REQUEST_COMPLETED,
            EventComponent.API,
            result,
            severity=severity,
            counters={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
            },
            reason_code=reason,
            duration_ms=(time.perf_counter() - start) * 1000,
        )
    except Exception as error:
        logger.warning(
            "observability.emit failed failure_class=%s", type(error).__name__
        )
    finally:
        reset_request_id(token)
    return response


# Include Routers
app.include_router(health_router)
app.include_router(chat_router, prefix=settings.API_V1_STR)
app.include_router(workspaces_router, prefix=settings.API_V1_STR)
app.include_router(conversations_router, prefix=settings.API_V1_STR)
app.include_router(memory_router, prefix=settings.API_V1_STR)
app.include_router(ops_router, prefix=settings.API_V1_STR)
app.include_router(planner_router, prefix=settings.API_V1_STR)
