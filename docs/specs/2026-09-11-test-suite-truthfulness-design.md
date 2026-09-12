# Test Suite Truthfulness: Sentinel Coverage, Assertion Strength, and Artifact Dependence

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-11 |
| Change class | Level 2 - Bounded Change |
| Decision owner | Repository owner |
| Scope | The boundary sentinel's coverage and route assertion, four assertions that cannot distinguish a healthy system from a broken one, and two tests that depend on git-ignored artifacts or a live model. Bounded to `backend/tests/`; no production module changes. |
| Related issue | None filed. Authorization basis is the repository owner's selection of workstream W7 from the owner-requested triage of the 2026-09-11 code review. |
| Superseded document | Not applicable |

## Summary

Eight findings from the 2026-09-11 review concern the test suite's ability to tell the truth: a boundary sentinel that scans five of nine packages, a route assertion that is both too strict and too narrow, assertions that cannot distinguish a healthy system from a degraded one, and two tests whose result depends on artifacts that are not in the repository.

**Five were verified as stated. Three were overstated, and this specification corrects them rather than repeating the claim.**

| # | Finding | Verified as stated? |
| --- | --- | --- |
| I47 | The boundary scan covers 5 of 9 packages | **Yes** — `orchestration`, `rag`, `preprocessing` and `memory` (outside `write_pipeline`) are unscanned |
| I48 | The route assertion is a hardcoded exact-set comparison | **Yes** — and it cannot see a `Mount`, which `openapi()` does not enumerate |
| I49 | The readiness assertion cannot fail | **No, overstated.** A `500` fails it. The real defect is that it cannot distinguish `ready` from `degraded`, and its mock engine accepts any SQL, so the probe's statements are never validated |
| I50 | `pytest.raises(Exception)` accepts a typo in the test's own SQL | **Yes** |
| I51 | A valid token is accepted even on a `500` | **No, wrong.** `500` is not in `(200, 503)`, so it fails. The real defect is a redundant second assertion and the same inability to distinguish `ready` from `degraded` |
| I52 | The vector-store test writes to a shared repository path with no skip guard | **Partly.** The path and the missing guard are real. `added_count == 2` is a genuine assertion, so "passes even if nothing was added" is wrong |
| I53 | Perfect fakes make the comparison gates unverifiable | **Yes** as a detection claim; "cannot fail" is imprecise |
| I54 | The chunker test depends on a real data file | **Yes, and worse than stated.** `data/` is git-ignored, so the test cannot pass on a clean checkout at all |

The corrections matter for the work: three of the eight need their assertions *strengthened so they can distinguish outcomes*, not merely repaired so they can fail.

## Context

`backend/tests/boundaries/test_clean_break_boundaries.py` is the clean-break sentinel. Its docstring states its purpose: to ensure no SQLite or schema-registry imports exist in mounted backend code, that no retired surface is imported, that legacy configuration options are removed, and that only approved routes are mounted.

Its import scan is driven by two module-level lists:

```python
MOUNTED_BACKEND_DIRS = [app, conversations, observability, security, storage]
MOUNTED_BACKEND_DIRS_WITH_MEMORY = [*MOUNTED_BACKEND_DIRS, memory/write_pipeline]
```

`backend/` contains nine packages. Four are absent from both lists: `orchestration`, `rag`, `preprocessing`, and `memory` outside `write_pipeline`. The scan is also AST-only, so `importlib.import_module`, `__import__`, and a retired table name inside a SQL string are invisible to it.

Its route check compares the mounted surface against a literal set of eight routes with `mounted_routes == approved_routes`, where `mounted_routes` comes from `app.openapi()["paths"]`.

Four assertions elsewhere cannot distinguish a working system from a broken one:

