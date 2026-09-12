# Configurable Model Provider Endpoint

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.2 |
| Date | 2026-09-11 |
| Change class | Level 2 - Bounded Change |
| Decision owner | Repository owner |
| Scope | How the model provider endpoint is supplied to the application. Bounded to one setting in `backend/app/config.py` and its documentation. |
| Related issue | None filed. Authorization basis is the repository owner's selection of the minimal approach from the provider-configuration proposal of 2026-09-11, and the owner's instruction that the setting be read from the environment with no code default. |
| Superseded document | Not applicable |

## Summary

`backend/app/config.py:29` declares the model provider endpoint as a **literal**:

```python
GITHUB_MODELS_URL: str = "https://models.inference.ai.azure.com"
```

The two places that build a model client read it through `settings` —
`backend/rag/generation/llm.py:60` and `backend/rag/evaluation/judge.py:108` — so
changing the endpoint today requires editing source.

This specification makes the setting read from the environment **with no code
default**, per the repository owner's instruction. The endpoint becomes required
deployment configuration: an unconfigured deployment fails loudly rather than
falling back to a vendor address baked into the source.

That is a deliberate behaviour change, and this document states its consequence
plainly rather than presenting it as a pure refactor. **An unset variable no
longer works.** Today it selects GitHub Models; after this change it produces an
empty base URL and the model call fails.

## Context

`Settings` is a pydantic `BaseModel` constructed once at import
(`settings = Settings()`, `config.py:123`), and each field reads its environment
variable at construction time. Three settings govern the model provider:

| Setting | Line | Source |
| --- | --- | --- |
| `GITHUB_TOKEN` | 27 | `os.getenv("GITHUB_TOKEN", "")` |
| `LLM_MODEL` | 28 | `os.getenv("LLM_MODEL", "gpt-4o-mini")` |
| `GITHUB_MODELS_URL` | 29 | **a literal — no environment read** |

The asymmetry is the defect. A deployment can already choose its model name and
its credential without a code change, but not its endpoint, which is the one
thing a non-GitHub provider must change.

Consumers, all through `settings`, so none needs editing:

- `backend/rag/generation/llm.py:59-62` — the online chat path.
- `backend/rag/evaluation/judge.py:107-110` — the offline LLM judge.

## Users

1. **Repository owner** — wants to point the application at a chosen provider without editing source, and does not want a vendor address shipped as a code default.
2. **Operator** — supplies the endpoint as deployment configuration and needs it documented.
3. **Engineer running the evaluation harness** — the judge uses the same endpoint, so a configured deployment evaluates against the provider it actually serves with.
4. **Future contributor** — needs the provider configuration to be findable. Today `.env.example` lists `GITHUB_TOKEN` and `LLM_MODEL` but not the endpoint.

## Problem Statement

**The endpoint is not configurable.** A literal in `config.py` is the only
source. Switching provider therefore requires a source edit, a review, and a
redeploy — for a value that is deployment configuration by nature.

**An empty base URL fails loudly, and the message misleads.** Measured on
2026-09-11 against `openai` 3.3.1: `OpenAI(base_url="", api_key=...)` keeps the
empty string (`client.base_url == ''`), and a chat-completions call raises
`openai.APIConnectionError: Connection error.`

Two things follow, and both matter:

- **It does not silently redirect.** An earlier draft of this specification
  claimed the SDK substitutes its own public endpoint for an empty one. That is
  **false**, and the measurement above is the correction. The SDK uses its own
  default only when `base_url` is *omitted*, not when it is empty.
- **The error is unhelpful.** `Connection error.` reads as a network fault. An
  operator who forgot to configure the endpoint would debug their network rather
  than their configuration.

**Why now.** The owner has chosen to point the application at a specific
OpenAI-compatible provider and has asked that the endpoint come only from the
environment, with no fallback compiled into the source.

## Goals

