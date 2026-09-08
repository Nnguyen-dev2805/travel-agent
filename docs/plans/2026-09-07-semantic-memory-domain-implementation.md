# Semantic Memory Domain Implementation Plan

> **For agentic workers:** Execute only after this exact child plan is approved.
> Use RED-GREEN-review cycles and keep the package free of adapters.

**Goal:** Prove one canonical semantic key, immutable write contracts,
deterministic safety policy, and conflict resolution without database, HTTP,
worker, or model-provider dependencies.

**Architecture:** A versioned registry defines one key. Immutable evidence,
candidate, decision, assertion, version, relation, operation, and change-set
types feed a pure resolver. Deterministic eligibility and sensitivity logic own
write permission.

**Tech Stack:** Python standard library, dataclasses, enums, pytest.

**Spec:** Approved focused spec v0.1 as amended by the approved Risk-based
Memory Control Amendment v0.1; ADRs 0013 and 0017 Accepted; ADR 0015
Superseded.

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-07 |
| Approved specification | Basic Semantic Memory Write Pipeline Design v0.1 |
| Scope | Master Tasks 3-5 only |
| Verification | Pure unit tests with no database/network/model provider |

## Approved Amendment Authority

All three tasks are executable under this approved child plan together with the
approved Risk-based Memory Control Amendment Implementation Plan v0.1. Task 3
must implement risk-based policy only; historical confirm-all disposition is
superseded.

## Task Table

| Task | Output | Verification |
| --- | --- | --- |
| 1 | First versioned registry and immutable domain contracts | Registry/model tests |
| 2 | Exact deterministic conflict truth table | Resolver tests |
| 3 | Eligibility, prohibited-secret, sensitivity, and write policy | Policy/safety tests |

## Task 1: Registry and Domain Contracts

**Files:** Create `backend/memory/write_pipeline/__init__.py`, `registry.py`,
`models.py`, and unit tests under `backend/tests/unit/memory_write_pipeline/`.

**Interfaces:** Define `HotelAtmosphere`, `SemanticKeyDefinition`,
`MemoryEvidence`, `MemoryCandidate`, `MemoryDecision`, `AssertionIdentity`,
`MemoryVersion`, `MemoryRelation`, `MemoryOperation`, and `MemoryChangeSet`.

- [ ] Write failing tests for the exact key, four values, single cardinality,
  user/conversation scopes, ordinary sensitivity, authority, fingerprint,
  prefixed IDs, UTC time, immutability, and unknown input rejection.
- [ ] Run registry/model tests and observe RED.
- [ ] Implement the minimal standard-library-only contracts and normalizers.
- [ ] Rerun tests and require GREEN.
- [ ] Review that display text never defines identity.

## Task 2: Pure Conflict Resolver

**Files:** Create `backend/memory/write_pipeline/resolver.py` and
`backend/tests/unit/memory_write_pipeline/test_resolver.py`.

**Interface:**

```python
resolve_change(candidate: MemoryCandidate,
               current: tuple[MemoryVersion, ...],
               relation: MemoryRelation) -> MemoryChangeSet
```

- [ ] Write parameterized RED tests for `ADD`, `REINFORCE`, explicit
  `SUPERSEDE`, weaker opposition, `ADD_EXCEPTION`, `PENDING_CONFLICT`, `REJECT`,
  and `NOOP`.
- [ ] Implement deterministic cardinality, authority, scope, time, and
  uncertainty rules without side effects.
- [ ] Require GREEN and inspect every expected transition exactly.
- [ ] Review that no repository/model/FastAPI import enters the resolver.

## Task 3: Eligibility and Safety Policy

**Files:** Create `backend/memory/write_pipeline/secrets.py`, `policy.py`,
`test_secrets.py`, and `test_policy.py`.

**Interfaces:** `detect_prohibited_content`, `evaluate_eligibility`,
`classify_sensitivity`, and `decide_candidate`.

- [ ] Write RED tests for authenticated user evidence, invalid actor/source,
  deleted source, ordinary preference, restricted hold, prohibited secret,
  unknown key, explicit low-risk direct-write eligibility without a second
  confirmation, sensitive no-store/no-prompt disposition, and background
  shadow disposition.
- [ ] Implement deterministic secret detection and registry-floor escalation;
  contextual model output may only raise sensitivity. `decide_candidate`
  returns policy data only: it never mutates storage, issues UI save state, or
  creates confirmation tokens. Valid low-risk explicit candidates are eligible
  for the later direct-commit path; valid background candidates are `SHADOW`;
  hard-policy failures are never `SHADOW`.
- [ ] Require GREEN with no raw prohibited value in logs or assertion text.
- [ ] Review the separation between extraction meaning and policy permission.

## Child Verification

Run `pytest -q backend/tests/unit/memory_write_pipeline`. Run import checks that
the package has no FastAPI, SQLAlchemy, repository, RAG, or provider dependency.

## Rollback

Remove the isolated V2 domain package and tests; no persistent state or public
contract exists in this child.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-09-07 for sequential
implementation by a different implementation agent. The current planning agent
is review-only and is not authorized to implement runtime changes or perform
Git delivery.