- `backend/tests/integration/test_ops_readiness_api.py:60-62` accepts any of `200` or `503`, and any member of the full readiness enum. A deployment reporting `degraded` is indistinguishable from one reporting `ready`, and the healthy-path test's `MockEngine` returns `(1,)` for every statement, so no probe query is ever validated.
- `backend/tests/integration/test_auth_api.py:54-55` asserts `in (200, 503)` and then `!= 401`, which the first assertion already guarantees.
- `backend/tests/integration/test_rag_evaluation_flow.py:236-237` runs the evaluation with `DeterministicMockRuntime(hit_rate=1.0)` and `DeterministicMockJudge(mean_score=5)`, so every retrieval hits and every answer scores the maximum. The gates are asserted to be unviolated, which is inevitable for any gate implementation given those inputs.
- `backend/tests/integration/test_postgres_migrations.py:211` asserts `pytest.raises(Exception)` around a migration that must fail closed, which accepts any error including one caused by a mistake in the test's own setup SQL.

Two tests depend on things the repository does not contain:

- `backend/tests/integration/test_vector_store.py` writes to `data/test_chromadb`, a shared path under a git-ignored directory, and asserts `store.count() >= 2` against a collection it never clears. It also constructs `VectorEmbedder`, which loads `sentence-transformers` and torch, with no skip guard.
- `backend/tests/unit/test_chunker.py:12-14` asserts a git-ignored dataset exists and that it has `>= 280` documents, while its docstring claims "all 282 documents".

**One structural fact changes the design.** `ChromaVectorStore` does not need an embedder: `add_chunks(chunks, embeddings)` and `search_similar(query_embedding, top_k)` take vectors. The test's `VectorEmbedder` calls exist only to produce vectors, so the store test can be hermetic. Only `test_embedder_generation` genuinely needs the model.

## Users

1. **Repository owner** — relies on the suite to report the truth before authorising changes, and on the sentinel to hold the clean break.
2. **Reviewer** — needs a green suite to mean something, because the whole review process is built on it.
3. **Engineer implementing the remaining workstreams** — W3, W4, W5 and W6 will each claim verification; a suite that cannot detect a regression makes those claims worthless.
4. **Future contributor on a clean checkout** — must be able to run the suite without first generating artifacts that are not in the repository.
5. **Future contributor adding a route** — must be told, by the sentinel, that a new route is a deliberate act rather than an omission.

## Problem Statement

**The sentinel does not cover the code it claims to protect.** Its purpose is to hold the clean break across mounted backend code. Four of nine packages are unscanned, including `rag` and `orchestration`, which are on the request path. A SQLite import introduced in `orchestration` would not fail the suite.

**The route assertion is simultaneously too strict and too narrow.** It fails on a legitimate new route, which trains a reader to edit the sentinel rather than read it. It also reads only `app.openapi()`, so a surface mounted in a way OpenAPI does not enumerate is invisible.

**Four assertions cannot distinguish success from a specific failure.** They accept any member of a status set that includes both the healthy and the degraded outcome. A green suite therefore cannot tell the owner whether readiness is reporting honestly, whether a gate is enforced, or whether a migration fails for the intended reason.

**Two tests are not runnable where the repository is the only input.** `data/` is git-ignored, so the chunker test fails on every clean checkout, and the vector-store test writes to a shared path under that directory and needs a model with no skip guard. Their results depend on machine state, which makes them unreliable in both directions: they can pass because of leftover data and fail because of a fresh clone.

**Why now.** The remaining workstreams (W3 outbox/worker, W4 retrieval/generation, W5 frontend, W6 preprocessing/evaluation) will each be verified by this suite. Fixing the suite after those claims are made means re-verifying them all.

## Goals

1. The import scan covers every mounted backend package, and its scope is derived from the repository rather than a hand-maintained list that can fall behind.
2. The route sentinel fails on a route that OpenAPI does not enumerate, and its failure message tells the reader exactly what to do.
3. Every assertion that currently accepts both a healthy and a degraded outcome distinguishes them, or states explicitly which outcome it expects and why.
4. A test's own setup cannot be mistaken for the failure it is asserting.
5. No test depends on a git-ignored artifact or a live model to produce a meaningful result, and where such a dependency is unavoidable the skip is explicit and named.
6. The suite remains green on a clean checkout with no `data/` directory and no model weights.

