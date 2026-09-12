# Test Suite Truthfulness Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence. Each task ends with a review checkpoint; do not begin
> the next task until the checkpoint condition holds.

**Goal:** Make the suite able to tell the truth — widen the boundary sentinel to every backend package, make its route assertion catch what OpenAPI cannot see, strengthen four assertions so they distinguish a healthy system from a specific failure, and remove two tests' dependence on git-ignored artifacts and a live model.

**Architecture:** Three independent groups, all confined to `backend/tests/`. The sentinel's scan scope is derived from the repository rather than a hand-maintained list. Weak assertions are replaced by ones that name which outcome they expect, or that compare a reported aggregate against what its components imply. Two tests are split into a hermetic part that always runs and can fail, and an artifact-dependent part that skips with the missing path named.

**Tech Stack:** Python 3 / pytest / FastAPI / Starlette 1.6 / ChromaDB / SQLAlchemy 2 / PostgreSQL 16

**Spec:** `docs/specs/2026-09-11-test-suite-truthfulness-design.md` v0.1

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-11 |
| Approved specification | `docs/specs/2026-09-11-test-suite-truthfulness-design.md` v0.1 — **Approved 2026-09-11** by the repository owner, together with this plan. |
| Execution owner | Implementation agent |
| Decision owner | Repository owner |
| Scope | Test-suite coverage, assertion strength, and artifact dependence in `backend/tests/` |
| Verification | The sentinel's own suite; the widened scan demonstrated against a deliberate violation; the route sentinel demonstrated against a deliberate `Mount`; `pytest backend/tests/unit`, `backend/tests/boundaries` and `backend/tests/integration`; the final skip inventory; `cd frontend && npx vitest run` |

## Global Constraints

1. Every persistent repository change requires a written specification and an approved implementation plan (`AGENTS.md`). This plan is a draft; it authorizes nothing. Level 2 requires no ADR, and the specification records why.
2. The repository owner creates or selects branches and decides when to stage, commit in the primary working tree, push, open a PR, merge, and release. No Git delivery is authorized by this plan.
3. The working tree is dirty and large. Read a dirty file before touching it and work with the existing edits rather than reverting them.
4. **No production module may change.** If a task appears to need one, stop and return the work for review: the approved design was wrong.
5. **No test may be deleted or relaxed.** Every test named in the specification is repaired, split, or given an explicit skip. A test whose assertion is replaced must be at least as strong as the one it replaces.
6. **No assertion may be widened to make a test pass.** If a strengthened assertion fails, the production behaviour it describes is the finding, and it is reported rather than accommodated.
7. The sentinel's scan scope is derived from the repository. A hand-maintained list that can fall behind is the defect being fixed.
8. The route comparison stays exact. The approved set becomes one named constant, and the failure message must name it and say that a new route requires a specification.
9. The structural route assertion must **fail when it discovers zero routes**, so a dependency rename cannot turn it into a silent no-op.
10. The two artifact-dependent tests must skip with the missing path or model named in the reason. A skip without a reason is not acceptable.
11. Behaviour changes use a red-green-refactor cycle. Every task states the failing test first, and every claim that an assertion can now discriminate is demonstrated by making it fail.
12. Never expose secrets, credentials, tokens, or sensitive personal data in code, logs, commands, evidence, or documentation. Test tokens remain obvious placeholders.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/tests/boundaries/test_clean_break_boundaries.py` | Derive the scan scope from the repository; hold the approved route set as one constant; add the structural route assertion | — |
| `backend/tests/integration/test_ops_readiness_api.py` | Assert the reported aggregate agrees with its components; make the mock engine validate statements | Task 1 |
| `backend/tests/integration/test_auth_api.py` | Assert what a valid token must achieve, without a redundant clause | Task 2 |
| `backend/tests/integration/test_rag_evaluation_flow.py` | Add a below-threshold run that asserts a failure state and names the gate | Task 2 |
| `backend/tests/integration/test_postgres_migrations.py` | Validate the setup before asserting a narrowed exception type | Task 2 |
| `backend/tests/integration/test_vector_store.py` | Hermetic store test on deterministic vectors; separately-marked embedder test | Task 3 |
| `backend/tests/unit/test_chunker.py` | Hermetic loader test against a fixture; artifact-dependent test with a named skip | Task 3 |

**No production file appears here.** That is the point of the change, and it is also its stopping condition.

## Task 1: The sentinel covers what it claims to protect

**Files:**

- Modify: `backend/tests/boundaries/test_clean_break_boundaries.py`

**Interfaces:**

- Produces: a repository-derived scan scope; `APPROVED_ROUTES` as the single source of truth; a structural assertion over the router tree
- Consumes: `_IncludedRouter.original_router.routes` for recursion, and `app.openapi()["paths"]` for the canonical product surface

- [x] **Step 1: Write the failing tests**

```python
def test_scan_scope_covers_every_backend_package():
    """The scope is derived, so a package added later is covered without an edit."""
    packages = _backend_packages()
    assert {"app", "conversations", "memory", "observability", "orchestration",
            "preprocessing", "rag", "security", "storage"} <= packages, packages
    assert "tests" not in packages, "the suite must not scan itself"