1. `GITHUB_MODELS_URL` is read from the environment.
2. **No code default.** The setting's default is the empty string, so the source ships no vendor address.
3. A blank or whitespace-only value yields the empty string rather than a malformed one. Whitespace must not survive into the base URL, because the SDK percent-encodes it into a garbage path (`"   "` becomes `%20%20%20/`).
4. Both existing consumers follow without being edited, because both read `settings`.
5. The setting is documented in `.env.example` and in `DEVELOPMENT.md`'s environment table, including that it is **required** and must speak the OpenAI chat-completions protocol.
6. Tests prove the environment variable is honoured, that unset yields the empty string, and that whitespace is stripped.

## Non-goals

1. **A fail-fast check for a missing endpoint.** Today `llm.py:56-58` already raises a named `ValueError` when `GITHUB_TOKEN` is absent. A parallel check for the endpoint would convert the measured `APIConnectionError: Connection error.` into a named configuration error, and would be roughly four lines in each of the two consumers. **Recommended, and deliberately not bundled** — see Failure and Recovery. It is the one follow-up that addresses a failure mode this change creates.
2. **Renaming the credential.** `GITHUB_TOKEN` keeps its name. It becomes the credential for whatever endpoint is configured, which is misleading; renaming it is a separate change touching five call sites and the artifact redaction list.
3. **Wrapping `GITHUB_TOKEN` in `SecretStr`.** It is currently a plain `str`, unlike `PG_PASSWORD` and `LOCAL_AUTH_TOKENS_JSON`. A real hygiene gap, and a separate change, because five readers would need `get_secret_value()`.
4. **A single `build_llm_client()` factory.** `llm.py` and `judge.py` still construct the client separately with identical arguments.
5. **Decoupling the evaluation preflight** from `settings.LLM_MODEL`.
6. **The memory pipeline's model default.** `MemoryExtractionModel` still defaults to `gemini-2.5-flash` and still has no real provider implementation.
7. **An https-only guard on the endpoint.** See Security and Privacy.

## Assumptions

1. The configured endpoint speaks the OpenAI chat-completions protocol, because both consumers construct `OpenAI(...)` from the `openai` SDK.
2. Reading the variable at `Settings()` construction is correct, because that is how every other setting in the file behaves and `Settings` is constructed once at import.
3. Constructing a client with an empty base URL does not raise. Verified: construction succeeds; only a request fails. So an unconfigured deployment still starts, and the failure appears on the first chat turn.
4. No test pins the literal. Verified: the only occurrence of the literal in the repository is its own definition.
5. The two consumers need no edit. Verified: both read `settings.GITHUB_MODELS_URL`.
6. Removing the default does not break the test suite. Expected because tests inject fake clients or monkeypatch `GITHUB_TOKEN`; the plan requires the full suite to be run to confirm rather than assume it.

## User and System Flows

**Flow 1 — Configured deployment.** The operator sets `GITHUB_MODELS_URL`, `GITHUB_TOKEN` and `LLM_MODEL`. The chat path and the judge both use the configured endpoint, because both read the same setting.

**Flow 2 — Unconfigured deployment.** The variable is unset. The application starts. The first chat turn raises `APIConnectionError: Connection error.` The readiness probe still reports the `model_provider` component as ready, because it checks only that the credential is present — so readiness does **not** catch this. That gap is recorded below.

**Flow 3 — Blank value.** `GITHUB_MODELS_URL=` is present but empty, or contains only whitespace. The setting is the empty string, which is the same outcome as unset.

## Behavioral and Data Contracts

### Setting (`backend/app/config.py`)

- **Produces:** `GITHUB_MODELS_URL: str`, read from the environment.
- **Contract:** the name is unchanged. **The default is the empty string** — no vendor address is compiled in.
- **Contract:** the value is stripped, so whitespace cannot become `%20%20%20/` in a base URL.
- **Contract:** it remains a plain `str`, consistent with `LLM_MODEL`. It is not a secret.
- **Contract:** an empty value is not rejected at construction. The application still imports and starts.

### Consumers

- **Contract:** unchanged. `llm.py` and `judge.py` continue to pass `settings.GITHUB_MODELS_URL` to `OpenAI(base_url=...)`.

### Documentation

