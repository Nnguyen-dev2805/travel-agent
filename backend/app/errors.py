"""Content-free error responses for request validation failures.

The approved R4 design requires that no log line and no HTTP error body carries
message content, a conversation title, a database path, SQL text, or a credential
value. Domain rejections already satisfy this, because the conversation contracts
raise messages that name the violated rule instead of the offending value.

Request-schema rejections do not. FastAPI's default `RequestValidationError`
response reports the offending value under `input`, and some error types repeat it
under `ctx`. A wrong-typed `title` or `content` therefore echoes user content
straight back, and a caller could defeat the guarantee deliberately by placing
content in any field of the request body.

This handler keeps the status code, the `detail` list, and the diagnostic fields
`type`, `loc`, and `msg`, and drops `input` and `ctx`. No diagnostic value is
lost: for a vocabulary violation, `msg` already names the permitted values.

The handler is registered on the application, so chat and workspace payloads are
redacted by the same rule rather than by a route-specific exception.
"""

from typing import Any, Dict, List, Sequence

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

VALIDATION_ERROR_STATUS = 422
"""Unchanged from FastAPI's default validation status.

Written as a literal because the Starlette constant for this code was renamed and
the old name now emits a deprecation warning on import.
"""

SAFE_VALIDATION_ERROR_KEYS = ("type", "loc", "msg")
"""Fields kept from a validation error entry.

`input` and `ctx` are excluded because either can carry caller-submitted content.
"""


def redact_validation_errors(
    errors: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return validation error entries without any caller-submitted value."""
    return [
        {key: entry[key] for key in SAFE_VALIDATION_ERROR_KEYS if key in entry}
        for entry in errors
    ]


async def content_free_validation_error_handler(
    request: Request, exception: RequestValidationError
) -> JSONResponse:
    """Answer a schema rejection without echoing the submitted payload."""
    return JSONResponse(
        status_code=VALIDATION_ERROR_STATUS,
        content={
            "detail": jsonable_encoder(redact_validation_errors(exception.errors()))
        },
    )
