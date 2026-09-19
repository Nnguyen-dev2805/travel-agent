"""Unit tests for source-neutral generation contracts and dependency boundaries.

Governed by Plan v0.15 and ADR 0039:
- GenerationContext deliberately has no travel_evidence, memory_context, or
  Memory/RAG domain types.
- backend/generation/contracts.py imports neither backend.rag, backend.memory,
  nor backend.orchestration.
- ContextSufficiency.NOT_REQUIRED is distinct from INSUFFICIENT.
- GenerationResult is source-neutral.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from enum import Enum
from pathlib import Path

import pytest


def test_generation_contracts_imports_and_types():
    from backend.generation.contracts import (
        ContextSufficiency,
        GenerationCitation,
        GenerationContext,
        GenerationResult,
    )

    # ContextSufficiency enum
    assert issubclass(ContextSufficiency, str)
    assert issubclass(ContextSufficiency, Enum)
    assert ContextSufficiency.NOT_REQUIRED.value == "not_required"
    assert ContextSufficiency.SUFFICIENT.value == "sufficient"
    assert ContextSufficiency.INSUFFICIENT.value == "insufficient"
    assert set(ContextSufficiency) == {
        ContextSufficiency.NOT_REQUIRED,
        ContextSufficiency.SUFFICIENT,
        ContextSufficiency.INSUFFICIENT,
    }

    # GenerationCitation
    cit = GenerationCitation(title="Danang Guide", url="https://example.com/danang")
    assert cit.title == "Danang Guide"
    assert cit.url == "https://example.com/danang"
    with pytest.raises(FrozenInstanceError):
        cit.title = "New Title"  # type: ignore

    # GenerationContext
    ctx = GenerationContext(
        prompt_context="Some prompt context",
        citations=(cit,),
        sufficiency=ContextSufficiency.SUFFICIENT,
    )
    assert ctx.prompt_context == "Some prompt context"
    assert ctx.citations == (cit,)
    assert ctx.sufficiency is ContextSufficiency.SUFFICIENT
    with pytest.raises(FrozenInstanceError):
        ctx.prompt_context = "Other"  # type: ignore

    # GenerationResult
    res = GenerationResult(
        reply="Hello from model",
        model="gpt-4o-mini",
        citations=(cit,),
    )
    assert res.reply == "Hello from model"
    assert res.model == "gpt-4o-mini"
    assert res.citations == (cit,)
    with pytest.raises(FrozenInstanceError):
        res.reply = "Mutated"  # type: ignore


def test_generation_contracts_clean_break_ast_boundary():
    """backend/generation/contracts.py imports neither rag, memory, nor orchestration."""
    contracts_path = (
        Path(__file__).resolve().parents[3] / "generation" / "contracts.py"
    )
    assert contracts_path.exists(), f"File {contracts_path} must exist"

    tree = ast.parse(contracts_path.read_text(encoding="utf-8"), filename=str(contracts_path))
    imported_modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    banned_prefixes = (
        "backend.rag",
        "backend.memory",
        "backend.orchestration",
        "backend.storage",
        "fastapi",
        "sqlalchemy",
        "openai",
    )

    violations = [
        mod
        for mod in imported_modules
        if any(mod == banned or mod.startswith(f"{banned}.") for banned in banned_prefixes)
    ]
    assert not violations, f"Banned imports found in generation contracts: {violations}"
