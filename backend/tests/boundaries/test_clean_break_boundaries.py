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
4. Only approved routes are mounted, and no route surface that `openapi()` cannot
   enumerate is mounted at all.
5. require_principal has no compatibility fallback mode, and authentication is
   enforced ahead of routing (ADR 0026).

The scan scope is **derived from the filesystem** rather than declared. A
hand-maintained package list is what previously left `orchestration`, `rag`,
`preprocessing` and `memory` unscanned — two of which are on the request path.
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

# The suite itself is excluded, so the sentinel does not scan its own fixtures
# or the probes its own tests plant.
_EXCLUDED_PACKAGE_DIRS = frozenset({"tests", "__pycache__"})


def _backend_packages() -> list[Path]:
    """Every package directory under `backend/`, except the suite itself.

    Derived rather than declared. A hand-maintained list is what previously left
    `orchestration`, `rag`, `preprocessing` and `memory` unscanned.

    A directory counts as a package when it contains Python files, **not** when
    it contains `__init__.py`: `backend/rag` is an implicit namespace package
    (PEP 420), so requiring the file would exclude the very package this scope
    exists to cover.
    """
    return sorted(
        child
        for child in BACKEND_ROOT.iterdir()
        if child.is_dir()
        and child.name not in _EXCLUDED_PACKAGE_DIRS
        and next(child.rglob("*.py"), None) is not None
    )


# The approved product surface. A new route requires a specification and an
# approved plan (`AGENTS.md`), so adding one is a deliberate edit here rather
# than an omission nothing can see.
APPROVED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/health"),
        ("GET", "/api/v1/ops/readiness"),
        ("POST", "/api/v1/chat"),
        ("POST", "/api/v1/conversations"),
        ("GET", "/api/v1/conversations"),
        ("GET", "/api/v1/conversations/{conversation_id}"),
        ("GET", "/api/v1/conversations/{conversation_id}/messages"),
        ("DELETE", "/api/v1/conversations/{conversation_id}"),
    }
)


def _collect_py_files(directories: list[Path]) -> list[Path]:
    py_files: list[Path] = []
    for d in directories:
        if d.is_dir():
            py_files.extend(sorted(d.rglob("*.py")))
        elif d.is_file() and d.suffix == ".py":
            py_files.append(d)
    return py_files


def _relative(py_file: Path) -> Path:
    """Path relative to the repository when possible, for readable messages."""
    try:
        return py_file.relative_to(REPO_ROOT)
    except ValueError:
        return py_file


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


# The one narrow exception: this module may open Chroma's store file read-only.
_SQLITE_EXCEPTION_PATH = "backend/observability/readiness.py"


def _sqlite_violations(packages: list[Path] | None = None) -> list[str]:
    """Forbidden SQLite / schema-registry imports across the given packages.

    Defaults to every backend package. Accepting an explicit list lets a test
    plant a violation in a temporary tree and assert it is reported, without
    writing anything into the repository.
    """
    violations: list[str] = []
    targets = _backend_packages() if packages is None else packages

    for py_file in _collect_py_files(targets):
        rel_path = _relative(py_file)
        for lineno, module, symbol in _scan_imports(py_file):
            mod_parts = module.split(".")

            # Check sqlite3 standard library import
            if (
                module == "sqlite3"
                or module.startswith("sqlite3.")
                or symbol == "sqlite3"
            ):
                if rel_path.as_posix() == _SQLITE_EXCEPTION_PATH:
                    continue
                violations.append(
                    f"{rel_path}:{lineno} imports sqlite3 ({module or symbol})"
                )
                continue

            # Check schema_registry import
            if "schema_registry" in mod_parts or symbol == "schema_registry":
                violations.append(
                    f"{rel_path}:{lineno} imports schema_registry ({module}.{symbol})"
                )
                continue

            # Check sqlite_repository or SQLite repository adapter import
            if "sqlite_repository" in mod_parts or symbol == "sqlite_repository":
                violations.append(
                    f"{rel_path}:{lineno} imports sqlite_repository ({module}.{symbol})"
                )
                continue

            if "sqlite" in module.lower() or "sqlite" in symbol.lower():
                violations.append(
                    f"{rel_path}:{lineno} imports SQLite adapter symbol ({module}.{symbol})"
                )
                continue

    return violations


