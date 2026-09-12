"""Integration-test package configuration.

Tests collected from this directory are integration tests, so the approved
plan command `pytest backend/tests/integration -m integration` selects them
explicitly. The path check keeps this hook from marking unit tests when both
trees are collected in one session.
"""

from pathlib import Path

import pytest

_INTEGRATION_ROOT = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items):
    for item in items:
        try:
            node_path = Path(str(item.fspath)).resolve()
        except Exception:
            continue
        if _INTEGRATION_ROOT in node_path.parents:
            item.add_marker(pytest.mark.integration)
