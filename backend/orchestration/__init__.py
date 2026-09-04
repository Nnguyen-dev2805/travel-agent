"""Orchestration module for runtime milestone R4.

Per ADR 0005 this package owns coordination between product modules for one
request. It receives the first `ConversationOrchestrator`, which the chat route
delegates to so neither the route handler nor the RAG module gains the other's
responsibility.

Dependencies run one way: orchestration depends on conversations and on an
injected RAG facade, and nothing depends on orchestration except the chat route.
`backend/rag`, the evaluation harness, and `backend/workspaces` must never import
this package.
"""

from backend.orchestration.conversation_orchestrator import (
    DEFAULT_TOP_K,
    ConversationOrchestrator,
    TurnOutcome,
    TurnPersistence,
)

__all__ = [
    "DEFAULT_TOP_K",
    "ConversationOrchestrator",
    "TurnOutcome",
    "TurnPersistence",
]