def test_no_sqlite_imports_in_mounted_backend():
    """Verify that no mounted backend module imports sqlite3, schema_registry, or any SQLite adapter.

    Per ADR 0019, PostgreSQL is the sole application store. SQLite adapters and
    the SQLite schema registry must not be imported anywhere in mounted backend code.

    Narrow exception: `backend/observability/readiness.py` may import the
    stdlib `sqlite3` module solely to open Chroma's store file in immutable
    read-only mode (`mode=ro`) for the index probe. It must never use SQLite
    as application storage; `test_readiness_sqlite_access_is_read_only`
    pins that contract.
    """
    violations = _sqlite_violations()

    assert not violations, (
        f"Found {len(violations)} forbidden SQLite / schema_registry imports in mounted backend:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_readiness_sqlite_access_is_read_only():
    """Pin the narrow sqlite3 exception: read-only Chroma probe, never a store.

    `backend/observability/readiness.py` may open Chroma's SQLite file only
    through an immutable read-only URI (`mode=ro`). It must not construct a
    Chroma client (which initializes storage as a side effect), must not
    touch script execution, and must not contain any write verb anywhere in
    the module — quoted or dynamically built.
    """
    import re

    source = (BACKEND_ROOT / "observability" / "readiness.py").read_text(
        encoding="utf-8"
    )
    assert "mode=ro" in source, "the probe must open SQLite read-only"
    assert "PersistentClient" not in source, (
        "the probe must not construct a Chroma client"
    )
    assert "executescript" not in source, "the probe must not execute SQL scripts"
    for verb in (
        "INSERT",
        "UPDATE",
        "DELETE",
        "REPLACE",
        "CREATE",
        "DROP",
        "ALTER",
        "ATTACH",
        "VACUUM",
    ):
        assert not re.search(rf"\b{verb}\b", source, re.IGNORECASE), (
            f"the probe must not contain {verb} anywhere"
        )


def _workspace_violations(packages: list[Path] | None = None) -> list[str]:
    """Forbidden workspaces / planner / legacy-memory imports.

    The retained memory write pipeline is the only permitted `backend.memory`
    module. Accepting an explicit package list lets a test plant a violation in
    a temporary tree and assert it is reported.
    """
    violations: list[str] = []
    targets = _backend_packages() if packages is None else packages

    for py_file in _collect_py_files(targets):
        rel_path = _relative(py_file)
        for lineno, module, symbol in _scan_imports(py_file):
            mod_parts = module.split(".")

            if "workspaces" in mod_parts or symbol == "workspaces":
                violations.append(
                    f"{rel_path}:{lineno} imports workspaces ({module}.{symbol})"
                )
                continue

            if "planner" in mod_parts or symbol == "planner":
                violations.append(
                    f"{rel_path}:{lineno} imports planner ({module}.{symbol})"
                )
                continue

            if (
                "memory" in mod_parts
                or "memory_controls" in mod_parts
                or symbol in ("memory", "memory_controls")
            ):
                if module == "backend.memory.write_pipeline" or module.startswith(
                    "backend.memory.write_pipeline."
                ):
                    continue
                violations.append(
                    f"{rel_path}:{lineno} imports legacy memory ({module}.{symbol})"
                )

    return violations


def test_no_workspace_or_planner_or_legacy_memory_imports():
    """Verify that no mounted backend module imports workspaces, planner, or legacy memory.

    Per ADR 0018 & ADR 0020, Workspace, Planner, and legacy Memory surfaces are removed.
    The only allowed memory module is backend.memory.write_pipeline.
    """
    violations = _workspace_violations()

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
                    violations.append(
                        f"config.py:{node.lineno} defines variable '{target.id}'"
                    )

    assert not violations, (
        f"Found {len(violations)} forbidden legacy config options in backend/app/config.py:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def _walk_routes(routes, prefix: str = "") -> list[tuple[str, str]]:
    """(method, path) for every route handler, recursing into included routers.

    This FastAPI version wraps an included router in `_IncludedRouter`, whose
    `path` is `None`; the inner routes are reached through `original_router`.
    Inner paths do **not** carry the include prefix (`/chat`, not `/api/v1/chat`),
    so this walk is used for structure and for detecting surfaces `openapi()`
    cannot enumerate — not for comparing against the prefixed approved set.
    """
    found: list[tuple[str, str]] = []
    for route in routes:
        kind = type(route).__name__
        if kind == "_IncludedRouter":
            inner = getattr(getattr(route, "original_router", None), "routes", None)
            if inner:
                found.extend(_walk_routes(inner, prefix))
            continue
        if kind == "Mount":
            continue  # reported separately
        path = getattr(route, "path", None)
        methods = (getattr(route, "methods", None) or set()) - {"HEAD", "OPTIONS"}
        if path:
            for method in sorted(methods):
                found.append((method, prefix + path))
    return found


def _uninspectable_mounts(routes) -> list[str]:
    """Route surfaces `openapi()` does not enumerate.

    A mounted sub-application is served but absent from the schema, so the
    approved route set cannot see it. That is a gap in the sentinel, not a
    property of the mount.
    """
    return [
        str(getattr(route, "path", "<unknown>"))
        for route in routes
        if type(route).__name__ == "Mount"
    ]


def _assert_route_tree_is_inspectable(app) -> None:
    mounts = _uninspectable_mounts(app.routes)
    assert not mounts, (
        "a mounted sub-application is not enumerated by openapi(), so the "
        f"approved route set cannot see it: {mounts}"
    )
    walked = _walk_routes(app.routes)
    assert walked, (
        "the route walk found nothing, so this assertion is not checking "
        "anything. The framework's included-router representation has probably "
        "changed: fix the walk rather than deleting this check."
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

    approved_routes = set(APPROVED_ROUTES)
    _assert_route_tree_is_inspectable(app)

    openapi = app.openapi()
    mounted_routes: set[tuple[str, str]] = set()
    for path, path_item in openapi.get("paths", {}).items():
        for method in path_item.keys():
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                mounted_routes.add((method.upper(), path))

    # Check for forbidden prefix routes
    forbidden_segments = ("/workspaces", "/planner", "/memory", "/memory/controls")
    forbidden_mounted = [
        f"{m} {p}"
        for m, p in sorted(mounted_routes)
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
        f"If you added a route deliberately, add it to APPROVED_ROUTES in this "
        f"file — a new route requires a specification and an approved plan "
        f"(`AGENTS.md`), so this edit is meant to be deliberate.\n"
        f"Missing approved routes ({len(missing_routes)}):\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(missing_routes))
        + f"\nUnexpected mounted routes ({len(unexpected_routes)}):\n"
        + "\n".join(f"  - {m} {p}" for m, p in sorted(unexpected_routes))
    )


def test_authentication_has_no_compatibility_mode():
    """Verify authentication is unconditional and enforced before routing.

    Per ADR 0018, authentication is unconditional. Per ADR 0026 the enforcement
    point is `enforce_authentication`, which runs in the middleware ahead of
    routing, while `require_principal` is only the accessor of the principal it
    resolved. The no-compatibility-mode check follows the control to its new
    location rather than being dropped: it now covers both functions.
    """
    from backend.security.dependencies import enforce_authentication, require_principal

    deps_file = BACKEND_ROOT / "security" / "dependencies.py"
    tree = ast.parse(deps_file.read_text(encoding="utf-8"), filename=str(deps_file))

    forbidden_terms = {
        "AUTH_REQUIRED",
        "COMPATIBILITY",
        "COMPATIBILITY_OWNER_ID",
        "_compatibility_principal",
    }
    checked = {"require_principal", "enforce_authentication"}
    seen: set[str] = set()
    found_forbidden: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in checked:
            seen.add(node.name)
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id in forbidden_terms:
                    found_forbidden.append(
                        f"{node.name} line {child.lineno}: references '{child.id}'"
                    )
                elif isinstance(child, ast.Attribute) and child.attr in forbidden_terms:
                    found_forbidden.append(
                        f"{node.name} line {child.lineno}: references attribute "
                        f"'{child.attr}'"
                    )

    assert seen == checked, f"function definitions not found: {checked - seen}"
    assert not found_forbidden, (
        f"authentication contains legacy compatibility mode references:\n"
        + "\n".join(f"  - {f}" for f in found_forbidden)
    )

    # Runtime check at the control's location: no credentials must be rejected
    # with 401, and must never yield a compatibility principal.
    scope = {"type": "http", "path": "/api/v1/chat", "headers": []}
    response = enforce_authentication(Request(scope))
    assert response is not None, "an unauthenticated request must be rejected"
    assert response.status_code == 401, (
        f"Expected 401 Unauthorized, got {response.status_code}"
    )

    # The accessor must fail closed rather than authenticate on its own. This is
    # what makes the enforcement point load-bearing: if it could resolve
    # credentials itself, deleting the middleware would go unnoticed.
    with pytest.raises(HTTPException) as exc_info:
        require_principal(Request(dict(scope)))
    assert exc_info.value.status_code == 500, (
        "require_principal must fail closed when the middleware did not run, "
        f"got {exc_info.value.status_code}"
    )


def test_authentication_is_enforced_in_the_middleware_before_the_body_limit():
    """The enforcement point must be the middleware, not a route dependency.

    A route dependency is solved inside `solve_dependencies`, which FastAPI
    calls after it has read and parsed the body, so a malformed body produced
    `422` before the authentication decision ran (ADR 0026). This check pins the
    call site and its position relative to the body limit.
    """
    main_file = BACKEND_ROOT / "app" / "main.py"
    source = main_file.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(main_file))

    handler: ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "request_correlation_middleware"
        ):
            handler = node
            break

    assert handler is not None, (
        "the correlation middleware must be registered; without it every "
        "guarded route fails closed with 500"
    )

    called = {
        child.func.id
        for child in ast.walk(handler)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }
    assert "enforce_authentication" in called, (
        "the correlation middleware must call enforce_authentication; otherwise "
        "an unauthenticated request with a malformed body is answered 422"
    )

    body = ast.get_source_segment(source, handler) or ""
    assert body.index("enforce_authentication") < body.index(
        "enforce_request_body_limit"
    ), "authentication must be evaluated before the body is read"


def test_cors_wraps_the_authentication_middleware():
    """An early `401` from the correlation middleware must pass through CORS.

    Starlette inserts each middleware at position 0, so the most recently
    registered layer is outermost. With CORS registered earlier the correlation
    middleware sits outside it, an early response carries no
    `Access-Control-Allow-Origin`, and a browser sees an opaque network error
    instead of the status. Moving the registration silently restores that.
    """
    from backend.app.main import app

    names = [middleware.cls.__name__ for middleware in app.user_middleware]
    assert "CORSMiddleware" in names, names
    assert "BaseHTTPMiddleware" in names, names
    assert names.index("CORSMiddleware") < names.index("BaseHTTPMiddleware"), (
        "CORSMiddleware must be registered last so it is outermost: "
        f"stack is {names}"
    )


# ---------------------------------------------------------------------------
# Sentinel coverage: the scope is derived, and the scan reports what it reads
# ---------------------------------------------------------------------------


def test_scan_scope_covers_every_backend_package():
    """The scope is derived, so a package added later is covered without an edit.

    Four packages were previously unscanned — `orchestration`, `rag`,
    `preprocessing` and `memory` — and two of them are on the request path.
    """
    names = {package.name for package in _backend_packages()}

    assert names >= {
        "app",
        "conversations",
        "memory",
        "observability",
        "orchestration",
        "preprocessing",
        "rag",
        "security",
        "storage",
    }, names
    assert "tests" not in names, "the suite must not scan itself"


def test_the_scan_reports_a_violation_it_is_given(tmp_path):
    """The scan must report a planted violation, not merely find nothing.

    The probe is built in a temporary tree: a boundary test that wrote into the
    repository would be a worse defect than the one it checks for.
    """
    package = tmp_path / "planted_package"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "offender.py").write_text("import sqlite3\n", encoding="utf-8")

    violations = _sqlite_violations([package])

    # Assert the message shape, not the path prefix: the temporary directory may
    # sit inside or outside the repository depending on `--basetemp`.
    assert len(violations) == 1, violations
    assert "offender.py:1 imports sqlite3 (sqlite3)" in violations[0]


