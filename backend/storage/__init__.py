"""Shared local application store for the Travel Agent prototype.

Per ADR 0004 one local SQLite file holds every relational product record during
the prototype phase, and each module records its own schema version in a
`schema_versions` table instead of competing for the single
`PRAGMA user_version` slot that SQLite provides per file.

This package depends on the Python standard library only. It must never import
FastAPI, Pydantic, RAG, Chroma, a model provider, the evaluation subsystem, or
any product module, because every product module may depend on it.

SQLite is a local development adapter, not production storage readiness. This
package settles no production migration, backup, restore, concurrency,
retention, or deletion policy.
"""

from backend.storage.schema_registry import (
    SENTINEL_USER_VERSION,
    SchemaRegistryError,
    open_application_database,
    read_module_version,
    register_module_schema,
)

__all__ = [
    "SENTINEL_USER_VERSION",
    "SchemaRegistryError",
    "open_application_database",
    "read_module_version",
    "register_module_schema",
]
