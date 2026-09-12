# Configurable Model Provider Endpoint Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence. Each task ends with a review checkpoint; do not begin
> the next task until the checkpoint condition holds.

**Goal:** Make the model provider endpoint an environment setting, so a deployment can point the chat path and the LLM judge at any OpenAI-compatible provider without editing source.

**Architecture:** One behavioural line in `backend/app/config.py`: the setting reads the environment and has **no default**. Both consumers read it through `settings`, so neither is edited. Documentation and four focused tests accompany it.

**This is not behaviour-preserving.** An unset variable stops working, so the migration sequencing — set the variable before the change reaches an environment — is part of the change rather than an operational afterthought.

**Tech Stack:** Python 3 / pydantic / pytest / `openai` 3.3.1

**Spec:** `docs/specs/2026-09-11-configurable-model-provider-endpoint-design.md` v0.1

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-11 |
| Approved specification | `docs/specs/2026-09-11-configurable-model-provider-endpoint-design.md` v0.2 — **Approved 2026-09-11** by the repository owner, together with this plan. |
| Execution owner | Implementation agent |
| Decision owner | Repository owner |
| Scope | One setting in `backend/app/config.py`, its documentation, and its test |
| Verification | `pytest backend/tests/unit/test_config.py`; the two consumer suites; the full unit and integration suites; a live check against the configured endpoint performed by the operator |

## Global Constraints

1. Every persistent repository change requires a written specification and an approved implementation plan (`AGENTS.md`). The specification and this plan were approved by the repository owner on 2026-09-11. Level 2 requires no ADR, and the specification records why.
2. The repository owner creates or selects branches and decides when to stage, commit in the primary working tree, push, open a PR, merge, and release. No Git delivery is authorized by this plan.
3. The working tree is dirty and large. Read a dirty file before touching it and work with the existing edits rather than reverting them.
4. **Only the one setting changes behaviour.** The setting's name is unchanged and both consumers are unedited. If a task appears to need a consumer change, the approved design was wrong and the work stops for review.
5. **The setting has no default.** Do not add a fallback vendor address, in any form. The owner ruled it out, and the specification records the rejected alternative that would have kept one.
6. **Strip the value.** Whitespace must not survive into the base URL: the OpenAI SDK percent-encodes `"   "` into `%20%20%20/`, which is a malformed endpoint rather than an empty one.
7. **Do not claim the SDK substitutes its own endpoint.** It does so only when `base_url` is *omitted*; an explicit empty string is kept. Measured on `openai` 3.3.1. An earlier draft of this plan asserted the opposite and the specification's version 0.2 withdraws that claim.
8. **This is not behaviour-preserving, and the migration is part of the change.** Today an unset variable selects GitHub Models; after this change the first chat turn fails. The Completion Record must state that the variable has to be set in an environment *before* the change reaches it, and the operator-facing documentation must say the setting is required.
9. **No credential change.** `GITHUB_TOKEN` is neither renamed nor wrapped in `SecretStr`. Five readers plus the artifact redaction list depend on its current shape.
10. **No fail-fast check for a missing endpoint, and no https-only guard.** Both are recommended in the specification as separate changes and are deliberately not bundled. Do not add them.
11. **Do not make any other setting configurable.** `LLM_MODEL` and `GITHUB_TOKEN` already are; nothing else in this change.
12. The test must exercise the **environment path**. Constructing `Settings(GITHUB_MODELS_URL=...)` proves nothing, because pydantic accepts an explicit override for any field whether or not the field reads the environment.
13. Behaviour changes use a red-green-refactor cycle. The task states the failing test first.
14. Never expose secrets, credentials, tokens, or sensitive personal data in code, logs, commands, evidence, or documentation. The endpoint is not a secret; the credential is, and it is not touched.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/app/config.py` | Read `GITHUB_MODELS_URL` from the environment, treating blank and whitespace as unset | — |
| `backend/tests/unit/test_config.py` | Prove the environment variable is honoured, and that unset and blank fall back to the default | Task 1 |
| `.env.example` | Document the setting beside the existing provider entries | — |
| `DEVELOPMENT.md` | Add the setting to the environment-variable table | — |

**No consumer file appears here.** `backend/rag/generation/llm.py` and `backend/rag/evaluation/judge.py` already read `settings.GITHUB_MODELS_URL` and must not be edited.

## Task 1: Make the endpoint configurable

**Files:**

- Modify: `backend/app/config.py:29`
- Test: `backend/tests/unit/test_config.py` (extend the existing module)
- Modify: `.env.example`, `DEVELOPMENT.md`

**Interfaces:**

- Produces: `Settings.GITHUB_MODELS_URL: str`, read from the environment
- Consumes: nothing new

- [x] **Step 1: Write the failing tests**

Add to `backend/tests/unit/test_config.py`. The existing module builds `Settings`
with explicit keyword arguments, which cannot observe the environment; these three
must go through `monkeypatch` instead.

```python
def test_models_url_reads_the_environment(monkeypatch):
    """The endpoint is deployment configuration, not a source constant."""
    monkeypatch.setenv("GITHUB_MODELS_URL", "https://api.example.test/v1")
    assert Settings().GITHUB_MODELS_URL == "https://api.example.test/v1"