def test_the_scan_detects_a_violation_in_a_previously_unscanned_package(tmp_path):
    """The four packages that were unscanned must now be scanned.

    Demonstrated rather than asserted: a file importing sqlite3 is planted in
    each previously-unscanned package's directory, and the scan must report it.
    """
    for package in ("orchestration", "rag", "preprocessing", "memory"):
        planted = BACKEND_ROOT / package / "_boundary_probe.py"
        assert not planted.exists()
    try:
        for package in ("orchestration", "rag", "preprocessing", "memory"):
            (BACKEND_ROOT / package / "_boundary_probe.py").write_text(
                "import sqlite3\n", encoding="utf-8"
            )
        violations = _sqlite_violations()
        assert len(violations) == 4, violations
    finally:
        for package in ("orchestration", "rag", "preprocessing", "memory"):
            (BACKEND_ROOT / package / "_boundary_probe.py").unlink(missing_ok=True)


def test_a_mount_is_rejected_because_openapi_cannot_see_it():
    """A surface OpenAPI does not enumerate must fail the sentinel."""
    from fastapi import FastAPI
    from starlette.routing import Mount

    probe = FastAPI()
    probe.mount("/static", Mount("/static", app=lambda scope, receive, send: None))
    assert _uninspectable_mounts(probe.routes), "a Mount must be reported"


def test_the_structural_walk_fails_when_it_finds_nothing():
    """A framework rename must fail loudly, not silently scan zero routes."""
    from fastapi import FastAPI

    assert _walk_routes(FastAPI().routes) == []
    with pytest.raises(AssertionError):
        _assert_route_tree_is_inspectable(FastAPI())


def test_approved_routes_is_the_single_source_of_truth():
    assert len(APPROVED_ROUTES) == 8, APPROVED_ROUTES
```

- [x] **Step 2: Run verification**

Run: `pytest backend/tests/boundaries -q`

Expected: FAIL — the helpers do not exist.

- [x] **Step 3: Derive the scan scope**

```python
_EXCLUDED_PACKAGE_DIRS = frozenset({"tests", "__pycache__"})


def _backend_packages() -> list[Path]:
    """Every package directory under `backend/`, except the suite itself.

    Derived rather than declared: a hand-maintained list is what let four
    packages go unscanned.
    """
    return sorted(
        child
        for child in BACKEND_ROOT.iterdir()
        if child.is_dir()
        and child.name not in _EXCLUDED_PACKAGE_DIRS
        and next(child.rglob("*.py"), None) is not None
    )
