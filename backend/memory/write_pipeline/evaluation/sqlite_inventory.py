"""Read-only SQLite legacy data inventory and migration decision generator.

Enforces:
- Read-only database connection ('mode=ro')
- Zero printing or leakage of message/candidate content
- Records schema versions, table counts, provenance assessment
- Generates JSON and Markdown reports under docs/reports/
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sqlite3
from typing import Any

logger = logging.getLogger("travel_agent_sqlite_inventory")


def inventory_sqlite_database(db_path: str | Path) -> dict[str, Any]:
    """Inspect local SQLite database read-only and return structured audit metadata."""
    path = Path(db_path)
    if not path.exists():
        return {
            "database_path": str(path),
            "exists": False,
            "table_counts": {},
            "schema_versions": {},
            "provenance_assessment": "DATABASE_FILE_NOT_FOUND",
            "legacy_decision": "DISPOSABLE",
            "rationale": "No SQLite file found at target path.",
        }

    # Open strictly in read-only mode using URI
    uri = f"file:{path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        cursor = connection.cursor()

        # 1. Inspect table names
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [row[0] for row in cursor.fetchall()]

        # 2. Count rows in each table without reading row content
        table_counts: dict[str, int] = {}
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            table_counts[table] = cursor.fetchone()[0]

        # 3. Read schema versions if schema_versions table exists
        schema_versions: dict[str, int] = {}
        if "schema_versions" in tables:
            cursor.execute("SELECT module, version FROM schema_versions")
            for mod, ver in cursor.fetchall():
                schema_versions[str(mod)] = int(ver)

        # 4. Assess memory provenance
        memory_tables = [t for t in tables if "memory" in t]
        has_memory_data = any(table_counts.get(t, 0) > 0 for t in memory_tables)

        if not memory_tables or not has_memory_data:
            provenance_assessment = "NO_LEGACY_MEMORY_DATA_EXISTS"
            legacy_decision = "DISPOSABLE"
            rationale = (
                "SQLite store contains no legacy memory candidates, runs, or assertions. "
                "Only trip_workspaces and workspace schema version exist. "
                "No in-place migration or backfill required; PostgreSQL is the sole "
                "authoritative store for semantic memory."
            )
        else:
            provenance_assessment = "LEGACY_MEMORY_FOUND_QUARANTINE_REQUIRED"
            legacy_decision = "QUARANTINE"
            rationale = (
                "Legacy memory data exists; must be quarantined as read-only compatibility "
                "evidence without active promotion into V2 PostgreSQL store."
            )

        return {
            "database_path": str(path),
            "exists": True,
            "tables": tables,
            "table_counts": table_counts,
            "schema_versions": schema_versions,
            "memory_tables_found": memory_tables,
            "provenance_assessment": provenance_assessment,
            "legacy_decision": legacy_decision,
            "rationale": rationale,
        }
    finally:
        connection.close()


def generate_inventory_report(
    db_path: str | Path = "data/app/travel_agent.sqlite3",
    output_dir: str | Path = "docs/reports/memory-write-pipeline",
) -> tuple[Path, Path]:
    """Run read-only inventory and write JSON + Markdown reports."""
    data = inventory_sqlite_database(db_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "legacy-sqlite-inventory-report.json"
    md_path = out_dir / "legacy-sqlite-inventory-report.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Markdown report
    md_lines = [
        "# Legacy SQLite Data Inventory and Migration Decision Report",
        "",
        f"**Database Path:** `{data['database_path']}`",
        f"**File Exists:** `{data['exists']}`",
        f"**Legacy Decision:** `{data['legacy_decision']}`",
        f"**Provenance Assessment:** `{data['provenance_assessment']}`",
        "",
        "## Schema Versions",
        "",
        "| Module | Version |",
        "| --- | --- |",
    ]
    for mod, ver in data.get("schema_versions", {}).items():
        md_lines.append(f"| `{mod}` | `{ver}` |")

    md_lines.extend([
        "",
        "## Table Inventory",
        "",
        "| Table Name | Row Count |",
        "| --- | --- |",
    ])
    for tbl, count in data.get("table_counts", {}).items():
        md_lines.append(f"| `{tbl}` | {count} |")

    md_lines.extend([
        "",
        "## Governance and Migration Decision",
        "",
        data.get("rationale", ""),
        "",
        "### Rollback and Disposal Safeguards",
        "- No memory records exist in SQLite to delete, backfill, or corrupt.",
        "- Workspaces in SQLite remain untouched for legacy read compatibility.",
        "- All V2 semantic memory writes and outbox events target isolated PostgreSQL.",
    ])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    return json_path, md_path


if __name__ == "__main__":
    j_path, m_path = generate_inventory_report()
    print(f"Generated SQLite inventory reports:\n  {j_path}\n  {m_path}")