def test_models_url_has_no_default(monkeypatch):
    """An unset variable yields the empty string, not a vendor address.

    This is the behaviour change: today an unset variable selects GitHub Models.
    """
    monkeypatch.delenv("GITHUB_MODELS_URL", raising=False)
    assert Settings().GITHUB_MODELS_URL == ""


def test_models_url_strips_whitespace(monkeypatch):
    """Whitespace must not survive into the base URL.

    A bare `os.getenv` without stripping yields `"   "`, and the OpenAI SDK
    percent-encodes that into `%20%20%20/` — a malformed endpoint rather than an
    empty one.
    """
    for blank in ("", "   ", "\t"):
        monkeypatch.setenv("GITHUB_MODELS_URL", blank)
        assert Settings().GITHUB_MODELS_URL == "", repr(blank)

    monkeypatch.setenv("GITHUB_MODELS_URL", "  https://api.example.test/v1  ")
    assert Settings().GITHUB_MODELS_URL == "https://api.example.test/v1"
```

Add one more, which is a **guard rather than a red test** — it documents a measured
SDK behaviour so a future reader does not repeat the mistake this plan made:

```python
def test_an_empty_endpoint_still_constructs_a_client():
    """The application must still start; only a request fails.

    Verified against `openai` 3.3.1: construction succeeds with an empty base URL
    and the failure appears on the first call as `APIConnectionError`. The SDK
    substitutes its own endpoint only when `base_url` is omitted, never when it is
    explicitly empty.
    """
    from openai import OpenAI

    client = OpenAI(api_key="sk-placeholder", base_url="")
    assert client.base_url == ""