```

**Corrected during implementation.** This sketch originally required
`(child / "__init__.py").exists()`. `backend/rag` **and** `backend/rag/evaluation`
are implicit namespace packages (PEP 420) and have no `__init__.py`, so that
predicate excluded exactly the packages the widened scope exists to cover.
Membership now keys on the presence of Python files. Recorded as discovered
finding 1 in the Completion Record.

Replace `MOUNTED_BACKEND_DIRS` and `MOUNTED_BACKEND_DIRS_WITH_MEMORY` with this. Keep
the existing narrow exception for `backend/observability/readiness.py`, and keep
`test_readiness_sqlite_access_is_read_only` unchanged.

- [x] **Step 4: Extract the violation check so it can be called directly**

The planted-file test needs the violation list, not just the assertion. Extract the
body of `test_no_sqlite_imports_in_mounted_backend` into
`_sqlite_violations() -> list[str]` and have the test assert it is empty.

- [x] **Step 5: Add the structural route assertion**

```python
def _walk_routes(routes, prefix: str = "") -> list[tuple[str, str]]:
    """(method, path) for every route handler, recursing into included routers.

    This FastAPI version wraps an included router in `_IncludedRouter`, whose
    `path` is `None`; the inner routes are reached through `original_router`.
    Inner paths do not carry the include prefix, so this walk is used for
    structure and counting, not for comparing against the prefixed approved set.
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
        for method in sorted((getattr(route, "methods", None) or set()) - {"HEAD", "OPTIONS"}):
            if path:
                found.append((method, prefix + path))
    return found


def _uninspectable_mounts(routes) -> list[str]:
    """Route surfaces OpenAPI does not enumerate."""
    return [
        getattr(route, "path", "<unknown>")
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
        "changed; fix the walk rather than deleting this check."
    )
```

Call `_assert_route_tree_is_inspectable(app)` from the existing
`test_only_approved_routes_mounted`.

- [x] **Step 6: Move the approved set to one constant and improve the message**

Hoist the literal set to a module-level `APPROVED_ROUTES` with a docstring stating
that a new route requires a specification and a deliberate edit here. Keep
`mounted_routes == APPROVED_ROUTES`, and make the failure message name the constant
and that requirement, in addition to the existing missing/unexpected listing.

- [x] **Step 7: Run verification**

Run: `pytest backend/tests/boundaries -q`

Expected: PASS, with the boundary count increased by the new tests.

- [x] **Step 8: Review checkpoint**

Review: the derived scope, the extracted violation helper, the structural assertion,
and the route constant. Confirm the scan now covers nine packages, that
`test_readiness_sqlite_access_is_read_only` is unchanged, that the planted-file test
cleans up after itself, and that the structural walk asserts non-empty.

Expected: the boundary suite passes; the planted-file test reports four violations
while the probes exist and zero after cleanup.

## Task 2: Assertions that discriminate

**Files:**

- Modify: `backend/tests/integration/test_ops_readiness_api.py`
- Modify: `backend/tests/integration/test_auth_api.py`
- Modify: `backend/tests/integration/test_rag_evaluation_flow.py`
- Modify: `backend/tests/integration/test_postgres_migrations.py`

**Interfaces:**

- Consumes: the readiness response's `status` and `components` fields
- Produces: a mock engine that fails on an unrecognised statement; a below-threshold evaluation run; a validated migration setup

- [x] **Step 1: Establish the facts the assertions depend on**

Before writing any assertion, determine by observation:

1. how the readiness aggregate is computed from its components, so the assertion
   can compare the two rather than restate the enum;
2. which parameter of `DeterministicMockRuntime` or `DeterministicMockJudge`
   produces a below-threshold result;
3. which exception type the migration actually raises when the orphan row is
   present.

Record each answer in the Completion Record. Do not guess any of them.

- [x] **Step 2: Write the failing tests**

```python
def test_readiness_status_agrees_with_its_components(client):
    """The reported aggregate must follow from the components.

    Previously any of the four enum values was accepted, so `degraded` satisfied
    a healthy-path expectation.
    """
    response = client.get(READINESS, headers=AUTHED)
    body = response.json()
    expected = _expected_status_from(body["components"])
    assert body["status"] == expected, (body["status"], body["components"])
    assert response.status_code == (200 if expected == "ready" else 503)


def test_the_probe_engine_rejects_an_unrecognised_statement():
    """A permissive mock validated no SQL: every statement returned (1,)."""
    engine = _StrictProbeEngine()
    with pytest.raises(AssertionError):
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT something_unexpected"))
```

For `test_auth_api.py`, replace the redundant pair:

```python
    # `401` is not in `(200, 503)`, so the old second assertion proved nothing.
    assert response.status_code in (200, 503)
    body = response.json()
    assert "detail" not in body or body["detail"] not in AUTH_FAILURE_DETAILS
    assert body["status"] == _expected_status_from(body["components"])
```

For `test_rag_evaluation_flow.py`, add a run whose inputs are below threshold and
assert the failure:

```python
def test_a_below_threshold_run_reports_a_failure_and_names_the_gate(tmp_path):
    """The existing run uses perfect doubles, so PASS was inevitable for any
    gate implementation. This run must fail, and must say why."""
    ...
    artifact = runner.run(mode=RunMode.FULL, output_dir=tmp_path / "failing")
    record = artifact.run_record
    assert record["state"] != ResultState.PASS.value, record["state"]
    assert record["failed_gates"], "a failing run must name the gate that fired"
```

For `test_postgres_migrations.py`, validate the setup and narrow the expectation:

```python
    with pg_engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT count(*) FROM conversations WHERE conversation_id = 'cv_orphan'")
        ).scalar() == 1, "the setup row must exist, or the upgrade fails for the wrong reason"

    with pytest.raises(<the observed exception type>):
        _upgrade_to_head(pg_engine, _test_dsn())
```

- [x] **Step 3: Run verification**

Run: `PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… pytest backend/tests/integration -q -k "readiness or auth or evaluation or migration"`

Expected: the new assertions FAIL against current behaviour where the specification
predicts they should — in particular the aggregate-agreement assertion, if the probe
does not in fact keep them consistent, and the below-threshold run, which has no
counterpart today.

- [x] **Step 4: Implement the discriminating assertions**

Make each assertion fail for its own reason and for no other. Where an assertion
cannot be made to fail without changing production behaviour, **stop**: that is a
production finding, and it is reported rather than accommodated.

- [x] **Step 5: Demonstrate that each new assertion can fail**

For each of the four, mutate the thing it asserts — reorder the aggregate, relax the
mock, make the below-threshold run pass, remove the setup row — and confirm the
assertion fails. Restore. Record the four demonstrations in the Completion Record.

- [x] **Step 6: Run verification**

Run: `PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… pytest backend/tests/integration -q`

Expected: PASS.

- [x] **Step 7: Review checkpoint**

Review: the four assertion changes and their mutation demonstrations. Confirm no
assertion was widened, that the readiness mock is stricter than before, that the
token test still asserts the token value never appears in a response, and that no
production file changed.

Expected: all four assertions fail when their subject is mutated, and the
integration suite passes unmutated.

## Task 3: Hermetic tests and named skips

**Files:**

- Modify: `backend/tests/integration/test_vector_store.py`
- Modify: `backend/tests/unit/test_chunker.py`

**Interfaces:**

- Consumes: `ChromaVectorStore(persist_directory, collection_name)` and `add_chunks(chunks, embeddings)`, which take vectors rather than text
- Produces: a deterministic vector helper; a fixture dataset written into `tmp_path`

- [x] **Step 1: Write the failing tests**

```python
def test_chroma_store_round_trip_without_a_model(tmp_path):
    """The store takes vectors, so no embedder is needed and nothing is skipped."""
    store = ChromaVectorStore(
        persist_directory=tmp_path / "chroma", collection_name="probe"
    )
    assert store.count() == 0, "a fresh directory must be empty"

    added = store.add_chunks(SAMPLE_CHUNKS, _vectors(len(SAMPLE_CHUNKS)))
    assert added == 2
    assert store.count() == 2, "an exact count, not a lower bound on a shared path"

    results = store.search_similar(_vector(0), top_k=2)
    assert len(results) == 2
    assert results[0]["metadata"]["title"] == "7 stunning rooftop bars"


def test_the_loader_reads_a_fixture_dataset(tmp_path):
    """The loader's behaviour, asserted where the repository is the only input."""
    path = tmp_path / "fixture.jsonl"
    path.write_text("\n".join(json.dumps(doc) for doc in FIXTURE_DOCS) + "\n",
                    encoding="utf-8")
    docs = load_jsonl_dataset(path)
    assert len(docs) == len(FIXTURE_DOCS)
    assert set(docs[0]) >= {"document_id", "url", "title", "text"}