## Non-goals

1. Any change to production code. If a task needs one, the approved design was wrong and the work stops.
2. Adding tests for behaviour that is not already claimed to be covered. This specification repairs existing assertions; it does not extend coverage into untested features. (W3–W6 own those.)
3. Replacing the readiness probe's real behaviour with a test double. The mock is made stricter, not more permissive.
4. Making the boundary sentinel risk-based. The owner chose to keep it strict with a single source of truth, because a new route in this repository is a governed act.
5. Any change to the RAG evaluation harness's production code, its gates, or its fixtures.
6. Deleting any test. Every test named here is repaired, split, or given an explicit skip — none is removed.
7. Enabling the memory write pipeline.

## Assumptions

1. `data/` is intentionally git-ignored (`.gitignore:29`), so artifacts under it are generated and must not be required by a test that claims to run on a checkout.
2. A legitimate new route in this repository requires a specification and an approved plan, so requiring a deliberate edit to the approved route set is consistent with the repository's governance rather than an obstacle to it.
3. `app.openapi()["paths"]` is the canonical enumeration of the product surface, and anything reachable but absent from it is a defect worth failing on.
4. `_IncludedRouter.original_router.routes` is the supported way to see the routes inside an included router in this FastAPI version; verified rather than assumed.
5. The readiness aggregate is a function of its components, so asserting that the reported aggregate agrees with the components is a real invariant rather than a restatement.
6. `DeterministicMockRuntime` and `DeterministicMockJudge` are test doubles whose job is to be deterministic; making one of them produce a below-threshold result is a change to the test, not to the harness.

## User and System Flows

**Flow 1 — A contributor adds a route.** The sentinel fails, and its message names the file, the constant to update, and the fact that a new route needs a specification. The contributor updates one constant deliberately.

**Flow 2 — A contributor reintroduces a retired import.** The scan fails, including in `orchestration`, `rag`, `preprocessing` and `memory`.

**Flow 3 — A contributor mounts a surface OpenAPI cannot see.** The structural assertion fails on the mount, rather than the route set comparison silently not noticing it.

**Flow 4 — Readiness reports `degraded` while claiming to be healthy.** The assertion fails, because the reported aggregate no longer matches its components. Today it passes.

**Flow 5 — A migration fails for the wrong reason.** The test fails at its own setup, because the setup asserts the orphan row was inserted, and only then asserts the narrow exception type.

**Flow 6 — A clean checkout runs the suite.** The hermetic tests run and can fail; the artifact-dependent test skips with a message naming the missing artifact.

## Behavioral and Data Contracts

### Import scan scope (`test_clean_break_boundaries.py`)

- **Produces:** the scanned package set derived from the repository, not a hand-maintained list.
- **Contract:** every package directory under `backend/` that is not `tests` is scanned. A package added later is covered without an edit. The existing narrow exception for `backend/observability/readiness.py` importing `sqlite3` read-only is preserved and remains pinned by its own test.

### Route sentinel (`test_clean_break_boundaries.py`)

- **Produces:** a single module-level constant holding the approved route set, and a structural assertion over the router tree.
- **Contract:** the comparison remains exact. The failure message names the constant to edit and states that a new route requires a specification.
- **Contract:** the router tree is walked recursively, and any `Mount` — or any route type other than `Route` and the included-router wrapper — fails the assertion, because OpenAPI does not enumerate it. The included-router case is recursed through `original_router.routes`.
- **Contract:** the documentation routes and `GET /health` remain permitted, and remain the only paths outside the API prefix.

### Readiness assertions (`test_ops_readiness_api.py`)

