# Basic Memory Write Pipeline Evaluation Protocol

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-07 |
| Decision owner | Repository owner |
| Governing spec | [Basic Semantic Memory Write Pipeline Design](../specs/2026-09-07-basic-semantic-memory-write-pipeline-design.md), Approved v0.1 |
| Scope | Candidate, policy, conflict, persistence, trigger, confirmation, isolation, deletion-safety, and operational evidence for the first semantic key |

## Approved Design Amendment and Evaluation Hold

The [Risk-based Memory Control Amendment](../specs/2026-09-07-risk-based-memory-control-amendment.md)
v0.1 is Approved and supersedes this protocol's confirm-all expectations.
Affected scenarios and metrics remain non-executable until the separate
[Risk-based Memory Control Evaluation Amendment](./memory-control-amendment-evaluation.md)
is approved. Do not freeze or implement the historical S01, S09, S16-S17 or
unconfirmed-mutation expectations as current product behavior.

## Purpose

This protocol defines how the first deployable semantic Write Pipeline is
judged. It separates component correctness from runtime integration and prevents
an average score from compensating for a scope, secret, deletion, confirmation,
or atomicity failure.

The protocol does not evaluate Conversation Summary, Episodic Memory, inferred
auto-promotion, memory-aware answer quality, pgvector retrieval, or the final
1,000-user production target.

## Result States

| State | Meaning |
| --- | --- |
| `PASS` | All required evidence is valid, every hard gate passes, and every required quality threshold passes |
| `FAIL` | Evidence is valid but at least one hard gate or required threshold fails |
| `INCONCLUSIVE` | Evidence is valid but required sample size, model comparison, or statistical evidence is insufficient |
| `INVALID` | Dataset, schema, configuration, accounting, infrastructure, or report evidence is missing or malformed |

Infrastructure failure and model parse failure never become favorable scores.

## Evaluation Layers

| Layer | Question | Primary evidence |
| --- | --- | --- |
| Domain | Does registry, normalization, authority, scope, sensitivity, and resolver logic produce the correct typed change set? | Pure unit tests and per-example records |
| Model extraction | Does bilingual text produce the expected candidate without persistence authority? | Frozen fixtures, strict-schema output, candidate labels |
| Policy | Does the candidate become invalid, rejected, shadow, held, pending, routed, or promotable correctly? | Decision records and reason codes |
| Persistence | Is one change applied atomically and idempotently under failure and concurrency? | PostgreSQL integration state and transaction injection |
| Trigger/runtime | Do explicit and normal-chat paths invoke the right write behavior without adding background latency to chat? | Integration timing and stored outbox/result evidence |
| Security/privacy | Can owner, secret, deleted source, stale worker, or missing confirmation bypass policy? | Zero-tolerance safety fixtures |
| Operations | Can failed and delayed work be diagnosed and recovered without content leakage? | Queue, retry, dead-letter, trace, and redaction evidence |

## Dataset Contract

The first dataset is proposed as:

```text
dataset_id: write-pipeline-hotel-atmosphere-v0.1
role: development
languages: vi, en
canonical_key: travel.preference.hotel_atmosphere
values: quiet, lively, central, secluded
```

Each JSONL example must contain:

```text
example_id
slice
language
source_events
existing_assertions_and_versions
expected_candidates
expected_decisions
expected_change_set
expected_persisted_state
expected_outbox_state
expected_trace_fields
expected_user_response_contract
```

Content uses synthetic identities and synthetic or redacted text. Examples must
not contain real credentials, payment data, passport data, or personal user
content.

## Required Scenario Matrix

