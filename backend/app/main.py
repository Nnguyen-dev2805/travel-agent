import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.app.config import assert_credential_isolation, settings
from backend.app.runtime_container import RuntimeContainer
from backend.app.errors import content_free_validation_error_handler
from backend.security.dependencies import (
    enforce_authentication,
    enforce_request_body_limit,
    resolve_cors_origins,
)
from backend.security.models import SecurityConfigurationError
from backend.observability.context import (
    current_request_id,
    reset_request_id,
    set_request_id,
)
from backend.observability.events import emit_event
from backend.observability.models import (
    EventComponent,
    EventName,
    EventResult,
    EventSeverity,
    generate_request_id,
)
from backend.app.api.health import router as health_router
from backend.app.api.ops import router as ops_router
from backend.app.api.chat import router as chat_router
from backend.app.api.conversations import router as conversations_router

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("travel_agent_main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler initializing container and pre-warming services."""
    # ADR 0034, as the first statement: a leaked credential must stop the process
    # before any connection is attempted, so the failure names the environment
    # rather than surfacing later as a request served by the wrong role. Placed
    # here and not in `RuntimeContainer.__init__`, so constructing a container in
    # a test does not require a curated environment.
    assert_credential_isolation("api")
    container = RuntimeContainer(settings)
    await container.startup()
    app.state.container = container
    logger.info("RuntimeContainer initialized and bound to app.state.container")

    logger.info("Pre-warming RAG Service and embedding model on server boot...")
    try:
        # Pre-warm the SAME instance the request path uses, so the container's
        # RAG service is constructed once rather than a second detached copy — and
        # then *actually* load the embedding weights. Constructing the object graph
        # alone left `VectorEmbedder.model` unloaded, so the previous success line
        # was untrue and the first user query paid for a multi-gigabyte checkpoint.
        container.rag_service().warm()
        logger.info("RAG Service and embedding model pre-warmed.")
    except Exception as error:  # noqa: BLE001 - a pre-warm must not stop startup
        # `failure_class`, never `str(error)`: this is the one startup log that used
        # to carry raw exception text, and an exception from an SDK or a provider can
        # hold an endpoint, a path or a response body. The rest of the repository
        # already reports a class.
        logger.warning(
            "rag.prewarm failed failure_class=%s", type(error).__name__
        )

    try:
        yield
    finally:
        logger.info("Shutting down application and disposing RuntimeContainer...")
        await container.shutdown()


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


async def _unhandled_exception_handler(request: Request, error: Exception):
    """Return a content-free 500 correlated with the request id.

    Only truly unhandled exceptions reach here: `HTTPException` keeps its
    controlled body through Starlette's own handler, and the validation
    handler above keeps schema rejections. The id comes from the request
    scope stashed by the correlation middleware, because that middleware
    already reset its context by the time this outer layer runs; the
    context and a fresh id are fallbacks only. Raw exception text, paths,
    SQL, prompts, and user content never enter the response.
    """
    scoped = request.scope.get("r9.request_id")
    if not isinstance(scoped, str) or not scoped.startswith("rq_"):
        scoped = None
    request_id = scoped or current_request_id() or generate_request_id()
    logger.error(
        "app.unhandled failure_class=%s request_id=%s",
        type(error).__name__,
        request_id,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error.", "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


app.add_exception_handler(Exception, _unhandled_exception_handler)

# CORS is registered *after* the middleware below so that it wraps it. See the
# comment on that registration: the order is load-bearing.


@app.middleware("http")
async def request_correlation_middleware(request: Request, call_next):
    """Authenticate, bind a server-owned request id, and emit one event.

    Authentication is evaluated here, ahead of routing and therefore ahead of
    request-body parsing, so an unauthenticated request is refused with `401`
    whether or not its body parses. A route dependency cannot achieve that:
    FastAPI reads and parses the body before it solves dependencies, so a
    malformed body produced `422` before the authentication decision ran
    (ADR 0026).

    The id travels in the `X-Request-ID` response header for local
    correlation only; it is never an authentication token. Every exit path
    emits exactly one completion event carrying method, path, status code, and
    duration inside counters: bodies and query strings are never logged.
    `request.url.path` may hold governed resource identifiers, which are safe
    event fields, but never message content. Observability failures must not
    break the response, so emission errors stay inside this middleware.
    """
    request_id = generate_request_id()
    token = set_request_id(request_id)
    # Stash the id on the request scope as well: the exception
    # middleware outside this layer handles unhandled failures after this
    # context is reset, so the safe-500 handler reads it back from here
    # to keep one id across the completion event, the header, and the
    # response body.
    request.scope["r9.request_id"] = request_id
    start = time.perf_counter()
    try:
        # Authentication first, so an unauthenticated request is refused
        # without its body being read.
        response = enforce_authentication(request)
        if response is None:
            try:
                response = await enforce_request_body_limit(request)
            except SecurityConfigurationError as error:
                logger.error(
                    "security.request rejected failure_class=%s",
                    type(error).__name__,
                )
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "Request rejected.", "request_id": request_id},
                )
        if response is None:
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
    # One tail for every exit, including the early rejections. Previously the
    # `413` and the configuration-`500` returned before this point and emitted
    # nothing, so neither appeared in the event stream at all.
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


# Configure CORS middleware. Origin resolution fails closed at startup when
# auth is enabled with a wildcard origin; otherwise the configured local
# origins apply. Authentication is unconditional (no compatibility mode).
#
# This must be registered LAST: Starlette inserts each middleware at position 0
# and therefore builds the stack with the most recently registered layer
# outermost. Registered here, CORS wraps the correlation middleware, so an early
# `401`, `413`, or configuration-`500` returned from it still passes through
# CORS and carries `Access-Control-Allow-Origin`. Register it earlier and a
# browser sees an opaque network error instead of the status, and a preflight
# `OPTIONS` is answered `401` before it is handled.
app.add_middleware(
    CORSMiddleware,
    allow_origins=resolve_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# Include Routers
app.include_router(health_router)
app.include_router(ops_router, prefix=settings.API_V1_STR)
app.include_router(chat_router, prefix=settings.API_V1_STR)
app.include_router(conversations_router, prefix=settings.API_V1_STR)
