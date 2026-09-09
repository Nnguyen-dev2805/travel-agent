"""FastAPI routes for risk-based memory user controls.

Confirm-all is superseded: explicit low-risk commands commit directly
and report application-owned outcomes only after commit, while bulk
delete and scope expansion commit through bounded one-time preview
tokens. Cross-owner identifiers report a miss without disclosing
existence, mirroring existing route patterns.

Logging records route, action, identifiers, reason codes, counts, and
failure class only. Utterances, display text, and secrets never enter
logs, and HTTP bodies never echo them.
"""

import logging
from functools import partial
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.config import settings
from backend.app.schemas.memory_controls import (
    MemoryCommandRequest,
    MemoryCommandResponse,
    MemoryConfirmRequest,
    MemoryDeletionRequest,
    MemoryEntryResponse,
    MemoryExpansionRequest,
    MemoryListResponse,
    PreviewPayloadResponse,
    PreviewTargetResponse,
    UndoDescriptorResponse,
)
from backend.memory.write_pipeline.postgres import (
    PostgresMemoryUnitOfWork,
    pg_commit_bulk_delete,
    pg_commit_delete_one,
    pg_list_active_versions,
    read_current_versions,
)
from backend.memory.write_pipeline.service import (
    BulkCommitted,
    DeletedEvent,
    HeldEvent,
    MemoryCommandNotFoundError,
    MemoryCommandService,
    MemoryCommandStaleError,
    MemoryCommandValidationError,
    PendingEvent,
    PreviewOffer,
    RefusedEvent,
    SavedEvent,
    ToggledEvent,
)
from backend.memory.write_pipeline.uow import (
    ConcurrentWriteError,
    CrossOwnerDeniedError,
    MemoryWriteError,
    StaleVersionError,
)
from backend.security.dependencies import require_principal
from backend.security.models import AuthenticatedPrincipal
from backend.storage.postgres import create_engine

logger = logging.getLogger("travel_agent_memory_controls")
router = APIRouter()

_NOT_FOUND_DETAIL = "Memory not found."
_PREVIEW_GONE_DETAIL = "Memory preview not found or expired."
_STALE_DETAIL = "Memory changed; please review again."
_STORAGE_ERROR_DETAIL = "Memory storage is unavailable."

_engine = None
_command_service = None


def get_command_service() -> MemoryCommandService:
    """Construct the command service over PostgreSQL, once per process.

    Both the engine and command service are process-scoped so that
    connection pools and bounded in-memory preview state persist
    across requests within the process. Tests override this dependency
    with isolated wiring instead.
    """
    global _engine, _command_service
    if _command_service is None:
        if _engine is None:
            from backend.app.config import pg_dsn

            _engine = create_engine(
                pg_dsn(
                    settings.PG_PASSWORD.get_secret_value(),
                    settings.PG_HOST,
                    settings.PG_PORT,
                    settings.PG_DB,
                    settings.PG_USER,
                )
            )
        uow = PostgresMemoryUnitOfWork(_engine)
        _command_service = MemoryCommandService(
            uow=uow,
            read_versions=lambda identity: read_current_versions(_engine, identity),
            list_active_versions=partial(pg_list_active_versions, _engine),
            commit_delete_one=partial(pg_commit_delete_one, _engine),
            commit_bulk_delete=partial(pg_commit_bulk_delete, _engine),
        )
    return _command_service


def _undo_response(undo) -> UndoDescriptorResponse:
    return UndoDescriptorResponse(
        action=undo.action,
        version_ids=list(undo.version_ids),
        note=undo.note,
    )


def _preview_response(offer: PreviewOffer) -> PreviewPayloadResponse:
    return PreviewPayloadResponse(
        preview_id=offer.preview_id,
        token=offer.token,
        operation=offer.display.operation,
        targets=[
            PreviewTargetResponse(
                version_id=item.version_id,
                canonical_key=item.canonical_key,
                normalized_value=item.normalized_value,
                scope=item.scope,
                old_scope=item.old_scope,
                new_scope=item.new_scope,
            )
            for item in offer.display.targets
        ],
        expires_in_seconds=offer.display.expires_in_seconds,
    )


def _command_response(result) -> MemoryCommandResponse:
    if isinstance(result, SavedEvent):
        return MemoryCommandResponse(
            status="saved",
            operation=result.operation,
            scope=result.scope,
            canonical_key=result.canonical_key,
            normalized_value=result.normalized_value,
            version_id=result.version_id,
        )
    if isinstance(result, DeletedEvent):
        return MemoryCommandResponse(
            status="deleted",
            committed_version_ids=list(result.deleted_version_ids),
            undo=_undo_response(result.undo),
        )
    if isinstance(result, BulkCommitted):
        return MemoryCommandResponse(
            status="committed",
            operation=result.operation,
            committed_version_ids=list(result.committed_version_ids),
            undo=_undo_response(result.undo),
        )
    if isinstance(result, ToggledEvent):
        return MemoryCommandResponse(
            status="toggled",
            operation=result.action,
            persistent=result.persistent,
            note=result.note,
            undo=_undo_response(result.undo),
        )
    if isinstance(result, HeldEvent):
        return MemoryCommandResponse(status="held", reason_code=result.reason)
    if isinstance(result, PendingEvent):
        return MemoryCommandResponse(status="pending", reason_code=result.reason)
    if isinstance(result, RefusedEvent):
        return MemoryCommandResponse(status="refused", reason_code=result.reason)
    if isinstance(result, PreviewOffer):
        return MemoryCommandResponse(
            status="preview_required", preview=_preview_response(result)
        )
    raise MemoryWriteError("The memory command produced an unknown outcome.")