| ID | Scenario | Expected pipeline result | Verification | Gate |
| --- | --- | --- | --- | --- |
| S01 | New explicit Vietnamese preference | Candidate `quiet`; confirmed command produces `ADD` | One assertion, one active version, evidence and decision aligned | Required quality |
| S02 | New explicit English preference | Candidate `quiet`; same canonical identity as S01 | Language-invariant normalized value | Required quality |
| S03 | Greeting or travel question without preference | No semantic candidate and `NOOP`/rejected no-signal evidence | Zero assertion/version writes | Required quality |
| S04 | Paraphrase of active value | `REINFORCE` existing assertion | New evidence; no duplicate assertion or value version | Required quality |
| S05 | Explicit confirmed correction | `SUPERSEDE` old active version with new value | Exactly one active current version; history preserved | Hard correctness |
| S06 | Weak inferred contradiction against explicit version | Shadow/opposing evidence or `PENDING_CONFLICT`; no supersession | Explicit version remains active | Hard correctness |
| S07 | Conversation-specific exception | `ADD_EXCEPTION` under conversation scope | User default remains active and unchanged | Hard correctness |
| S08 | Equal-authority ambiguous contradiction | `PENDING_CONFLICT` | No destructive mutation and no conflicting values injected as current truth | Hard correctness |
| S09 | Contextually sensitive or restricted statement | `HELD_SENSITIVE` or excluded under focused scope | No active durable version or embedding | Hard safety |
| S10 | Secret/payment/authentication pattern | Reject before model/candidate persistence where detectable | Zero raw value in DB, logs, reports, prompts, indexes | Hard safety |
| S11 | Duplicate event delivery | Same idempotent result | One candidate/evidence semantic outcome, no duplicate version | Hard correctness |
| S12 | Failure after evidence but before version/outbox commit | Whole transaction rolls back | No partial rows in any canonical table | Hard correctness |
| S13 | Cross-owner source/assertion mismatch | Fail closed | Zero foreign-owner reads or writes | Hard safety |
| S14 | Source conversation deleted while worker is leased | Job `CANCELLED`; no candidate/version commit | Deletion epoch mismatch recorded without content | Hard safety |
| S15 | Normal chat background extraction | `SHADOW` decision only | Zero active versions; chat response does not wait for extractor | Hard rollout |
| S16 | Explicit operation without confirmation | Controlled pending/cancelled result | Zero durable mutation | Hard safety |
| S17 | Confirmation references stale preview/version | Re-resolve and request a new confirmation or fail controlled | No mutation against stale expected version | Hard correctness |
| S18 | Invalid model output, then valid bounded repair | One candidate from repaired strict output | Repair count and versions recorded | Required quality |
| S19 | Invalid model output twice | `INVALID`, no mutation | Parse/schema failure remains visible | Hard correctness |
| S20 | Model provider unavailable | Background retry; chat succeeds | No fallback auto-promotion and no false success | Hard rollout |
| S21 | Canonical trace persistence fails | Mutation rolls back | No active version without durable decision evidence | Hard correctness |
| S22 | External telemetry export fails | Canonical mutation may commit | Local operational failure visible; no data corruption | Required operations |

## Metric Table

| Metric | Definition | Initial threshold | Interpretation |
| --- | --- | --- | --- |
| Candidate precision | Correct expected candidates / all produced candidates | `>= 0.95` overall | Primary write-quality measure; false durable inputs are costly |
| Candidate recall | Correct expected candidates / all expected candidates | `>= 0.90` for explicit supported preference | Measures missed useful facts; does not compensate for hard failures |
| Key accuracy | Candidates with correct canonical key / eligible candidates | `1.00` for the single supported key | A wrong key breaks conflict and retrieval identity |
| Value normalization accuracy | Correct normalized value / eligible candidates | `>= 0.98` overall and `>= 0.95` per language | Measures bilingual semantic normalization |
| Scope accuracy | Correct user/conversation scope / eligible candidates | `1.00` in hard scope fixtures; `>= 0.98` overall | Scope errors may become privacy errors |
| Sensitivity accuracy | Correct sensitivity band / eligible candidates | `1.00` for prohibited/restricted fixtures | Under-classification is a hard failure |
| Relationship accuracy | Correct same/contradiction/update/exception/unrelated/uncertain label | `>= 0.95` overall; `1.00` for explicit correction and exception hard cases | Diagnoses model semantic comparison separately from resolver behavior |
| Resolver accuracy | Exact expected typed change set / valid resolver examples | `1.00` on required truth table | Resolver is deterministic and must not average away errors |
| Background promotion count | Active versions produced by normal-chat shadow flow | `0` | Auto-promotion is outside this spec |
| Duplicate semantic-write count | Additional assertions/versions after event redelivery | `0` | Idempotency hard gate |
| Partial transaction count | Canonical tables left inconsistent after injected failure | `0` | Atomicity hard gate |
| Cross-owner access/write count | Foreign-owner row observed or mutated | `0` | Isolation hard gate |
| Deleted-source write count | Derived write committed after source deletion epoch | `0` | Deletion-resurrection hard gate |
| Unconfirmed mutation count | Mutation committed without valid confirmation | `0` | User-control hard gate |
| Raw secret leakage count | Secret token present in DB, log, report, model request, or index evidence | `0` | Non-compensating safety gate |
| Chat extraction wait | Normal chat response waits for background model extraction | `false` | Hot-path isolation gate |
| Message/outbox p95 | Application/database time for persisted message plus outbox under load | `<= 100 ms` starting budget | Provisional engineering objective, not current claim |
| Background availability p95 | Eligible shadow candidate available after idle trigger | `<= 60 seconds` starting budget | Freshness objective |

## Hard Gates

One event fails the evaluation candidate:

1. cross-owner read or write;
2. prohibited secret reaches durable candidate, memory, model request, index,
   log, or report outside the approved redacted representation;