- **Produces:** an assertion that the reported aggregate agrees with its components, and a mock engine that validates the statements it is given.
- **Contract:** the expected HTTP status is derived from the reported aggregate — `200` for `ready`, `503` otherwise — so a `degraded` report can no longer satisfy a healthy-path expectation.
- **Contract:** the mock engine fails on an unrecognised statement rather than returning a default, so a probe query that changes shape is caught.

### Token acceptance (`test_auth_api.py`)

- **Produces:** an assertion about what a valid token must achieve.
- **Contract:** the redundant `!= 401` is replaced by a statement that cannot be satisfied by the first assertion — the response must not be an authentication rejection, and the status must agree with the reported readiness aggregate.

### Evaluation flow (`test_rag_evaluation_flow.py`)

- **Produces:** a second evaluation run whose inputs are below threshold.
- **Contract:** at least one run uses a runtime or judge double configured to miss, and the test asserts the resulting state is a failure and names the gate that fired. The existing passing run is kept, because a gate that always fails is as uninformative as one that never does.

### Migration failure (`test_postgres_migrations.py`)

- **Produces:** a narrowed exception expectation and a validated setup.
- **Contract:** the setup asserts the orphan row exists before the upgrade is attempted, so a mistake in the setup SQL fails at the setup. The exception type is the narrowest one the migration actually raises, determined by observation rather than guessed.

### Vector store (`test_vector_store.py`)

- **Produces:** a hermetic store test and a separately-marked embedder test.
- **Contract:** the store test supplies deterministic 1024-dimension vectors, uses a `tmp_path` persist directory, and therefore needs no model and no skip guard. The embedder test keeps the real `VectorEmbedder` and skips explicitly when the model is unavailable.
- **Contract:** the store test asserts an exact count on a fresh directory rather than a lower bound on a shared one.

### Dataset loader (`test_chunker.py`)

- **Produces:** a hermetic loader test and an artifact-dependent test.
- **Contract:** the loader is exercised against a small fixture written into `tmp_path`, so its behaviour is asserted where the repository is the only input. The artifact-dependent test skips explicitly when `data/processed/` is absent and, when it runs, asserts the exact document count rather than a lower bound.

## Errors and Edge Cases

1. **A new backend package is added.** Expected: it is scanned automatically.
2. **`backend/tests` is under `backend/`.** Expected: excluded explicitly, so the suite does not scan itself.
3. **A package directory contains no Python files.** Expected: no failure; an empty scan is not an error.
4. **A legitimate route is added.** Expected: the sentinel fails with an actionable message. This is intended.
5. **A `Mount` is added.** Expected: the structural assertion fails and names it.
6. **The router wrapper's internal attribute changes name.** Expected: the structural assertion fails loudly rather than silently scanning nothing. The assertion must fail if it discovers zero routes.
7. **Readiness reports `ready` but a component is `not_ready`.** Expected: the assertion fails.
8. **The mock engine receives an unexpected statement.** Expected: it fails, naming the statement shape.
9. **The model is unavailable.** Expected: the embedder test skips with a message naming the model; the store test still runs, because it needs no model.
10. **`data/processed/` is absent.** Expected: the artifact test skips with a message naming the path; the hermetic loader test still runs.
11. **`data/processed/` exists with a truncated file.** Expected: the artifact test fails on the exact count, which is the defect the loose bound currently hides.
12. **A below-threshold evaluation run.** Expected: the test asserts a failure state and names the gate.

## Security and Privacy

**Trust boundaries.** Unchanged. This specification touches no production module, so no runtime trust boundary moves.

**Authorization.** No change. The auth test's assertion is strengthened, not relaxed; it continues to assert that a valid token is accepted and that the token value never appears in a response.

**Data classification.** Improved in one respect: the vector-store test currently writes to a shared directory under `data/`, and after this change it writes only to a pytest temporary directory. No test writes into the repository.

**Privacy.** No change. No test reads or logs user content. The readiness and evaluation tests use synthetic values, and the migration test's rows carry no user data.