def test_the_scan_reports_a_planted_legacy_memory_import(tmp_path):
    package = tmp_path / "planted_package"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "offender.py").write_text(
        "from backend.memory import legacy_store\n", encoding="utf-8"
    )

    violations = _workspace_violations([package])

    assert len(violations) == 1, violations
    assert "legacy memory" in violations[0]


def test_the_write_pipeline_remains_the_permitted_memory_module(tmp_path):
    """The narrow exception must survive the widened scope."""
    package = tmp_path / "planted_package"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "allowed.py").write_text(
        "from backend.memory.write_pipeline import models\n", encoding="utf-8"
    )

    assert _workspace_violations([package]) == []


def test_a_mount_is_rejected_because_openapi_cannot_see_it():
    """A surface OpenAPI does not enumerate must fail the sentinel.

    The route set comparison reads `openapi()`, so a mount is invisible to it.
    """
    from fastapi import FastAPI

    async def _asgi(scope, receive, send):  # pragma: no cover - never called
        pass

    probe = FastAPI()
    probe.mount("/static", _asgi)

    assert _uninspectable_mounts(probe.routes) == ["/static"]
    with pytest.raises(AssertionError):
        _assert_route_tree_is_inspectable(probe)


def test_the_structural_walk_fails_when_it_finds_nothing():
    """A framework rename must fail loudly rather than silently scan zero routes.

    A bare `FastAPI()` is not suitable here: it carries the four documentation
    routes, so the walk is never empty for it.
    """

    class _NoRoutes:
        routes: list = []

    assert _walk_routes(_NoRoutes().routes) == []
    with pytest.raises(AssertionError):
        _assert_route_tree_is_inspectable(_NoRoutes())


def test_the_structural_walk_sees_the_mounted_routes():
    from backend.app.main import app

    assert len(_walk_routes(app.routes)) >= len(APPROVED_ROUTES)


def test_approved_routes_is_the_single_source_of_truth():
    assert len(APPROVED_ROUTES) == 8, APPROVED_ROUTES
    assert ("GET", "/health") in APPROVED_ROUTES
    assert ("POST", "/api/v1/chat") in APPROVED_ROUTES