- **Produces:** an entry in `.env.example` and a row in `DEVELOPMENT.md`'s environment table.
- **Contract:** both state that the setting is **required**, that it must speak the OpenAI chat-completions protocol, and that there is no default.

## Errors and Edge Cases

1. **Unset.** Expected: the empty string. The application starts; the first model call raises `APIConnectionError`.
2. **Blank.** Expected: the empty string, identical to unset.
3. **Whitespace only.** Expected: the empty string after stripping. A bare `os.getenv` without stripping would produce `%20%20%20/` as the base URL.
4. **A non-https value.** Expected: accepted, with the risk recorded. See Security and Privacy.
5. **An unreachable or non-conforming endpoint.** Expected: the model call fails and the existing error paths report it; this change adds no endpoint validation.
6. **A test that sets the variable after import.** Expected: no effect, because `Settings` is constructed once. Tests must construct a fresh `Settings()` to observe the variable.
7. **Readiness with an unset endpoint.** Expected: `model_provider` reports ready, because the probe checks the credential only. This is a pre-existing gap that this change makes reachable, and it is recorded rather than fixed.

## Security and Privacy

**Trust boundaries.** One boundary moves from a code constant to deployment configuration: the external model endpoint that receives user message content and retrieved travel context. `SECURITY.md`'s External Providers section already governs this flow and is not changed by making the address configurable.

**Authorization.** Unchanged. The endpoint is not an authorization input.

**Data classification.** Unchanged. No new data is read or stored.

**A claim corrected.** An earlier draft stated that an empty base URL would silently redirect user content to the SDK's own public endpoint. Measurement shows the opposite: the SDK keeps the empty string and the request fails. The security consequence is therefore a **loud outage**, not a silent misroute. The correction is recorded here because the original claim would have justified a fallback default that the owner has since ruled out.

**Residual risk, recorded rather than bundled.** An operator can point user content at an arbitrary address by setting one variable, without a code review. Two mitigations exist and neither is part of this change:

1. **An https-only guard.** Rejecting a non-https value prevents plaintext transmission of user content from a misconfiguration.
2. **Naming.** `GITHUB_TOKEN` remains the credential's name, so a deployment reads as if it talks to GitHub when it may not.

**Secret handling.** Unchanged. The endpoint is not a secret, and the credential's handling is out of scope. `backend/rag/evaluation/artifacts.py:502` scrubs `GITHUB_TOKEN` from evaluation artifacts; that list is unaffected because the credential's name does not change.

## Observability and Operations

- `backend/observability/readiness.py:86,92` reports `settings.LLM_MODEL` and checks `settings.GITHUB_TOKEN`. It does **not** report the endpoint and does **not** catch an unset endpoint. Extending it is out of scope and recorded as a follow-up.
- No new log line, event, or metric.
- The change is visible in `.env.example`, which is the discoverable place an operator looks.

## Capacity, Latency, and Cost

- **Latency.** No change. One extra `os.getenv` at import.
- **Capacity.** No change.
- **Cost.** No change. The cost of model calls is a property of the configured provider.
- **Measurement.** Not applicable; there is nothing to measure for a value read once at import.

## Compatibility and Staged Migration

**This change is not behaviour-preserving, and the sequencing below is the mitigation.**

**Coexistence.** Today, an unset variable selects GitHub Models. After this change, an unset variable produces an empty base URL and the chat path fails. A deployment that never set the variable will break on the first chat turn after this change is deployed.

**Sequencing.** The variable must be set **before** the code change reaches an environment. Concretely:

1. Add `GITHUB_MODELS_URL` to the target environment's configuration, pointing at the provider in use (for a GitHub Models deployment, `https://models.inference.ai.azure.com`).
2. Confirm the value is present in the running configuration.
3. Deploy the code change.

**Rollout gate.** The full test suite passes with the variable unset, and a configured environment resolves the configured endpoint through both consumers without either being edited.

**Rollback boundary.** Reverting the commit restores the literal, and an unset variable works again. No data is written and no stored state depends on the value, so there is no irreversible effect.

## Failure and Recovery