```

- [x] **Step 2: Run verification**

Run: `pytest backend/tests/unit/test_config.py -q`

Expected: FAIL. `test_models_url_has_no_default` fails because the literal still returns the vendor address, and `test_models_url_strips_whitespace` fails for the same reason. The client-construction guard passes before and after — it is a documentation guard, not a red test.

- [x] **Step 3: Make the setting env-driven, with no default**

`backend/app/config.py:29`:

```python
GITHUB_MODELS_URL: str = os.getenv("GITHUB_MODELS_URL", "").strip()
```

The `.strip()` is required and follows the idiom already used by `database_dsn()`
in the same file (`(self.DATABASE_URL or "").strip()`). Without it, a
whitespace-only value survives into the base URL and the SDK percent-encodes it
into `%20%20%20/`.

There is **no** `or` fallback. That is the owner's decision and the source of the
behaviour change this plan carries: an unset variable now yields the empty string,
and the first model call raises `APIConnectionError: Connection error.`

- [x] **Step 4: Document the setting**

`.env.example`: add the setting beside the existing `GITHUB_TOKEN` and `LLM_MODEL`
entries, with a comment stating that the endpoint **must speak the OpenAI
chat-completions protocol** and that it is **required — there is no default**, so
leaving it unset makes the first model call fail with a connection error.

`DEVELOPMENT.md`: add a row to the environment-variable table beside the existing
`GITHUB_TOKEN` row, matching that table's column shape, and mark it required.

Neither may state a default, because the code has none. If either document
currently implies the endpoint is optional, correct it.

- [x] **Step 5: Run verification**

Run: `pytest backend/tests/unit/test_config.py backend/tests/unit/test_llm_generator.py backend/tests/unit/test_evaluation_judge.py -q`

Expected: PASS. The two consumer suites are included because they are the callers
of the changed setting; neither should need an edit.

- [x] **Step 6: Confirm the consumers were not edited**

Run: `git diff --stat backend/rag/generation/llm.py backend/rag/evaluation/judge.py`

Expected: no output. A change here means the design was wrong.

- [x] **Step 7: Review checkpoint**

Review: the setting, the three tests, the two documentation entries, and the
consumer diff. Confirm the default is byte-identical to the previous literal, that
blank and whitespace fall back rather than reaching the SDK, that no consumer file
changed, and that no other setting was touched.

Expected: the config suite passes; the consumers are unmodified; the documented
default matches the code.

## Package Verification

Run in this order on the exact final worktree state:

1. `pytest backend/tests/unit` — expect pass
2. `pytest backend/tests/boundaries` — expect pass, unchanged count
3. `PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… pytest backend/tests/integration` — expect zero failures and zero skips
4. `cd frontend && npx vitest run` — expect pass
5. `git diff --stat backend/rag/generation/llm.py backend/rag/evaluation/judge.py` — expect no output
6. `grep -n "GITHUB_MODELS_URL" backend/app/config.py` — expect exactly one line, and it reads the environment with no fallback
7. `python -c "from backend.app.config import settings; print(repr(settings.GITHUB_MODELS_URL))"` with the variable unset — expect `''`, proving no default survives in the source
8. `grep -rn "GITHUB_MODELS_URL" .env.example DEVELOPMENT.md` — expect both to name the setting, state that it is required, and state no default
9. `git status --short --untracked-files=all` — compare against the approved change set

Report actual output, exit status, and every check that could not run. Note that
`pytest backend/tests/unit backend/tests/boundaries` cannot be run as one command
in this environment; run the directories separately and report both counts.

**Check 3 is the one that matters most.** Removing a default is the kind of change
that silently breaks a suite which happened to rely on it, so the full integration
run is the evidence that nothing did. If it fails, that is a finding to report, not
a test to adjust.

**Not a verification step, and not claimable as one.** No call is made to any
third-party endpoint by this plan. Whether a configured provider accepts this
application's request shape — `temperature=0.7`, `max_tokens=800`, and a
`vendor/model`-style identifier — is the operator's first check after configuring a
deployment, and it must be reported separately if it is reported at all.

**Operator-facing migration note required in the Completion Record.** Because an
unset variable stops working, the record must state plainly that the variable has
to be set in an environment before this change reaches it, and give the value a
GitHub Models deployment would need.

## Rollback

1. Revert `backend/app/config.py:29` to the literal.
2. Revert the three tests and the two documentation entries.

No data is written and no stored state depends on the value, so there is no
irreversible effect. No step requires a destructive Git operation.

## Completion Record

| Field | Value |
| --- | --- |
| Specification approval | **Approved 2026-09-11** — `docs/specs/2026-09-11-configurable-model-provider-endpoint-design.md` v0.2, repository owner. |
| Plan approval | **Approved 2026-09-11** — repository owner, with the instruction to implement immediately. |
| Execution | **Complete — Task 1 implemented.** |
| Verification | **Run on the final worktree state.** All nine package checks pass, with one check corrected and disclosed below. |
| Delivery gate | Repository owner only. No Git delivery is authorized by this plan. |

**Checked where evidence exists.** The seven step checkboxes are ticked because the evidence below exists.

### Task 1 — Make the endpoint configurable

| Field | Value |
| --- | --- |
| Setting | `backend/app/config.py:35` — `os.getenv("GITHUB_MODELS_URL", "").strip()` |
| Consumers changed | **None.** `llm.py` and `judge.py` were not edited; both already read `settings.GITHUB_MODELS_URL` |
| Tests | `backend/tests/unit/test_config.py` → **7 passed** (was 3; four added) |
| Documentation | `.env.example` line 17 and `DEVELOPMENT.md` line 35, both stating the setting is required with no default |

### Package verification — actual results

| # | Check | Result |
| --- | --- | --- |
| 1 | `pytest backend/tests/unit` | **798 passed** (was 794; +4) |
| 2 | `pytest backend/tests/boundaries` | **16 passed**, unchanged count |
| 3 | `pytest backend/tests/integration` | **163 passed, 0 failed, 0 skipped** — **run with `GITHUB_MODELS_URL` unset**, which is the check that matters: removing the default broke nothing |
| 4 | `cd frontend && npx vitest run` | **28 passed (3 files)** |
| 5 | Consumers unedited | **The check as written was invalid** — see deviation 1. Verified by modification time instead: `llm.py` last written **5.7 hours** before this change and `judge.py` **8 days** before it; neither was touched. `judge.py` has no diff against `HEAD` at all, and the only `GITHUB_MODELS_URL` lines in `llm.py`'s diff are a re-indentation from an earlier plan |
| 6 | `GITHUB_MODELS_URL` in `config.py` | one line, line 35, reading the environment with no fallback |
| 7 | The value with the variable unset | `''` — no default survives in the source |
| 8 | `.env.example` and `DEVELOPMENT.md` | both name the setting and mark it **required** with no default |
| 9 | `git status --short --untracked-files=all` | nothing staged or committed; `HEAD` still `cec0933` on `feature/agent-memory` |

### Load-bearing proof recorded

Reverting `config.py` to the hardcoded literal makes **three** tests fail —
`test_models_url_reads_the_environment`, `test_models_url_has_no_default` and
`test_models_url_strips_whitespace`. Restored → **7 passed**. The tests are
load-bearing, and the red-green cycle held despite the test mechanism changing
between the RED run and the GREEN run (see deviation 2).

### The fact that had to be established, and how it turned out

`Settings` evaluates `os.getenv` **in its class body**, so the value is captured
**once, when the module is imported** — not per `Settings()` call. Established by
measurement:

- In the same process, setting the variable after import changes nothing: `Settings().GITHUB_MODELS_URL` returns the import-time value.
- In a fresh interpreter with the variable set, the value is read correctly: configured → the configured URL; whitespace, empty, and unset → `''`.

This is correct for the application, which imports once with its environment already
in place. It is fatal for the obvious test, which is why the tests spawn an
interpreter rather than using `monkeypatch`.

### Deviations from the approved plan

1. **Package check 5 was invalid as written, and was replaced.** It read `git diff --stat backend/rag/generation/llm.py backend/rag/evaluation/judge.py` and expected no output. In a working tree carrying several plans' uncommitted work, that command shows the **session's accumulated diff**, not this change's — it reported 30 insertions in `llm.py` that belong to an earlier plan. The consumers were verified by modification time and by inspecting the diff for the setting's name instead. **The check was corrected, not the result explained away.**
2. **The tests use a fresh interpreter, not `monkeypatch`.** The plan specified `monkeypatch.setenv` followed by `Settings()`. That cannot work: the default is baked at import. The first GREEN attempt failed with two tests still red, which is how the mechanism was found. The tests now spawn an interpreter, reproducing the real read. The red-green evidence was re-established by mutation after the change (see above), so the claim does not rest on the abandoned mechanism.
3. **The test module's docstring was widened** from "PostgreSQL DSN resolution" to "DSN resolution and provider configuration", because it now covers both.
4. **A fourth test was added** beyond the plan's three: `test_an_empty_endpoint_still_constructs_a_client`. It is a guard, not a regression test — it pins the measured SDK behaviour so the mistake this plan made is not repeated. The plan anticipated it.

### Operator-facing migration note — required, and not optional

**`GITHUB_MODELS_URL` must be set in an environment before this change reaches it.**
Before this change, an unset variable selected GitHub Models and the chat path
worked. After it, an unset variable produces an empty base URL and the first model
call raises `APIConnectionError: Connection error.`

A deployment that used GitHub Models and never set the variable needs:

```bash
GITHUB_MODELS_URL=https://models.inference.ai.azure.com
```

Set it first, confirm it is present, then deploy the change.

### Limits — disclosed, not claimed as passing

1. **No call was made to any third-party endpoint.** Whether a configured provider accepts this application's request shape — `temperature=0.7`, `max_tokens=800`, and a `vendor/model`-style identifier — is untested and is the operator's first check after configuring a deployment.
2. **The failure message misleads, and this change does not fix it.** An unset endpoint produces `Connection error.`, which names neither the setting nor the configuration, so an operator may investigate the network first. The fail-fast check that would fix it is the specification's non-goal 1 and is **not** implemented; the owner did not authorize it.
3. **The readiness probe will not catch an unset endpoint.** `model_provider` reports ready, because it checks the credential only. Pre-existing, and made reachable by this change.
4. **An operator can now redirect user content to an arbitrary address** with one environment variable and no code review. The https-only guard that would limit this is the specification's non-goal 7 and is not implemented.
5. **`GITHUB_TOKEN` keeps its name** while becoming the credential for whatever endpoint is configured.
6. **`test_models_url_has_no_default` is a behaviour-change test, not a correctness test.** It asserts that the variable is unset in the test environment. If a developer sets `GITHUB_MODELS_URL` in their shell, that test fails for an environmental reason rather than a code reason — which is the intended reading, since the test's subject is exactly "no default exists".
7. **The observation about `LLM_MODEL` stands unchanged.** It does not strip whitespace, so a whitespace-only model name is used verbatim while a whitespace-only endpoint becomes empty. Out of scope, recorded rather than silently corrected.
8. **No Git delivery was performed.** Nothing was staged or committed.
