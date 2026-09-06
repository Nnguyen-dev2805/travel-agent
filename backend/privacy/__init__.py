"""Workspace deletion coordination for milestone R9.

This package owns the privacy deletion service and its result contracts.
"""

from backend.privacy.deletion import (
    DeletionConflictError,
    DeletionResult,
    DeletionService,
    PrivacyServiceError,
)

__all__ = [
    "DeletionConflictError",
    "DeletionResult",
    "DeletionService",
    "PrivacyServiceError",
]
