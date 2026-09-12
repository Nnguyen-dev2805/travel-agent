"""The generation package must not load the model stack on a submodule import.

Regression test for a real defect. `backend/rag/generation/__init__.py` used to
re-export `RAGService` eagerly, which imports `VectorEmbedder`, which imports
`sentence-transformers`, which imports torch. Importing `...generation.llm` to
build a prompt therefore loaded the entire model runtime; in a memory-constrained
environment the import was killed outright (exit 137), and because
`backend/tests/conftest.py` imports the app, that one eager import blocked the
whole Python suite.

Checked in a subprocess on purpose. If the test session has already imported the
model stack, an in-process assertion would pass or fail for reasons unrelated to
this package, which is exactly the kind of test this repository does not want.
"""

import subprocess
import sys

_MODEL_STACK = ("sentence_transformers", "torch", "transformers")


def _modules_after(statement: str) -> set[str]:
    """Import `statement` in a fresh interpreter and return its loaded modules."""
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; {statement}; print('\\n'.join(sys.modules))"],
        capture_output=True,
        text=True,
        check=True,
    )
    return set(result.stdout.splitlines())


def _assert_no_model_stack(loaded: set[str]) -> None:
    offending = sorted(set(_MODEL_STACK) & loaded)
    assert not offending, f"importing the package loaded the model stack: {offending}"


def test_importing_the_llm_submodule_does_not_load_the_model_stack():
    loaded = _modules_after("import backend.rag.generation.llm")

    assert "backend.rag.generation.llm" in loaded, "the submodule did not import at all"
    _assert_no_model_stack(loaded)


def test_importing_the_package_root_does_not_load_the_model_stack():
    loaded = _modules_after("import backend.rag.generation")

    _assert_no_model_stack(loaded)


def test_the_llm_submodule_still_exposes_its_public_name():
    """The package may export nothing, but the submodules must stay importable."""
    loaded = _modules_after("from backend.rag.generation.llm import LLMGenerator")

    assert "backend.rag.generation.llm" in loaded
    _assert_no_model_stack(loaded)