**Integrity of the verification claim.** This is the substance of the change. A suite whose assertions cannot distinguish outcomes produces a verification claim that is not supported by evidence, which is a governance risk rather than a runtime one.

## Observability and Operations

- No production logging, event, or metric changes.
- The sentinel's failure messages become operational: they name the constant to edit and the reason a new route needs one, so the failure teaches instead of merely blocking.
- The artifact-dependent skips are named in the skip reason, so a reader can see what is unverified in their environment rather than reading a green run as full coverage.
- The plan requires the final skip inventory to be reported, because the count of skips is the measure of how much this suite does not verify locally.

## Capacity, Latency, and Cost

- **Latency.** The suite gets faster. Removing the real embedder from the vector-store test removes a model load; making the loader test hermetic removes a 281-document parse. The widened import scan adds a single AST parse per file across four more packages, which is milliseconds.
- **Capacity.** No new fixtures beyond two small ones written into temporary directories.
- **Cost.** No model call in the store test. The evaluation test gains one additional in-process run with no external calls.
- **Measurement.** The plan requires the before-and-after suite counts and durations to be reported, and the final skip inventory, since the claim is that the suite becomes both stronger and cheaper.

## Compatibility and Staged Migration

**Coexistence.** Not applicable in the usual sense: this change is confined to the test suite, which is not deployed. No production behaviour changes, so there is no rollout sequencing.

**Sequencing.** The three groups are independent of one another and of the production workstreams. They should land before W3–W6, because those workstreams will cite this suite as evidence.

**Rollout gate.** The suite passes on a checkout with no `data/` directory present, and the sentinel fails when a `Mount` is added.

**Rollback boundary.** Reverting the commit restores the previous tests exactly. Nothing here writes data or changes production behaviour, so there is no irreversible effect.

## Failure and Recovery

| Failure | Behaviour | Recovery |
| --- | --- | --- |
| A new route is added without updating the sentinel | The sentinel fails, naming the constant | Update the constant deliberately, with the specification the route requires |
| A retired import appears in `rag` or `orchestration` | The widened scan fails | Remove the import; the sentinel did its job |
| A route is mounted invisibly to OpenAPI | The structural assertion fails | Decide whether the surface is intended; if so, it needs its own change |
| A probe statement changes shape | The strict mock fails, naming the statement | Update the mock and confirm the probe's new statement is correct |
| The model is unavailable | The embedder test skips, named | No recovery needed; the store test still runs |
| `data/` is absent | The artifact test skips, named | Generate the artifact if the full check is wanted |
| A package is added under `backend/` | Scanned automatically | No recovery needed |

## Required ADRs

**None.** This change is confined to test code. It makes no decision that other components depend on: the sentinel's scope, the strength of an assertion, and whether a test needs a model are all properties of the tests themselves. No production interface, contract, schema, or module boundary changes. Recording an ADR here would promote a test repair into an architecture decision and misrepresent the repository's decision history.

## Alternatives Considered

### Repair in place: widen the scan, strengthen the assertions, make two tests hermetic — the selected approach

**Approach.** Three independent groups. Derive the scan scope from the repository. Keep the route comparison exact, move the approved set to one named constant, and add a structural assertion for anything OpenAPI cannot enumerate. Strengthen the four weak assertions so they distinguish outcomes. Make the store and loader tests hermetic, and split out the genuinely artifact-dependent checks with explicit skips.

**Benefits.** Fixes each finding at its cause. The suite becomes able to fail for the right reason and, in three cases, able to fail at all in a way it currently cannot. Two tests stop depending on machine state. No production code changes, so no runtime risk.

**Costs.** The sentinel still requires an edit when a legitimate route is added, which is a deliberate friction. The structural assertion reaches into a framework attribute that could be renamed by a dependency upgrade, which is why it must fail when it discovers nothing.

**Selected because** it is the only alternative that repairs the assertions rather than deleting or relaxing them, and because it keeps the sentinel strict, which the owner chose on the grounds that a new route in this repository is a governed act.

