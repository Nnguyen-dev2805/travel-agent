"""Target architecture boundary tests (clean-break sentinel).

Governed by:
- ADR 0018: Authenticated Chat-Only Product Container
- ADR 0019: PostgreSQL-Only Application Persistence & SQLite Retirement
- ADR 0020: Removal of Public Memory Management Surface
- ADR 0021: Standalone Conversation Ownership & Auto-Create
- ADR 0022: Clean-Break Migration, Data Disposal & Rollback Policy
- Specification: docs/specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md

These static and runtime boundary tests act as sentinels ensuring:
1. No SQLite or schema-registry imports exist in mounted backend code.
2. No workspaces, planner, or legacy memory imports exist in mounted backend code.
3. Legacy configuration options (APP_DB_PATH, WORKSPACE_DB_PATH, AUTH_REQUIRED) are removed.
4. Only approved routes are mounted in FastAPI application.
5. require_principal has no compatibility fallback mode.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Tuple

import pytest
from fastapi import HTTPException
from starlette.requests import Request

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_ROOT.parent

# Mounted backend packages under the clean-break target architecture
MOUNTED_BACKEND_DIRS = [
    BACKEND_ROOT / "app",
    BACKEND_ROOT / "conversations",
    BACKEND_ROOT / "observability",
    BACKEND_ROOT / "security",
    BACKEND_ROOT / "storage",
]

# Mounted backend packages for legacy domain check (includes retained memory write_pipeline)
MOUNTED_BACKEND_DIRS_WITH_MEMORY = [
    *MOUNTED_BACKEND_DIRS,
    BACKEND_ROOT / "memory" / "write_pipeline",
]


def _collect_py_files(directories: list[Path]) -> list[Path]:
    py_files: list[Path] = []
    for d in directories:
        if d.is_dir():
            py_files.extend(sorted(d.rglob("*.py")))
        elif d.is_file() and d.suffix == ".py":
            py_files.append(d)
    return py_files


def _scan_imports(py_file: Path) -> list[tuple[int, str, str]]:
    """Return list of (lineno, module, imported_symbol) for all imports in a Python file."""
    try:
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))
    except Exception as e:
        pytest.fail(f"Failed to parse AST for {py_file}: {e}")

    imports: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno, alias.name, ""))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append((node.lineno, module, alias.name))
    return imports


def test_no_sqlite_imports_in_mounted_backend():
    """Verify that no mounted backend module imports sqlite3, schema_registry, or any SQLite adapter.

    Per ADR 0019, PostgreSQL is the sole application store. SQLite adapters and
    the SQLite schema registry must not be imported anywhere in mounted backend code.
    """
    violations: list[str] = []
    py_files = _collect_py_files(MOUNTED_BACKEND_DIRS)

    for py_file in py_files:
        rel_path = py_file.relative_to(REPO_ROOT)
        for lineno, module, symbol in _scan_imports(py_file):
            mod_parts = module.split(".")

            # Check sqlite3 standard library import
            if module == "sqlite3" or module.startswith("sqlite3.") or symbol == "sqlite3":
                violations.append(f"{rel_path}:{lineno} imports sqlite3 ({module or symbol})")
                continue

            # Check schema_registry import
            if "schema_registry" in mod_parts or symbol == "schema_registry":
                violations.append(f"{rel_path}:{lineno} imports schema_registry ({module}.{symbol})")
                continue

            # Check sqlite_repository or SQLite repository adapter import
            if "sqlite_repository" in mod_parts or symbol == "sqlite_repository":
                violations.append(f"{rel_path}:{lineno} imports sqlite_repository ({module}.{symbol})")
                continue

            if "sqlite" in module.lower() or "sqlite" in symbol.lower():
                violations.append(f"{rel_path}:{lineno} imports SQLite adapter symbol ({module}.{symbol})")
                continue

    assert not violations, (
        f"Found {len(violations)} forbidden SQLite / schema_registry imports in mounted backend:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_no_workspace_or_planner_or_legacy_memory_imports():
    """Verify that no mounted backend module imports workspaces, planner, or legacy memory.

    Per ADR 0018 & ADR 0020, Workspace, Planner, and legacy Memory surfaces are removed.
    The only allowed memory module is backend.memory.write_pipeline.
    """
    violations: list[str] = []
    py_files = _collect_py_files(MOUNTED_BACKEND_DIRS_WITH_MEMORY)

    for py_file in py_files:
        rel_path = py_file.relative_to(REPO_ROOT)
        for lineno, module, symbol in _scan_imports(py_file):
            mod_parts = module.split(".")

            # Check workspaces import
            if "workspaces" in mod_parts or symbol == "workspaces":
                violations.append(f"{rel_path}:{lineno} imports workspaces ({module}.{symbol})")
                continue

            # Check planner import
            if "planner" in mod_parts or symbol == "planner":
                violations.append(f"{rel_path}:{lineno} imports planner ({module}.{symbol})")
                continue

            # Check legacy memory imports (anything with memory / memory_controls not in write_pipeline)
            if "memory" in mod_parts or "memory_controls" in mod_parts or symbol in ("memory", "memory_controls"):
                # Exception: backend.memory.write_pipeline (and submodules) is the approved write pipeline
                if module == "backend.memory.write_pipeline" or module.startswith("backend.memory.write_pipeline."):
                    continue
                violations.append(f"{rel_path}:{lineno} imports legacy memory ({module}.{symbol})")

    assert not violations, (
        f"Found {len(violations)} forbidden workspace/planner/legacy-memory imports in mounted backend:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_no_legacy_config_options():
    """Verify that APP_DB_PATH, WORKSPACE_DB_PATH, and AUTH_REQUIRED do not exist in backend/app/config.py.

    Per ADR 0018 and ADR 0019, SQLite configuration and authentication compatibility flag
    must not appear in production settings.
    """
    from backend.app.config import Settings, settings

    forbidden_options = ["APP_DB_PATH", "WORKSPACE_DB_PATH", "AUTH_REQUIRED"]
    violations: list[str] = []

    # Check Settings model fields
    for opt in forbidden_options:
        if opt in Settings.model_fields:
            violations.append(f"Settings.model_fields contains '{opt}'")
        if hasattr(settings, opt):
            violations.append(f"settings instance has attribute '{opt}'")

    # AST check on config.py source
    config_py = BACKEND_ROOT / "app" / "config.py"
    tree = ast.parse(config_py.read_text(encoding="utf-8"), filename=str(config_py))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in forbidden_options:
                    violations.append(f"config.py:{node.lineno} defines variable '{target.id}'")

    assert not violations, (
        f"Found {len(violations)} forbidden legacy config options in backend/app/config.py:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_only_approved_routes_mounted():
    """Verify that backend/app/main.py mounts ONLY the approved 8 routes.

    Approved routes per ADR 0018:
    - GET /health
    - GET /api/v1/ops/readiness
    - POST /api/v1/chat
    - POST /api/v1/conversations
    - GET /api/v1/conversations
    - GET /api/v1/conversations/{conversation_id}
    - GET /api/v1/conversations/{conversation_id}/messages
    - DELETE /api/v1/conversations/{conversation_id}

    No /workspaces, /planner, /memory, or /memory/controls routes may be mounted.
    """
    from backend.app.main import app

    approved_routes = {
        ("GET", "/health"),
        ("GET", "/api/v1/ops/readiness"),
        ("POST", "/api/v1/chat"),
        ("POST", "/api/v1/conversations"),
        ("GET", "/api/v1/conversations"),
        ("GET", "/api/v1/conversations/{conversation_id}"),
        ("GET", "/api/v1/conversations/{conversation_id}/messages"),
        ("DELETE", "/api/v1/conversations/{conversation_id}"),
    }

    openapi = app.openapi()
    mounted_routes: set[tuple[str, str]] = set()
    for path, path_item in openapi.get("paths", {}).items():
        for method in path_item.keys():
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                mounted_routes.add((method.upper(), path))

    # Check for forbidden prefix routes
    forbidden_segments = ("/workspaces", "/planner", "/memory", "/memory/controls")
    forbidden_mounted = [
        f"{m} {p}" for m, p in sorted(mounted_routes)
        if any(seg in p for seg in forbidden_segments)
    ]
    assert not forbidden_mounted, (
        f"Found forbidden routes mounted on FastAPI app:\n"
        + "\n".join(f"  - {r}" for r in forbidden_mounted)
    )

    # Check exact equality with approved routes
    missing_routes = approved_routes - mounted_routes
    unexpected_routes = mounted_routes - approved_routes

    assert mounted_routes == approved_routes, (
        f"Mounted routes do not match approved clean-break route set.\n"
        f"Missing approved routes ({len(missing_routes)}):\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
        + f"\nUnexpected mounted routes ({len(unexpected_routes)}):\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(unexpected_routes))
    )


def test_require_principal_has_no_compatibility_mode():
    """Verify that require_principal in backend/security/dependencies.py has no compatibility mode.

    Per ADR 0018, authentication is unconditional. require_principal must never check
    AUTH_REQUIRED or fall back to AuthMode.COMPATIBILITY or a compatibility principal.
    """
    from backend.security.dependencies import require_principal

    # 1. AST check: require_principal must not reference AUTH_REQUIRED or COMPATIBILITY
    deps_file = BACKEND_ROOT / "security" / "dependencies.py"
    tree = ast.parse(deps_file.read_text(encoding="utf-8"), filename=str(deps_file))

    require_principal_node: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "require_principal":
            require_principal_node = node
            break

    assert require_principal_node is not None, "require_principal function definition not found in dependencies.py"

    forbidden_terms = {"AUTH_REQUIRED", "COMPATIBILITY", "COMPATIBILITY_OWNER_ID", "_compatibility_principal"}
    found_forbidden: list[str] = []

    for child in ast.walk(require_principal_node):
        if isinstance(child, ast.Name) and child.id in forbidden_terms:
            found_forbidden.append(f"line {child.lineno}: references '{child.id}'")
        elif isinstance(child, ast.Attribute) and child.attr in forbidden_terms:
            found_forbidden.append(f"line {child.lineno}: references attribute '{child.attr}'")

    assert not found_forbidden, (
        f"require_principal contains legacy compatibility mode references:\n"
        + "\n".join(f"  - {f}" for f in found_forbidden)
    )

    # 2. Runtime check: Calling require_principal without credentials must raise 401,
    # and must never return a compatibility principal.
    req = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as exc_info:
        principal = require_principal(req)
        # If it didn't raise, fail explicitly with the principal details
        pytest.fail(f"require_principal returned principal without auth: {principal}")

    assert exc_info.value.status_code == 401, f"Expected 401 Unauthorized, got {exc_info.value.status_code}"
