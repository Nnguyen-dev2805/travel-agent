"""Per-module schema registry for the shared local application store.

Per ADR 0004 this module is the only place that owns `PRAGMA user_version` and
the `schema_versions` table. Product modules ask it to open the shared database
and to register their own schema version; they never negotiate versions with
each other.

Two safety rules define the behavior:

1. **The pragma is a store marker, not a version count.** A fresh file receives
   `SENTINEL_USER_VERSION`. Any other non-zero value means the file belongs to a
   build this one does not understand, including the value `1` that a pre-R4
   workspace build writes. Such a file fails closed and is never migrated
   automatically, so an older build refuses an R4 database instead of writing
   into a schema it cannot read.
2. **A recorded module version must match exactly.** R4 ships no migration
   framework, so a recorded version above or below the requested one fails
   closed rather than guessing a migration path.

Raised `SchemaRegistryError` messages are safe for a controlled HTTP 500
response: they never include the local database path, full SQL text,
credentials, or user content.

This module depends on the Python standard library only.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Callable

logger = logging.getLogger("travel_agent_storage")

SENTINEL_USER_VERSION = 1000
"""Marker written to `PRAGMA user_version` by an R4 or later build.

The value must differ from `0`, which SQLite reports for an uninitialized file,
and from `1`, which a pre-R4 workspace build expects. A value far from any
plausible sequential schema number keeps it self-evidently a marker rather than
a count when a developer inspects the database by hand.
"""

REGISTRY_TABLE = "schema_versions"

_CREATE_REGISTRY_TABLE = f"""
CREATE TABLE IF NOT EXISTS {REGISTRY_TABLE} (
    module  TEXT PRIMARY KEY,
    version INTEGER NOT NULL
)
"""

_SELECT_MODULE_VERSION = f"SELECT version FROM {REGISTRY_TABLE} WHERE module = ?"

_INSERT_MODULE_VERSION = f"INSERT INTO {REGISTRY_TABLE} (module, version) VALUES (?, ?)"


class SchemaRegistryError(Exception):
    """The shared application store could not be opened or version-checked.

    Messages raised as this type are safe for a controlled HTTP 500 response.
    They must not carry local filesystem paths, full SQL text, credentials, or
    user content.
    """


def open_application_database(db_path: Path) -> sqlite3.Connection:
    """Open the shared application database and ensure the registry exists.

    Creates the parent directory when absent, enforces the sentinel ownership
    rule, and creates `schema_versions` when it is missing. The caller owns the
    returned connection and must close it.

    Raises:
        SchemaRegistryError: The parent directory cannot be created, the
            database cannot be opened, the registry cannot be initialized, or
            the file carries an unrecognized store marker.
    """
    path = Path(db_path)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise SchemaRegistryError(
            "Could not create the local application database directory."
        ) from error

    try:
        connection = sqlite3.connect(path)
    except sqlite3.Error as error:
        raise SchemaRegistryError(
            "Could not open the local application database."
        ) from error

    try:
        with connection:
            observed = connection.execute("PRAGMA user_version").fetchone()[0]

            if observed == 0:
                connection.execute(_CREATE_REGISTRY_TABLE)
                connection.execute(f"PRAGMA user_version = {SENTINEL_USER_VERSION}")
                logger.info(
                    "Initialized the shared application schema registry with store "
                    "marker %s.",
                    SENTINEL_USER_VERSION,
                )
            elif observed == SENTINEL_USER_VERSION:
                connection.execute(_CREATE_REGISTRY_TABLE)
            else:
                raise SchemaRegistryError(
                    f"The local application database reports store marker {observed}, "
                    f"but this build recognizes marker {SENTINEL_USER_VERSION}. "
                    "Refusing to migrate automatically."
                )
    except sqlite3.Error as error:
        connection.close()
        raise SchemaRegistryError(
            "Could not initialize the local application schema registry."
        ) from error
    except SchemaRegistryError:
        connection.close()
        raise

    return connection


def register_module_schema(
    connection: sqlite3.Connection,
    module: str,
    version: int,
    create: Callable[[sqlite3.Connection], None],
) -> None:
    """Create a module's schema on first use, or verify its recorded version.

    On first registration the `create` callback runs and the version is
    recorded, both inside one transaction, so a partially created schema is
    never recorded as complete. A matching recorded version is accepted without
    re-running `create`. Any mismatch fails closed.

    Raises:
        SchemaRegistryError: The recorded version differs from `version`, or the
            schema could not be created or recorded.
    """
    try:
        with connection:
            recorded = _select_module_version(connection, module)

            if recorded is None:
                create(connection)
                connection.execute(_INSERT_MODULE_VERSION, (module, version))
                logger.info(
                    "Registered schema module %s at version %s.", module, version
                )
                return

            if recorded != version:
                raise SchemaRegistryError(
                    f"Schema module '{module}' is recorded at version {recorded}, "
                    f"but this build supports version {version}. "
                    "Refusing to migrate automatically."
                )
    except sqlite3.Error as error:
        raise SchemaRegistryError(
            f"Could not register the schema for module '{module}'."
        ) from error


def read_module_version(connection: sqlite3.Connection, module: str) -> int | None:
    """Return the recorded schema version for a module, or None when absent.

    Raises:
        SchemaRegistryError: The registry could not be read.
    """
    try:
        return _select_module_version(connection, module)
    except sqlite3.Error as error:
        raise SchemaRegistryError(
            f"Could not read the recorded schema version for module '{module}'."
        ) from error


def _select_module_version(connection: sqlite3.Connection, module: str) -> int | None:
    row = connection.execute(_SELECT_MODULE_VERSION, (module,)).fetchone()
    return None if row is None else int(row[0])