```

- [x] **Step 2: Run verification**

Run: `pytest backend/tests/unit/test_chunker.py backend/tests/integration/test_vector_store.py -q`

Expected: FAIL on the new tests (helpers do not exist) and, before the change,
observe the current state: the store test needs a model and the loader test needs a
git-ignored file.

- [x] **Step 3: Make the store test hermetic**

Replace `VectorEmbedder` with a deterministic helper producing 1024-dimension
vectors, and `data/test_chromadb` with `tmp_path`. Assert exact counts. Keep
`test_embedder_generation` with the real embedder and give it an explicit skip:

```python
pytestmark_embedder = pytest.mark.skipif(
    not _model_available(),
    reason="sentence-transformers model unavailable: embedder test needs real weights",
)
```

- [x] **Step 4: Split the loader test**

Keep a hermetic fixture test as the primary check. Add the artifact-dependent test
with a named skip:

```python
requires_dataset = pytest.mark.skipif(
    not DATASET_PATH.exists(),
    reason=f"generated artifact absent: {DATASET_PATH} (data/ is git-ignored)",
)
```

When it runs, assert the **exact** document count read from the file rather than a
lower bound, and correct the docstring, which currently claims 282 while asserting
280.

- [x] **Step 5: Run verification**

Run: `pytest backend/tests/unit/test_chunker.py backend/tests/integration/test_vector_store.py -q -rs`

Expected: PASS, with the skip reasons printed by `-rs` naming the artifact and the
model.

- [x] **Step 6: Prove the store test needs no model**

Run it with the model unavailable — the condition under which it previously errored
or skipped — and confirm it still passes. Record the command and result.

- [x] **Step 7: Review checkpoint**

Review: both files, the skip reasons, and the model-independence demonstration.
Confirm no test was deleted, that the store test writes only under `tmp_path`, and
that the artifact test asserts an exact count.

Expected: the hermetic tests pass without `data/` and without model weights; the
artifact-dependent tests skip with the path or model named.

## Package Verification

Run in this order on the exact final worktree state:

1. `pytest backend/tests/unit` — expect pass
2. `pytest backend/tests/boundaries` — expect pass, with the new boundary tests present
3. `PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… pytest backend/tests/integration -rs` — expect zero failures, and the **skip inventory** printed
4. `cd frontend && npx vitest run` — expect pass
5. The four assertion mutation demonstrations from Task 2, each reported with its observed failure
6. The planted-file demonstration from Task 1 — four violations reported, then cleaned up
7. The `Mount` demonstration from Task 1 — the structural assertion fails
8. The store test run with the model unavailable — expect pass, not skip
9. `git status --short --untracked-files=all` — compare against the approved change set, and confirm **no production file** is modified

Report actual output, exit status, and every check that could not run. Check 3 needs
a live database; if unavailable, that is a limitation to disclose, not a pass. Note
that `pytest backend/tests/unit backend/tests/boundaries` cannot be run as one
command in this environment; run the directories separately and report both counts.

## Rollback

1. Revert the boundary sentinel to its previous scan lists and route literal.
2. Revert the four assertions in Task 2.
3. Revert both files in Task 3.

Nothing here writes data or changes production behaviour, so there is no
irreversible effect. No step requires a destructive Git operation.

## Completion Record

| Field | Value |
| --- | --- |
| Specification approval | **Approved 2026-09-11** — `docs/specs/2026-09-11-test-suite-truthfulness-design.md` v0.1, repository owner. |
| Plan approval | **Approved 2026-09-11** — repository owner, with the explicit instruction to implement immediately. |
| Execution | **Complete — Tasks 1, 2 and 3 implemented.** |
| Verification | **Run on the final worktree state.** All nine package checks pass, with one unreproduced transient and four discovered findings disclosed below. |
| Delivery gate | Repository owner only. No Git delivery is authorized by this plan. |

**Checked where evidence exists.** The 22 step checkboxes are ticked only because the evidence below exists.

### Per-task status

| Task | Implemented | Verified | Evidence |
| --- | --- | --- | --- |
| 1 — The sentinel covers what it claims to protect | Yes | **Yes** | `backend/tests/boundaries` → **16 passed** (was 8). Scan scope derived from the filesystem; planted-violation tests in a temporary tree; structural route assertion; `APPROVED_ROUTES` as one constant. |
| 2 — Assertions that discriminate | Yes | **Yes** | Readiness **5 passed**, auth **4 passed**, evaluation **3 passed**, migrations **30 passed**. Four mutation proofs below. |
| 3 — Hermetic tests and named skips | Yes | **Yes** | Chunker **5 passed**, vector store **3 passed** (0 skipped on this machine, because the weights are cached). |

### The facts that had to be established, and how they turned out

| # | Fact | Established value |
| --- | --- | --- |
| a | How the readiness aggregate follows from its components | Worst-state over components whose `reason_code != "disabled"`, precedence `not_ready` > `unknown` > `degraded` > `ready`; the route maps anything other than `ready` to `503` |
| b | Which double produces a below-threshold evaluation result | `DeterministicMockJudge(mean_score=1)`. **`DeterministicMockRuntime.hit_rate` is a dead parameter** — `retrieve` ignores it and always returns rank-1 `doc-001`, so the runtime cannot be made to miss |
| c | The exception the migration raises | `RuntimeError`, from `20260907_01_owned_conversations.py:179` (`"Conversation backfill hit a missing workspace"`) and `:191` (`"… owner mismatch"`). Both narrowed with `pytest.raises(RuntimeError, match=…)` |
| d | The exact document count a correct corpus contains | **Not hardcoded.** The artifact test derives it from the non-blank line count of the file it just read, so it cannot drift. The file holds 281 records on this machine |

### Package verification — actual results

| # | Check | Result |
| --- | --- | --- |
| 1 | `pytest backend/tests/unit` | **794 passed** (was 792; +2 net from splitting the loader test) |
| 2 | `pytest backend/tests/boundaries` | **16 passed** (was 8) |
| 3 | `pytest backend/tests/integration -rs` | **163 passed, 0 failed, 0 skipped** (was 160) |
| 4 | `cd frontend && npx vitest run` | **28 passed (3 files)** |
| 5 | Four assertion mutation proofs | all four **fail as expected** — see below |
| 6 | Planted-file demonstration | four violations reported while the probes existed; all removed afterwards |
| 7 | `Mount` demonstration | the structural assertion fails on a mounted sub-application |
| 8 | Store tests with the model cache hidden | **2 passed, 1 skipped**, the skip reason naming the missing path — the store test genuinely needs no model |
| 9 | `git status --short --untracked-files=all` | nothing staged or committed; **no production file modified** |

The change set matches the File Responsibility Map exactly: seven modified test files, no new test modules, and **zero production files** — which was this plan's stopping condition.

### Load-bearing proofs recorded

**Every new assertion was mutated and observed to fail.** Each mutation targeted the production behaviour the assertion describes, and each file was restored and verified byte-identical afterwards.

| Mutation | Target test | Result |
| --- | --- | --- |
| `_compose_status` no longer follows from its components | `test_readiness_route_returns_components_with_request_id` | **1 failed** |
| the readiness probe issues `SELECT 2` instead of `SELECT 1` | `test_readiness_route_healthy_returns_200` | **1 failed** |
| the migration raises `absent workspace` instead of `missing workspace` | `test_backfill_missing_workspace_fails_upgrade` | **1 failed** |
| the run-level answer-quality threshold is relaxed to `0.0` | `test_a_below_threshold_run_fails_and_names_the_gate` | **1 failed** |

**The scan reads the four previously-unscanned packages.** A file containing `import sqlite3` was planted in `orchestration`, `rag`, `preprocessing` and `memory`; the sentinel reported all four and failed. Removed afterwards, and a follow-up run passed.

**The store test needs no model.** With the model cache hidden, the two store tests passed and only the embedder test skipped, with the missing path in the reason. Before this change the same module could not run without weights at all.

### Discovered findings — reported, not fixed

1. **Two backend directories are implicit namespace packages.** `backend/rag` **and** `backend/rag/evaluation` have no `__init__.py` (PEP 420), so the first version of `_backend_packages()` — which required one — excluded exactly the packages the widened scope exists to cover. Caught by this plan's own scope test. The predicate now keys on the presence of Python files, not on `__init__.py`. A repository-wide sweep found **no other place** that derives package membership from `__init__.py`; the only remaining trace was this plan's own Step 3 sketch, which has been corrected and annotated so it cannot be copied back.
2. **`DeterministicMockRuntime.hit_rate` is a dead parameter.** It is accepted and stored but never read, so a caller asking for a 0.0 hit rate silently gets a perfect one. The below-threshold run therefore had to come from the judge. Not fixed: it is a test double, and changing it is a separate decision.
3. **The answer-quality threshold has two sources of truth.** `comparison.py` declares `GROUNDEDNESS_MINIMUM = 4.0` and `CORRECTNESS_MINIMUM = 4.0` as "D5 hard gates … exact thresholds, not config-driven", while the run-level gate in `runner.py:154` compares against the **literal `4.0`**. Mutating the constants has no effect on the run-level gate — this plan's first attempt at mutation 4 proved it. The two can drift apart. Not fixed: it is a production change, and this plan authorises none.
4. **The same `pytest.raises(Exception)` pattern exists outside the approved scope.** `backend/tests/unit/test_crawler_and_store.py:33` wraps a read-only store open in an unconstrained exception expectation. It is the same defect class as I50 but is not one of the eight findings this plan covers, so it is reported rather than fixed.

### Deviations from the approved plan

1. **The planted-violation tests build their probe in a temporary tree, not in the real packages.** The plan sketched planting inside `orchestration`, `rag`, `preprocessing` and `memory`. The specification's own Security section says no test writes into the repository, so the in-suite tests use `tmp_path` and the real-package demonstration was performed once, outside the suite, and reverted. The two together are the evidence: one proves the scope includes those packages, the other proves the scan reports what it is given.
2. **`_sqlite_violations` and `_workspace_violations` accept an optional package list.** Necessary for the temporary-tree tests, and it keeps the default repository-derived scope.
3. **The empty-file loader test asserts a raise, not an empty list.** The plan's sketch assumed `load_jsonl_dataset` returns `[]` for an empty file. It raises `ValueError`. The production behaviour is fail-closed and defensible, so the test was corrected to pin the real contract rather than the production code changed — and the finding is recorded here rather than silently absorbed.
4. **The below-threshold comparison test must pass `baseline_run_id`.** Without it `compare_runs` refuses as `INVALID` with `reason='Incompatible comparison contract: baseline_run_id'` and no gate ever runs. Discovered by the first failing run.
5. **The store test gained a second case** (`… does not accumulate across instances`) beyond the plan's sketch, pinning the exact-count property the shared path used to hide.

### Limits — disclosed, not claimed as passing

1. **One transient could not be reproduced.** An integration run executed **concurrently with the frontend suite** reported `150 passed, 13 errors`, with a traceback pointing into the backfill migration. The identical command run alone reported **163 passed, 0 errors, 0 skipped**. The errors were not captured in full and the mechanism is not established, so this is recorded as an unreproduced transient rather than explained away. If it recurs, it needs its own investigation. The suite was green on a clean run, and the database was verified healthy afterwards (head matches `ALEMBIC_HEAD`, 15 tables, RLS enabled and forced on `messages` and `conversations`).
2. **The structural route assertion reaches into `_IncludedRouter.original_router`**, a framework representation rather than a public contract. It is written to fail loudly if it discovers zero routes, so a dependency rename cannot turn it into a silent no-op — but it is a coupling, not a guarantee.
3. **The widened scan remains AST-only.** Dynamic imports and retired table names inside SQL strings are still invisible. This is a limit of the approach and is not implied to be solved.
4. **The artifact-dependent tests remain unverified on a clean checkout by design.** On this machine the corpus exists, so `test_loader_real_dataset` ran and asserted the exact count; on a clean checkout it would skip with the path named. Its skip reason is the disclosure.
5. **`data/` was not regenerated**, and no test writes there any more. `data/test_chromadb` is no longer referenced by any test.
6. **No test was deleted or relaxed.** One test was split into three (`test_loader_real_dataset` → a hermetic fixture test, an empty-file test, and the artifact test); every replacement assertion is at least as strong as the one it replaced.
7. **No production file was modified.** Verified in check 9.
8. **No Git delivery was performed.** Nothing was staged or committed.