| Failure | Behaviour | Recovery |
| --- | --- | --- |
| Variable unset or blank | `APIConnectionError: Connection error.` on the first model call; the application starts normally | Set `GITHUB_MODELS_URL` and restart. **The message names neither the setting nor the configuration**, so an operator may investigate the network first |
| Readiness with an unset endpoint | `model_provider` reports ready — the probe checks the credential only | Pre-existing gap, recorded; not fixed here |
| Endpoint unreachable | `APIConnectionError` | Correct the configuration or the network |
| Endpoint rejects the model name | The provider's error surfaces through the existing paths | Choose a model the endpoint serves |
| Endpoint rejects `temperature` or `max_tokens` | The provider's error surfaces; `llm.py` sends both | A separate change would make those configurable |

**The first row is the reason a fail-fast check is recommended.** `llm.py` already fails fast with a named `ValueError` when the credential is missing; the same treatment for the endpoint would turn a misleading connection error into a configuration error. It is listed as non-goal 1 so the owner can add it deliberately rather than find it bundled.

## Required ADRs

**None.** This change makes one existing constant read from the environment, with no fallback, using the same mechanism the two settings above it already use. It introduces no new component, changes no interface another module depends on, and alters no schema. Recording an ADR would promote a configuration default into an architecture decision.

## Alternatives Considered

### Read from the environment with no default — the selected approach

**Approach.** `GITHUB_MODELS_URL: str = os.getenv("GITHUB_MODELS_URL", "").strip()`, plus `.env.example`, `DEVELOPMENT.md`, three tests, and one client-construction guard.

**Benefits.** Achieves the owner's goal with one behavioural line. The source ships no vendor address. Both consumers follow with no edit. The blast radius is measured: one definition and two readers, and no test pins the literal.

**Costs.** An unset variable stops working, so every deployment must set it before the change lands. The failure it produces is a misleading `Connection error.` rather than a named configuration error. The readiness probe does not catch it.

**Selected because** the owner directed that the endpoint come only from the environment, and because a deployment that must be configured explicitly is a defensible design for a value that is deployment configuration by nature.

### Read from the environment, keeping the current address as the default

**Approach.** `os.getenv("GITHUB_MODELS_URL", "").strip() or "https://models.inference.ai.azure.com"`.

**Benefits.** Behaviour-preserving: an unset variable keeps working exactly as today. No migration sequencing is required.

**Costs.** The source keeps shipping a vendor address as a default, which is what the owner asked to remove.

**Rejected** by owner instruction. Recorded because it is the only alternative that requires no migration step, so the cost of the selected approach is visible rather than implicit.

### Add a fail-fast check alongside the setting

**Approach.** The selected change, plus in `llm.py` and `judge.py`:

```python
if not settings.GITHUB_MODELS_URL:
    raise ValueError("GITHUB_MODELS_URL is missing in server environment.")
```

**Benefits.** Converts the measured `APIConnectionError: Connection error.` into a named configuration error, mirroring the check that already exists for the credential two lines above. Roughly four lines per consumer.

**Costs.** Two consumer files change, so the change is no longer one line, and the consumers' error paths gain a branch that needs its own test.

**Not selected, and recommended.** It is the one option that addresses a failure mode this change creates. It is left out so the owner can approve it deliberately.

## Current-state Evidence