### Mark the weak tests as expected-to-pass and add coverage separately

**Approach.** Leave the assertions as they are, and add new, stronger tests alongside them.

**Benefits.** Nothing existing is touched, so no existing test can be broken by the change. Smallest diff.

**Costs.** The weak assertions remain, and a reader cannot tell from the file which assertion is load-bearing. The suite grows while its weakest parts stay weakest, and the review's finding — that a green run does not mean what it appears to mean — survives untouched.

**Rejected because** it addresses the symptom. The finding is that specific assertions do not discriminate; adding more assertions elsewhere does not make those ones discriminate.

### Replace the boundary sentinel with a risk-based check

**Approach.** Drop the exact route comparison. Assert instead that no forbidden path segment is mounted and that every mounted route rejects an unauthenticated request.

**Benefits.** No false positive on a legitimate new route. Stronger on the risk that matters most, because it would catch an unguarded route. Simpler to maintain.

**Costs.** It loses the ability to detect a **new public surface mounted quietly**, which is exactly what a clean-break sentinel exists to prevent. A route that is authenticated but unintended would pass.

**Rejected because** the owner chose to keep the sentinel strict: in a repository where every new route requires a specification, a sentinel that forces a deliberate edit is doing its job rather than obstructing.

### Give the two artifact-dependent tests skip guards only

**Approach.** Add `skipif` guards and tighten the assertions, leaving the structure alone.

**Benefits.** Smallest possible diff. Both tests stop failing on a clean checkout.

**Costs.** The store test would still need a real model, so it would skip in any constrained environment — the same class of skip that currently hides coverage. The loader's real behaviour would still only be exercised when an artifact happens to be present.

**Rejected because** the store test does not need a model at all, which is a fact this specification established by reading the store's interface. Accepting a skip where a hermetic test is available trades a real check for an absent one.

## Current-state Evidence

| Claim | Evidence path | Verified how |
| --- | --- | --- |
| The import scan covers 5 of 9 packages | `backend/tests/boundaries/test_clean_break_boundaries.py:33-45` | Direct read; `backend/` contains `app`, `conversations`, `memory`, `observability`, `orchestration`, `preprocessing`, `rag`, `security`, `storage`, `tests` |
| The route assertion is an exact-set comparison | `test_clean_break_boundaries.py:304-314` | Direct read |
| A `Mount` is absent from `openapi()` | Recursive walk of `app.routes` on 2026-09-11 printed a `Mount` branch that the OpenAPI enumeration does not include | Executed |
| The included-router wrapper exposes its inner routes | Same probe: `_IncludedRouter.original_router.routes` yielded 1, 1, 1 and 5 routes = 8 total, matching the 8 OpenAPI operations | Executed |
| Inner route paths do not carry the API prefix | Same probe: the walk yielded `/chat`, `/conversations`, `/ops/readiness`, while OpenAPI yields `/api/v1/...` | Executed |
| The readiness assertion accepts both outcomes | `backend/tests/integration/test_ops_readiness_api.py:60-62` | Direct read |
| The readiness mock accepts any statement | `test_ops_readiness_api.py:77-92`, `execute` returns `MagicMock(first=lambda: (1,))` for any statement that is not `alembic_version` | Direct read |
| A `500` **does** fail the readiness and token assertions | `assert response.status_code in (200, 503)` excludes `500` | Direct read; **corrects the review's I49 and I51 wording** |
| The token assertion's second line is redundant | `test_auth_api.py:54-55`: `401` is not in `(200, 503)` | Direct read |
| The evaluation test's doubles are perfect by construction | `test_rag_evaluation_flow.py:236-237`, `DeterministicMockRuntime(hit_rate=1.0)`, `DeterministicMockJudge(mean_score=5)` | Direct read |
| The migration test accepts any exception | `test_postgres_migrations.py:211` | Direct read |
| The vector store needs no embedder | `ChromaVectorStore.add_chunks(chunks, embeddings)` and `search_similar(query_embedding, top_k)` | Signature read via `inspect` |
| The vector-store test writes to a shared repository path | `test_vector_store.py:9,23-26,58` | Direct read |
| `data/` is git-ignored | `git check-ignore -v data/processed/vietnam_travel_raw.jsonl` → `.gitignore:29:data` | Executed |
| The dataset is not tracked | `git ls-files --error-unmatch data/processed/vietnam_travel_raw.jsonl` → no match | Executed |
| The chunker test's bound contradicts its docstring | `test_chunker.py:11-14`, docstring "all 282 documents", assertion `>= 280` | Direct read |