@router.post("/memory/controls/commands", response_model=MemoryCommandResponse)
def handle_command(
    request: MemoryCommandRequest,
    service: MemoryCommandService = Depends(get_command_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> MemoryCommandResponse:
    """Handle one NL memory utterance under risk-based rules."""
    try:
        result = service.handle_utterance(
            principal,
            request.utterance,
            conversation_id=request.conversation_id,
            scope=request.scope,
            idempotency_key=request.idempotency_key,
        )
    except MemoryCommandValidationError as error:
        logger.info("memory.command rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except CrossOwnerDeniedError:
        logger.info("memory.command miss failure_class=cross_owner")
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    except (MemoryCommandStaleError, StaleVersionError, ConcurrentWriteError) as error:
        logger.info("memory.command conflict failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=409, detail=_STALE_DETAIL) from error
    except MemoryCommandNotFoundError as error:
        logger.info("memory.command miss failure_class=not_found")
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from error
    except MemoryWriteError as error:
        logger.error("memory.command failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    if isinstance(result, (SavedEvent, DeletedEvent, BulkCommitted)):
        logger.info(
            "memory.command ok status=%s operation=%s",
            "committed",
            getattr(result, "operation", "delete"),
        )
    else:
        logger.info(
            "memory.command ok status=%s",
            getattr(result, "action", type(result).__name__),
        )
    return _command_response(result)


@router.get("/memory/controls/memories", response_model=MemoryListResponse)
def list_memories(
    scope: Optional[str] = Query(None, description="Filter to one scope"),
    service: MemoryCommandService = Depends(get_command_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> MemoryListResponse:
    """List one owner's active memories in governed vocabulary only."""
    versions = service.list_memories(principal, scope)
    logger.info(
        "memory.controls.list ok owner_count=%s",
        len(versions),
    )
    return MemoryListResponse(
        memories=[
            MemoryEntryResponse(
                version_id=item.version_id,
                canonical_key=item.canonical_key,
                normalized_value=item.normalized_value,
                scope=item.scope.value,
                authority=item.authority.value,
                sensitivity=item.sensitivity.value,
                valid_from=item.valid_from,
            )
            for item in versions
        ]
    )


@router.post("/memory/controls/deletions", response_model=MemoryCommandResponse)
def delete_memories(
    request: MemoryDeletionRequest,
    service: MemoryCommandService = Depends(get_command_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> MemoryCommandResponse:
    """Delete one version directly, or open a preview for many."""
    try:
        result = service.delete_versions(principal, request.version_ids)
    except MemoryCommandValidationError as error:
        logger.info("memory.controls.delete rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MemoryCommandNotFoundError:
        logger.info("memory.controls.delete miss failure_class=not_found")
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    except (MemoryCommandStaleError, StaleVersionError, ConcurrentWriteError) as error:
        logger.info(
            "memory.controls.delete conflict failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=409, detail=_STALE_DETAIL) from error
    except CrossOwnerDeniedError:
        logger.info("memory.controls.delete miss failure_class=cross_owner")
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    except MemoryWriteError as error:
        logger.error(
            "memory.controls.delete failed failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info("memory.controls.delete ok")
    return _command_response(result)


@router.post("/memory/controls/expansions", response_model=MemoryCommandResponse)
def expand_scope(
    request: MemoryExpansionRequest,
    service: MemoryCommandService = Depends(get_command_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> MemoryCommandResponse:
    """Open a scoped preview widening one conversation version to user."""
    try:
        result = service.preview_scope_expansion(principal, request.version_id)
    except MemoryCommandValidationError as error:
        logger.info("memory.controls.expand rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MemoryCommandNotFoundError:
        logger.info("memory.controls.expand miss failure_class=not_found")
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    except CrossOwnerDeniedError:
        logger.info("memory.controls.expand miss failure_class=cross_owner")
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    except MemoryWriteError as error:
        logger.error(
            "memory.controls.expand failed failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info("memory.controls.expand ok")
    return _command_response(result)


@router.post("/memory/controls/confirmations", response_model=MemoryCommandResponse)
def confirm_preview(
    request: MemoryConfirmRequest,
    service: MemoryCommandService = Depends(get_command_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> MemoryCommandResponse:
    """Confirm one pending preview after full revalidation, exactly once."""
    try:
        result = service.confirm_preview(principal, request.preview_id, request.token)
    except MemoryCommandValidationError as error:
        logger.info("memory.controls.confirm rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MemoryCommandNotFoundError:
        logger.info("memory.controls.confirm miss failure_class=preview_gone")
        raise HTTPException(status_code=404, detail=_PREVIEW_GONE_DETAIL)
    except (MemoryCommandStaleError, StaleVersionError, ConcurrentWriteError) as error:
        logger.info(
            "memory.controls.confirm conflict failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=409, detail=_STALE_DETAIL) from error
    except CrossOwnerDeniedError:
        logger.info("memory.controls.confirm miss failure_class=cross_owner")
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    except MemoryWriteError as error:
        logger.error(
            "memory.controls.confirm failed failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info("memory.controls.confirm ok")
    return _command_response(result)