| Claim | Evidence path | Verified how |
| --- | --- | --- |
| The endpoint is a literal with no environment read | `backend/app/config.py:29` | Direct read |
| The two settings above it read the environment | `backend/app/config.py:27-28` | Direct read |
| Exactly two consumers, both via `settings` | `backend/rag/generation/llm.py:60`, `backend/rag/evaluation/judge.py:108` | Repository-wide search for `GITHUB_MODELS_URL` |
| No test pins the literal | Repository-wide search for `models.inference.ai.azure.com` returned only its own definition | Executed |
| `.env.example` omits the setting | `.env.example` lists `GITHUB_TOKEN` (line 8) and `LLM_MODEL` (line 11), not the endpoint | Direct read |
| `DEVELOPMENT.md` documents the credential but not the endpoint | `DEVELOPMENT.md:33` | Direct read |
| `Settings` is constructed once at import | `backend/app/config.py:123` | Direct read |
| The OpenAI SDK requires a credential even with a `base_url` | Probe, `openai` 3.3.1: `OpenAI(base_url=...)` raised `OpenAIError: Missing credentials`; with `OPENAI_API_KEY` set it constructed | Executed |
| **An empty base URL is kept as an empty string, not replaced by the SDK's own** | Probe: `OpenAI(api_key=…, base_url="").base_url` is `''`; the SDK default `https://api.openai.com/v1/` appears only when `base_url` is omitted | Executed. **Corrects the earlier draft** |
| **A request with an empty base URL raises a connection error** | Probe: `chat.completions.create(...)` with `base_url=""` raised `openai.APIConnectionError: Connection error.` | Executed |
| Whitespace is percent-encoded into the base URL | Probe: `base_url="   "` yields `client.base_url == '%20%20%20/'` | Executed |
| The readiness probe reports the model but not the endpoint, and checks the credential only | `backend/observability/readiness.py:80,86,92` | Direct read |
| The artifact redaction list names only `GITHUB_TOKEN` | `backend/rag/evaluation/artifacts.py:502` | Direct read |

**Not verified.** No call was made to any third-party endpoint, so whether a given provider accepts this application's request shape — `temperature=0.7`, `max_tokens=800`, and a `vendor/model`-style identifier — is untested. That is the operator's first check after configuring a deployment. Whether removing the default breaks any test was not established by reading; the plan requires the full suite to be run.

## Components and Dependency Direction

```
backend/app/config.py  (GITHUB_MODELS_URL: literal -> os.getenv, no default)
   │
   ├─► backend/rag/generation/llm.py:60    OpenAI(base_url=settings.GITHUB_MODELS_URL, ...)
   └─► backend/rag/evaluation/judge.py:108 OpenAI(base_url=settings.GITHUB_MODELS_URL, ...)
```

**Allowed dependency direction.** Unchanged. No module gains a dependency; one setting gains an environment read and loses a default.

**Ownership.** `config.py` owns deployment configuration. The consumers own client construction and are unchanged.

## Data Flow and Lifecycle

**Configuration lifecycle.** Read once at import. Changing it requires a process restart, which is how every other setting behaves.

**Request lifecycle.** Unchanged, except that an unconfigured endpoint now fails on the first model call instead of resolving to a working default.

## Approval Record

| Field | Value |
| --- | --- |
| Version | 0.2 |
| Status | Approved — 2026-09-11, repository owner |
| Approver role | Repository owner |
| Date | 2026-09-11 |
| Authorization boundary | Authorizes preparation and approval of the implementation plan at `docs/plans/2026-09-11-configurable-model-provider-endpoint-implementation.md`. Implementation is authorized only by the separate plan approval recorded below. |

**Approved 2026-09-11 by the repository owner, together with Plan F.** The approval authorizes execution of the single task of that plan.

**What this approval does NOT authorize.** A fail-fast check for a missing endpoint; renaming or wrapping the credential; an https-only guard; merging the two client constructions; decoupling the evaluation preflight; and any Git delivery.

**Three consequences of this approval must be understood as part of it.**

1. **An unset variable stops working.** Today it selects GitHub Models. After this change it produces an empty base URL and the first chat turn raises `APIConnectionError`. Every deployment must set `GITHUB_MODELS_URL` **before** this change reaches it; the migration sequence is in Compatibility and Staged Migration.
2. **The failure is misleading.** The error names neither the setting nor the configuration. A fail-fast check would fix that and is recommended as non-goal 1; it is not bundled.
3. **The readiness probe will not catch it.** `model_provider` reports ready on an unset endpoint, because it checks the credential only.

**One claim from version 0.1 is withdrawn.** That draft stated that an empty base URL would silently redirect user content to the SDK's own public endpoint. Measurement contradicts it: the SDK keeps the empty string and the request fails. The security consequence is an outage, not a silent misroute.
