"""Request correlation context for milestone R8.

The current request id lives in a `ContextVar` so concurrent requests never
share correlation state. Ids are always server-generated; R8 never trusts or
persists caller-supplied request ids. This module uses only the standard
library plus observability models.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

from backend.observability.models import (
    REQUEST_ID_PREFIX,
    ObservabilityValidationError,
    generate_request_id,
)

_current_request_id: ContextVar[str | None] = ContextVar(
    "observability_request_id", default=None
)


def current_request_id() -> str | None:
    """Return the active request id, or `None` outside a request scope."""
    return _current_request_id.get()


def set_request_id(value: str) -> Token:
    """Bind one server-generated request id to the current context.

    Returns the reset token so middleware and tests can leave no state
    behind.
    """
    if not isinstance(value, str) or not value.startswith(REQUEST_ID_PREFIX):
        raise ObservabilityValidationError(
            "Observability request id must carry the governed prefix."
        )
    return _current_request_id.set(value)


def new_request_id() -> str:
    """Generate and bind a fresh server-owned request id."""
    request_id = generate_request_id()
    set_request_id(request_id)
    return request_id


def reset_request_id(token: Token) -> None:
    """Restore the request id state captured in `token`."""
    _current_request_id.reset(token)