3. background normal-chat processing creates an active semantic version;
4. explicit correction fails to supersede the expected version;
5. weaker inference supersedes an explicit version;
6. conversation exception destroys or supersedes the user default;
7. ambiguous conflict causes destructive mutation;
8. duplicate delivery creates duplicate semantic state;
9. injected failure leaves partial canonical state;
10. unconfirmed user action mutates durable state;
11. deleted source or stale worker creates derived state;
12. active memory exists without durable decision and provenance evidence.

## Execution Procedure

| Step | Command or action | Required evidence | Failure state |
| --- | --- | --- | --- |
| 1. Validate fixtures | `python -m backend.memory.write_pipeline.evaluation.cli validate-dataset --dataset docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1` | Dataset ID/version, unique examples, valid labels, mandatory slices | `INVALID` |
| 2. Run deterministic domain tests | `pytest -q backend/tests/unit/memory_write_pipeline` | Registry, normalization, policy, resolver, lifecycle results | `FAIL` on test failure |
| 3. Run PostgreSQL integration tests | `pytest -q backend/tests/integration/test_memory_write_postgres.py` | Constraints, RLS, UoW rollback, idempotency, concurrent writes | `FAIL` or `INVALID` when DB unavailable, reported distinctly |
| 4. Run trigger/worker tests | `pytest -q backend/tests/integration/test_memory_write_runtime.py` | Message/outbox atomicity, chat non-blocking, lease/retry/cancel behavior | `FAIL` |
| 5. Run safety suite | `python -m backend.memory.write_pipeline.evaluation.cli run --dataset docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1 --suite safety --output-dir docs/reports/memory-write-pipeline/candidate` | Per-example hard gates and content-leak scan | `FAIL` for gate event; `INVALID` for incomplete evidence |
| 6. Run bilingual quality suite | Same CLI with `--suite quality` | Precision, recall, key/value/scope/sensitivity/relationship metrics and slices | `FAIL` below threshold |
| 7. Run load/failure profile | Same CLI with `--suite operational` | p50/p95/p99, queue age, retries, dead letters, rollback and recovery | `FAIL` for hard correctness; quality result may be `INCONCLUSIVE` until sample target is met |
| 8. Compare exact change set | `git status --short --untracked-files=all` plus reviewed diff and direct reads | No unplanned source, dependency, migration, generated, or fixture changes | `INVALID` for scope mismatch |
| 9. Produce report | Candidate CLI writes JSON and Markdown with environment and code identity | Complete run metadata, counts, gates, metrics, failures, limitations | `INVALID` when report is partial |
| 10. Repository-owner review | Review spec mapping, reports, remaining limitations, and rollback | Explicit approval or requested changes | No promotion without approval |

Commands name the intended interfaces and paths. They cannot be claimed as
passing until the implementation plan creates them and fresh execution exits
successfully.

## Mandatory Slices

1. Vietnamese explicit preference.
2. English explicit preference.
3. Paraphrase/duplicate.
4. Explicit correction.
5. Weak inference opposition.
6. Conversation exception.
7. Ambiguous conflict.
8. Restricted/contextually sensitive.
9. Prohibited secret/payment/authentication.
10. Cross-owner.
11. Redelivery/idempotency.
12. Transaction failure.
13. Deleted source/stale worker.
14. Confirmation absent/stale.
15. Provider and structured-output failure.
16. Background shadow-only rollout.

Every required slice must contain eligible evidence. An empty mandatory slice
makes the run `INVALID`, not passed.

## Run Metadata

Every report records:

```text
run_id and timestamp
dataset ID, version, role, and example counts
code revision and dirty-state evidence
registry and normalizer versions
model provider, model ID/revision, prompt and output-schema versions
extractor, sensitivity, relationship-classifier, policy, and resolver versions
PostgreSQL and migration revision
worker configuration and retry policy version
feature-gate state
completed, failed, skipped, cancelled, dead-letter, and invalid counts
metric numerators, denominators, thresholds, and mandatory slices
hard-gate events
latency, token, provider-cost, retry, and queue-age summaries
known limitations and checks that did not run
```

## Baseline and Promotion Rules

1. The deterministic rule-based current implementation is a compatibility
   reference, not an automatic quality baseline for the new semantic contract.
2. The first valid development run establishes measurement behavior but cannot
   authorize background auto-promotion.
3. A frozen benchmark and safety dataset version is required before enabling
   explicit production traffic for the new path.
4. Background inferred auto-promotion requires a later specification and a
   new comparison against shadow behavior.
5. Thresholds may be tightened through a reviewed protocol revision. They may
   not be relaxed inside a candidate run.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-09-07. It is the
evaluation authority for child implementation plans derived from the approved
focused specification. Approval does not claim that commands, fixtures,
metrics, reports, or runtime behavior already exist or pass.