**Not verified.** The number of documents a correctly generated dataset contains was not measured, so the exact count the artifact-dependent test should assert is not stated here; the plan requires it to be derived from the file at implementation time rather than guessed. Whether `DeterministicMockRuntime` and `DeterministicMockJudge` expose a parameter that produces a below-threshold result was not read; the plan requires it to be established before that task's test is written. The suite's current duration and skip count were not measured for this specification; the plan requires them as the before-and-after baseline.

## Components and Dependency Direction

```
backend/tests/boundaries/test_clean_break_boundaries.py
   │  scan scope derived from backend/ ; route sentinel + structural assertion
   ▼
backend/tests/integration/{test_ops_readiness_api,test_auth_api,test_postgres_migrations,
                           test_rag_evaluation_flow,test_vector_store}.py
   │  stronger assertions ; hermetic store test
   ▼
backend/tests/unit/test_chunker.py
   │  hermetic loader test + artifact-dependent test
```

**Allowed dependency direction.** Unchanged. No test gains a dependency on a production module it does not already import, and no production module is touched. The only new dependency is `tmp_path`, which pytest already provides.

**Ownership.** Each test file owns its own assertions. The sentinel owns the repository-wide invariants, which is why its scan scope is derived from the repository rather than declared per test.

## Data Flow and Lifecycle

**Sentinel lifecycle.** Runs on every suite invocation, on a checkout. Its scan scope is computed from the filesystem, so it stays current without maintenance.

**Hermetic test lifecycle.** Builds its input in a temporary directory, asserts, and leaves nothing behind. Repeatable and independent of machine state.

**Artifact-dependent test lifecycle.** Skips when the artifact is absent, with the path named. When it runs, it asserts an exact property so that a partial artifact is a failure rather than a pass.

**Assertion lifecycle.** An assertion that accepts both a healthy and a degraded outcome is replaced by one that names which it expects. Where both are legitimate, the assertion compares the reported outcome against what the components imply, which is a real invariant.

## Approval Record

| Field | Value |
| --- | --- |
| Version | 0.1 |
| Status | Approved — 2026-09-11, repository owner |
| Approver role | Repository owner |
| Date | 2026-09-11 |
| Authorization boundary | Authorizes preparation and approval of the implementation plan at `docs/plans/2026-09-11-test-suite-truthfulness-implementation.md`. Implementation is authorized only by the separate plan approval recorded below. |

**Approved 2026-09-11 by the repository owner, together with Plan E.** The approval authorizes execution of the three tasks of that plan.

**What this approval does NOT authorize.** Deleting or relaxing any test; any change to production code; changes to the RAG evaluation harness's gates or fixtures; extending coverage into untested features owned by W3–W6; and any Git delivery.

**The owner approved this specification knowing that three of the eight findings were overstated in the review that prompted the work.** The corrections are recorded in the table above and are part of what was approved.

**One consequence of this approval must be understood as part of it.** Three of the eight findings were overstated in the review that prompted this work. This specification corrects them, and the corrections make three tasks smaller than the review implied while leaving them real: the readiness, token and evaluation assertions need to *discriminate between outcomes*, not merely to become able to fail. If the owner's intent was to fix all eight as literally described, that intent cannot be satisfied, because two of the eight descriptions do not match the code.
