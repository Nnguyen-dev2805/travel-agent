# Memory Read Pipeline V1.5 Design

> **Scope reset on 2026-09-09:** this file is retained as architecture
> exploration history. It is not the active implementation scope. The active
> Draft is [AI Memory Core Engineering Design](./2026-09-09-ai-memory-core-engineering-design.md).
> Foreground turn queues, SSE, leases, quarantine operations, rollout cohorts,
> and other platform/product decisions explored here are deferred unless a
> later approved spec explicitly promotes them.

| Field | Value |
| --- | --- |
| Status | Draft |
| Version | 0.1 |
| Date | 2026-09-08 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Query-conditioned read, effective-state resolution, safe generation context, and evaluation for semantic memory |
| Related issue | Repository-owner approved exception: interactive Read Pipeline design session on 2026-09-08 |
| Superseded document | Extends, but does not yet supersede, the approved Memory Retrieval Design v0.3 |

## Document Operating Rule

This is the living specification for the Read Pipeline design interview. Every
settled decision is recorded with purpose, selected approach, rationale,
trade-offs, invariants, failure behavior, and verification intent. Open
decisions remain explicitly listed. No implementation plan or runtime code is
authorized while this document is Draft or In Review.

## Summary

Read Pipeline V1.5 will turn canonical semantic memory into relevant, safe, and
measurably useful generation context. It is more than record retrieval: it
decides whether memory is needed, enforces owner and lifecycle eligibility,
resolves the effective value across scopes and time, abstains when relevance or
state is uncertain, packs a bounded structured context, and records why memory
was or was not used.

The quality target is production-shaped behavior for a bounded semantic slice,
not broad memory coverage. Model assistance is permitted only for ambiguous
request relevance. Authorization, lifecycle, sensitivity, scope precedence,
effective-state resolution, and final selection remain deterministic.

## Current-state Evidence

| Current behavior | Evidence | Limitation relative to V1.5 |
| --- | --- | --- |
| `MemoryRetrievalService` filters active, unexpired records and queries the repository by owner | `backend/memory/retrieval.py` | Legacy records and scopes remain workspace-shaped; no V2 assertion/version read model |
| Selection ranks lexical token overlap; active corrections bypass overlap and rank first | `backend/memory/retrieval.py` | Keyword overlap has weak semantic recall; correction bypass can inject irrelevant state |
| Memory retrieval is gated and defaults off | `backend/app/config.py` | No rollout evidence yet supports default-on V1.5 reads |
| Bound chat degrades to generation without memory when memory repository/service access fails | `backend/orchestration/conversation_orchestrator.py` | Degradation exists, but V1.5 must distinguish ordinary unavailability from security anomalies |
| Selected memory is prepended to travel context and does not become a citation | `backend/orchestration/conversation_orchestrator.py`, `backend/orchestration/memory_context.py` | Raw memory text is flattened but remains untrusted prompt content; injection is explicitly not neutralized |
| Selection events carry selected IDs, reasons, and eligible count contracts | `backend/memory/models.py`, `backend/memory/sqlite_repository.py` | Online chat emits events but current evidence does not establish a complete V1.5 selection/use trace lifecycle |

CodeGraph was queried first on 2026-09-08. Material claims above were also
checked against direct source because the active CodeGraph index follows the
primary worktree and later write-pipeline work exists in another linked
worktree.

## Problem Statement

Persisted memory creates no user value until it is used correctly. Naively
injecting every active record causes irrelevant personalization, stale or
conflicting behavior, prompt-injection exposure, unnecessary tokens, and poor
debuggability. Conversely, an overly strict selector produces no continuity.

The Read Pipeline must optimize useful personalization while preserving hard
privacy and correctness constraints. Retrieval correctness and generation-use
correctness are separate: selecting the right memory does not prove that the
model applied it appropriately.

## Goals

1. Select only memory that is authorized, current, relevant, and safe for the
   current turn.
2. Resolve one effective semantic value using current-turn intent, conversation
   scope, user scope, authority, valid time, and conflict state.
3. Prefer abstention over uncertain or irrelevant personalization.
4. Give generation bounded structured context whose authority is explicitly
   below system instructions and the current user request.
5. Continue chat without memory on ordinary read/classifier failure while
   failing closed on owner or policy uncertainty.
6. Produce content-safe evidence explaining selection, non-selection,
   fallback, and model-classifier use.
7. Evaluate retrieval, correct non-use, generation use, privacy, latency, and
   cost separately.

## Non-goals

1. Conversation Summary or Episodic Memory retrieval.
2. Vector database, learned ranker, cross-encoder, or personalized fine-tuning.
3. Inferred-memory auto-promotion.
4. Workspace-scoped memory behavior; workspace scope remains reserved.
5. Changing Write Pipeline lifecycle or user-control semantics.
6. Treating memory as a travel-knowledge citation.
7. Proving the final 1,000-user production target before measured rollout.

## Agreed Decision D01: Hybrid Relevance Routing

### Purpose

Avoid both brittle keyword-only routing and an expensive model call on every
turn.

### Selected approach

1. Deterministic rules resolve clear relevant and irrelevant requests.
2. Only ambiguous requests reach a bounded structured relevance classifier.
3. The classifier returns a closed relevance enum and reason code; it receives
   no database authority and selects no memory ID.
4. Deterministic policy maps the classification and effective state to final
   selection or abstention.

### Why selected

Rule-first routing is fast and auditable for obvious hotel intents. A bounded
classifier improves semantic coverage for indirect requests without handing
authorization, scope, lifecycle, or mutation authority to a model.

### Trade-offs

- Better recall than keyword-only routing, but adds synchronous latency and
  provider cost on ambiguous turns.
- More controllable than model-only routing, but requires a maintained rule
  set, classifier schema, fixtures, timeout, and versioned evaluation.
- Abstention reduces harmful over-personalization, but may miss some useful
  opportunities.

### Required outcomes

The governed vocabulary is initially:

```text
RELEVANT
POSSIBLY_RELEVANT
IRRELEVANT
CURRENT_TURN_OVERRIDES_MEMORY
UNCERTAIN
```

The exact mapping from these outcomes to classifier calls and selection is an
open decision in the interview.

## Agreed Decisions D02-D06: Product Boundary and Quality Posture

### D02: One executable key behind extensible semantic interfaces

**Purpose:** preserve diagnostic clarity while avoiding a hotel-specific
architecture. **Selected approach:** only
`travel.preference.hotel_atmosphere` executes in V1.5, while routing,
effective-state, selection, context, and trace interfaces use canonical key
definitions rather than hard-coded hotel branches. **Why:** one key permits
end-to-end quality attribution; generic interfaces preserve a migration path to
later semantic keys. **Trade-off:** the initial product benefit is narrow and
generic seams must be kept minimal to avoid speculative abstraction.

### D03: Preferences are soft by default

**Purpose:** personalize recommendations without turning taste into a safety or
feasibility constraint. **Selected approach:** `hotel_atmosphere` influences
ranking and explanation when relevant but does not eliminate every alternative.
The current user request may override it for the current turn. **Why:** hotel
atmosphere is preference, not a hard exclusion. **Trade-off:** generation-use
evaluation must judge degree of influence rather than simple inclusion.

### D04: Precision-first rollout with explicit abstention

**Purpose:** minimize trust-damaging false personalization. **Selected
approach:** uncertain relevance or state produces abstention; thresholds may
move toward balanced precision/recall only after labeled evidence exists.
**Why:** an omitted useful preference is less harmful in the first rollout than
an irrelevant or contradictory personal reference. **Trade-off:** early
personalization coverage will be intentionally lower.

### D05: Application-owned `Using memory` affordance

**Purpose:** provide inspectable transparency without interrupting the travel
task. **Selected approach:** the application shows a small `Using memory`
affordance only when an eligible relevant Memory was selected, its durable
selection trace succeeded, a non-empty `MemoryContext` was accepted into the
generation request, and generation began. The detail states that a saved
preference was included for the answer; it does not claim proven causal effect.
Model prose does not own this state. **Why:** these conditions are observable
application facts; generated self-report cannot prove use, while per-turn
counterfactual generation is too expensive. **Trade-off:** the model may still
ignore supplied context. Material influence is measured offline through D33,
not asserted by online UI.

### D06: Read-your-write on the next eligible turn

**Purpose:** keep visible application state and subsequent personalization
consistent. **Selected approach:** after an explicit save, correction, delete,
or Undo commits successfully, the next eligible turn must read the committed
version. Background `SHADOW` candidates remain unreadable. **Why:** showing a
successful state change and then using stale memory breaks user trust.
**Trade-off:** caches must be absent, synchronously invalidated, or guarded by a
version/epoch; request ordering becomes a required dependency of this guarantee.

### D07: Server-enforced per-conversation foreground FIFO

**Purpose:** make transcript order, current-turn context, read-your-write, and
multi-client behavior deterministic. **Selected approach:** the server accepts
turns into a per-conversation FIFO lane with at most one foreground turn in the
active execution state. Separate conversations execute concurrently. The UI
may render queue/cancel state but is never the ordering authority. **Why:**
message-sequence allocation alone cannot prevent two turn lifecycles from
interleaving, and UI-only exclusion fails across devices or retrying clients.
**Trade-off:** a slow turn can cause head-of-line blocking inside its
conversation; durable admission, terminal-state, timeout, cancellation, and
idempotency contracts are required. Background Memory extraction is outside
the foreground lane after its source/outbox commit because it creates unreadable
`SHADOW` state only.

This decision assigns ownership to a Conversation Turn Coordinator that extends
the existing Conversation Orchestrator seam. The Read Orchestrator consumes an
admitted turn and a stable snapshot boundary; it does not own the queue or
conversation lock. A dedicated foreground-turn-ordering ADR is required after
this architecture specification is approved.

### D08: Durable `ConversationTurn` aggregate and logical transcript order

**Purpose:** preserve a durable pairing between one user input and its assistant
outcome even when physical inserts occur concurrently. **Selected approach:** a
`ConversationTurn` owns a server-assigned `turn_sequence` and lifecycle
`QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCELLED`. User and assistant
messages reference the turn and render in `(turn_sequence, position_in_turn)`
order rather than relying on database insertion time. Failure detail is a
governed reason code, not an expanding status vocabulary. **Why:** message-only
sequence can legally produce `user A, user B, assistant A, assistant B`, which
does not preserve conversational pairing. **Trade-off:** introduces a durable
turn schema, migration, and lifecycle invariants, but provides one home for
queue state, cancellation, idempotency, snapshots, and observability.

### D09: Pin the memory snapshot at execution admission

**Purpose:** make read-your-write and retry behavior deterministic. **Selected
approach:** when a turn moves from `QUEUED` to `RUNNING`, after the prior turn
is terminal and its foreground mutations are committed, the Read Pipeline
captures the effective memory revision and selected version IDs. The turn uses
that snapshot throughout generation and retry. **Why:** arrival-time snapshots
can miss the preceding turn's write; repeated reads during one turn can change
the prompt mid-execution. **Trade-off:** a concurrent memory edit after the
turn starts becomes visible only on the next eligible turn.

### D10: Client idempotency key with payload binding

**Purpose:** distinguish network retries from two intentional messages.
**Selected approach:** persistent chat clients provide an idempotency key scoped
to owner and conversation. The server binds it to a canonical payload hash.
The same key and payload returns the existing turn/result; the same key with a
different payload returns a controlled conflict; a new key creates a new turn.
**Why:** server-generated request IDs cannot identify a retry whose first
response was lost, while content/time heuristics can collapse legitimate
duplicate text. **Trade-off:** clients must preserve keys across retry and the
server must retain deduplication state for a governed period.

### D11: Durable asynchronous turn resource with SSE delivery

**Purpose:** accept queued work without tying correctness to one long-lived
HTTP request. **Selected approach:** turn creation returns `202 Accepted` with
`turn_id`, `turn_sequence`, and initial status. The client consumes ordered
server-sent events for queue, execution, content, and terminal updates; a
status resource supports reconnect and bounded polling fallback. **Why:** the
turn remains durable across browser disconnects and queue waits, while SSE fits
the primarily server-to-client event direction with less protocol complexity
than a full WebSocket channel. **Trade-off:** requires an event cursor,
reconnect contract, status endpoint, and client state reconciliation.

### D12: Cancellation preserves committed effects

**Purpose:** stop unwanted work without falsifying already committed history.
**Selected approach:** cancelling a queued turn moves it directly to
`CANCELLED` before memory read or model invocation. A running cancellation
fences the turn, requests best-effort provider cancellation, discards late
provider output, and reaches terminal `CANCELLED`. Cancellation is idempotent.
An explicit Memory mutation committed before cancellation remains committed and
is reversed only through its governed Undo operation. **Why:** a later turn may
already have observed committed state; implicit rollback would violate
read-your-write and auditability. **Trade-off:** the UI must distinguish
cancelled generation from a separately undoable Memory change.

### D13: Failure-class-aware queue progression

**Purpose:** prevent ordinary provider failures from freezing a conversation
without allowing integrity or security anomalies to propagate. **Selected
approach:** transient operational failures receive bounded retries inside the
same turn and pinned snapshot. Exhaustion produces terminal `FAILED`, retains
the user input and controlled failure state, creates no fabricated assistant
message, and releases the next queued turn. Owner mismatch, payload-hash
conflict, impossible lifecycle transition, sequence corruption, or foreign
memory produces terminal failure plus conversation-lane quarantine until
controlled recovery. **Why:** always-stop harms availability; always-continue
hides potentially unsafe state. **Trade-off:** failure classification and
quarantine recovery require explicit operations, metrics, and tests.

### D14: Bounded admission with provisional per-conversation and per-owner limits

**Purpose:** prevent unbounded cost, queue growth, and denial-of-service while
preserving normal bursty chat behavior. **Selected approach:** start with at
most five queued turns per conversation and twenty queued-or-running turns per
owner across conversations. Exceeding admission returns `429` with
`Retry-After` and creates no new turn; an existing idempotency key remains
resolvable. **Why:** one queued turn is unnecessarily restrictive, an unbounded
queue is unsafe, and dynamic admission lacks traffic evidence. **Trade-off:**
the initial numbers are provisional operational budgets and must be measured by
queue/load tests before production claims or tuning.

### D15: Short database claim, renewable lease, and fencing token

**Purpose:** support multiple runtime workers without holding a transaction
through model latency. **Selected approach:** a short transaction claims the
head turn, moves it to `RUNNING`, and records `lease_owner`, `lease_until`,
attempt, and a new fencing token. Work and provider calls occur outside the
transaction. Terminal commit verifies the current token. Expired leases may be
reclaimed under the retry budget; late workers cannot publish. **Why:** process
mutexes do not coordinate multiple instances and long row locks damage pool
availability. **Trade-off:** heartbeats, lease expiry, fencing, reclaim, and
stale-result tests add operational complexity.

### D16: Failure-class-aware bounded retry

**Purpose:** recover likely transient provider faults without making chat waits
or side effects unbounded. **Selected approach:** provider/network transient
failures receive at most two total attempts with bounded backoff and jitter
inside the same turn and snapshot. Memory-read unavailability degrades
immediately to no-memory generation. Validation, authorization, owner,
idempotency-payload, deterministic policy, integrity, and security failures are
not retried; integrity/security quarantines the lane under D13. **Why:** generic
retry amplifies deterministic errors and latency, while no retry wastes cheap
recovery opportunities. **Trade-off:** a transient Memory outage can miss
personalization for one turn in favor of predictable foreground latency.

### D17: Versioned snapshot with pre-publication safety revalidation

**Purpose:** make a turn replayable without publishing output based on revoked
or unsafe state. **Selected approach:** when a turn enters `RUNNING`, persist a
snapshot containing owner, conversation, turn identity/sequence, memory epoch,
selected assertion/version IDs and versions, effective scopes, and
registry/router/policy/selector/classifier versions. Retry reuses the snapshot.
Before publishing, verify the turn fencing token, owner, memory-enabled state,
and deletion/security epoch. Ordinary new writes become visible next turn; if a
selected version is deleted, disabled, or becomes unsafe, discard the generated
output and recompute without memory within the remaining deadline, otherwise
fail controlled. **Why:** a long database snapshot across a model call is
operationally unsafe, while re-reading freely makes one turn internally
inconsistent. **Trade-off:** snapshot evidence and selective invalidation add
storage and a second validation phase.

### D18: Deterministic effective-state precedence

**Purpose:** produce one explainable value for generation without mutating
durable state during reads. **Selected approach:** an explicit normalized
current-turn value governs only the present turn; otherwise an eligible active
conversation-scoped value shadows the eligible active user-scoped default;
otherwise the user default applies; otherwise the pipeline abstains. Multiple
active versions in the same assertion slot are an integrity violation, not a
last-write-wins opportunity: the read abstains, emits content-free integrity
evidence, and quarantines the lane under D13. **Why:** specificity and current
intent are more faithful than recency alone, while silent repair would hide a
broken write invariant. **Trade-off:** corruption reduces availability until
controlled recovery instead of guessing a value.

### D20: Precision-first relevance outcome mapping

**Purpose:** make model-assisted relevance advisory and auditable. **Selected
approach:** only `RELEVANT` may proceed to effective-state selection.
`POSSIBLY_RELEVANT` and `UNCERTAIN` abstain but retain distinct evaluation
reasons; `IRRELEVANT` avoids selection; `CURRENT_TURN_OVERRIDES_MEMORY`
suppresses the historical value for that key. No model self-reported numeric
confidence controls selection. **Why:** this implements D04 precision-first
behavior and creates labeled evidence for later threshold changes. **Trade-off:**
potentially useful ambiguous personalization is intentionally omitted during
the initial rollout.

## Proposed Shared Turn-Intent Seam

Q18 revealed that current-turn understanding is upstream of both Memory Read
and Memory Write. A durable command remains Write Pipeline authority, while a
transient override and relevance outcome are Read Pipeline inputs. Running two
independent semantic analyses would duplicate model cost and can produce
contradictory interpretations.

The proposed seam is a pure `TurnIntentAnalysis` produced once by a rule-first,
bounded analyzer under the Conversation Turn Coordinator. It may contain a
validated relevance outcome, an optional canonical current-turn value, and an
optional proposed durable command intent. Read consumes only relevance and the
transient override. Write revalidates and owns every durable command, policy,
conflict decision, transaction, and application save event. The analyzer never
mutates Memory and its output grants no write authority. This proposal remains
open as D19.

This proposal is one logical module, not two new services. Its external
interface is intentionally small:

```text
analyze_turn(current_message, bounded_completed_context)
-> TurnIntentAnalysis
```

Rule matching, follow-up/context-need detection, safe context construction,
bounded classifier invocation, and output validation are private implementation
steps behind that interface. The follow-up detector is initially a private
deterministic function, not a separately deployed component or public seam. It
becomes a separate module only if a second real caller or independently
replaceable implementation appears. The analyzer may reuse the Write Pipeline's
owned prohibited-content detector through its existing interface; it must not
copy secret patterns or create a competing safety policy.

The module is deliberately limited to memory-related turn meaning. It is not a
general-purpose NLU layer and must not absorb travel planning, tool routing,
generation, authorization, Memory persistence, or prompt assembly.

### D19: Shared memory-related turn analysis

**Purpose:** interpret memory-related turn meaning once without merging Read
and Write authority. **Selected approach:** the Conversation Turn Coordinator
invokes one `TurnIntentAnalyzer` before Read/Write routing. The module uses
private deterministic rules and a private follow-up/context-need detector, then
may make at most one bounded classifier call. It returns relevance, an optional
current-turn override, and an optional proposed durable command intent. Read
consumes only transient relevance/override. Write independently revalidates and
owns every durable mutation and application save result. **Why:** independent
Read/Write analyzers duplicate cost and can disagree, while placing mutation
routing inside Read reverses dependency ownership. **Trade-off:** the shared
contract must stay narrow; if it grows into general NLU it becomes a central
coupling point. The detector remains private until a second real caller or
replaceable implementation justifies a new seam.

### D21: Adaptive completed-context escalation

**Purpose:** understand elliptical follow-ups without sending unnecessary
conversation data or stored Memory to the classifier. **Selected approach:**
deterministic rules first inspect the current message. Conclusive results return
without recent context and without a model call when possible. Only a detected
context-dependent or ambiguous request adds a token-bounded window of completed
turns and invokes the bounded classifier at most once. Queued/running turns,
stored Memory values, internal traces, and prohibited raw content are excluded.
If bounded context remains insufficient, return `UNCERTAIN` and abstain. **Why:**
this retains follow-up quality near an always-context approach while reducing
latency, cost, privacy exposure, and circular relevance bias on self-contained
turns. **Trade-off:** the private escalation detector can miss a dependency;
evaluation must separately measure self-contained, pronoun/follow-up, and
insufficient-context slices. Exact turn and token budgets remain open.

### D22: Database-first eligibility plus application revalidation

**Purpose:** prevent unauthorized or invalid state from reaching ranking while
remaining resilient to adapter or stored-data defects. **Selected approach:**
PostgreSQL query predicates and RLS first constrain owner, relevant keys,
active lifecycle, executable scopes, expiry, ordinary sensitivity, and
deletion/security epoch. Application policy then revalidates owner/scope
consistency, registry/version support, lifecycle, sensitivity, expiry,
assertion/version identity, and pinned snapshot epoch. **Why:** application-only
filtering exposes excess rows to process memory; database-only filtering trusts
one implementation layer too much. **Trade-off:** duplicated critical checks
must share contract tests so defense-in-depth does not become semantic drift. A
foreign row observed after database enforcement drops the whole Memory context,
emits security evidence, and quarantines the conversation lane.

### D23: One key-scoped canonical snapshot query across active scopes

**Purpose:** avoid over-fetch and inconsistent user/conversation reads.
**Selected approach:** one canonical read interface loads active assertion/
version inputs for the routed keys in the authenticated owner scope and current
conversation scope at the pinned memory epoch. It returns only fields needed by
effective-state resolution. A validated current-turn override suppresses the
historical read for that same key; a proposed durable command is independently
read and revalidated by Write Pipeline. **Why:** loading all owner Memory
increases exposure and ranking noise, while separate scope queries can observe
different revisions. **Trade-off:** the adapter query is more specialized, but
its interface hides consistency and filtering complexity from callers.

### D24: One effective item and a 128-token Memory-context ceiling

**Purpose:** keep V1.5 context predictable and proportional to its one
single-valued executable key. **Selected approach:** effective-state resolution
may select at most one Memory item; serialized Memory context has a provisional
hard ceiling of 128 tokens. A structured item is dropped whole rather than
truncated if it cannot fit, producing `CONTEXT_BUDGET_EXCEEDED` and no-Memory
generation. **Why:** quality comes from correct selection, not candidate volume,
and a general ranker would be speculative for one key. **Trade-off:** the
ceiling must be re-evaluated when more keys become executable.

### D25: Canonical structured generation context with lower authority

**Purpose:** give generation useful semantic state without raw-evidence or
instruction injection. **Selected approach:** a provider-neutral,
schema-versioned `MemoryContext` contains only canonical key, normalized value,
effective scope, and `soft_preference` influence. Owner IDs, assertion/version
IDs, raw evidence/display text, confidence, internal reasons, and write/control
state stay out of generation and live only in private traces where applicable.
System/developer policy defines Memory as untrusted supplemental data below the
current user request; it is not a citation and cannot prove read/write state.
No selected item means no empty Memory section. **Why:** canonical enums make
the prompt smaller, safer, and easier to evaluate than prose or raw records.
**Trade-off:** localized nuance from source wording is intentionally discarded;
the Write registry must preserve the semantic distinction needed by generation.

### D27: Strict versioned turn-intent output

**Purpose:** make model-assisted turn understanding bounded, testable, and
non-authoritative. **Selected approach:** `turn-intent-analysis-v1` uses closed
fields for relevance, at most one relevant key, context dependency, an optional
registry-valid current-turn override and intent type, an optional proposed
durable-command intent, and a governed reason code. It contains no free-form
rationale, self-reported confidence, Memory IDs, or persistence instruction.
Unknown or extra fields invalidate the output. **Why:** free text and confidence
cannot be used as deterministic policy, while a strict schema supports fixtures
and safe fallbacks. **Trade-off:** strict validation increases abstention when
provider output drifts.

### D28: One classifier call, 1.5-second provisional deadline, no semantic repair

**Purpose:** improve ambiguous relevance without creating an unbounded
foreground latency loop. **Selected approach:** after deterministic routing and
adaptive context construction, make at most one strict structured classifier
call under a provisional 1.5-second deadline. Transport-only normalization may
occur, but no second model repair or semantic guessing is allowed. Timeout,
provider failure, or invalid schema maps to `UNCERTAIN`, abstention, and
no-Memory generation. **Why:** precision-first behavior makes safe non-use a
valid fallback. **Trade-off:** transient classifier errors reduce
personalization coverage; the deadline must be tuned from measured provider
p95 rather than treated as a permanent constant.

### D29: Code-reviewed versioned deterministic routing rules

**Purpose:** resolve obvious bilingual intent cheaply and reproducibly without
placing policy branches in orchestration. **Selected approach:** a private
versioned rules module behind `TurnIntentAnalyzer` owns clear lodging relevance
and irrelevance markers, follow-up/context-dependency markers, normalized
hotel-atmosphere synonyms, durable-command markers, and governed reason codes.
Rules are code-reviewed and fixture-tested in English and Vietnamese; V1.5 has
no runtime-editable database rules. **Why:** orchestrator `if` chains create
shotgun policy, while model-only routing adds avoidable cost and variance.
**Trade-off:** rules require maintenance and can miss paraphrases, which route
to the bounded classifier rather than silently becoming irrelevant.

### D30: Closed read outcomes and stage-specific reason codes

**Purpose:** explain selection, abstention, degradation, and security blocking
without free-form content. **Selected approach:** canonical outcomes are
`NOT_TRIGGERED`, `SELECTED`, `ABSTAINED`, `DEGRADED`, and
`BLOCKED_SECURITY`. Closed reasons cover irrelevant/current override, no
eligible/effective value, pending conflict, classifier uncertainty/timeout/
invalid output, insufficient context, context budget, memory unavailability,
unsupported registry, integrity violation, and foreign-owner anomaly. **Why:**
outcome answers what happened while reason identifies the stage; free strings
cannot be reliably aggregated and may leak content. **Trade-off:** new failure
semantics require reviewed vocabulary versions rather than ad hoc strings.

### D31: Durable selection snapshot before model; append-only use outcome after

**Purpose:** prevent unaudited Memory injection and preserve historical truth.
**Selected approach:** persist content-free routing, classifier, snapshot,
selection, schema, and token evidence before sending `MemoryContext` to the
generation model. If this persistence fails, degrade to no-Memory generation.
After generation, append terminal delivery/use-assessment evidence rather than
rewriting the selection decision. **Why:** logs alone are not durable evidence
and a final-only trace can be lost after Memory already crossed the prompt
seam. **Trade-off:** trace-store unavailability reduces personalization, but
chat remains available without Memory.

### D32: `Using memory` reports supplied context, not causal effect

**Purpose:** make UI wording verifiably true. **Selected approach:** apply the
revised D05 conditions and expose application-owned detail equivalent to “A
saved preference was included for this answer.” Do not depend on model
self-report. **Why:** causal impact requires a counterfactual; selection and
request admission are directly observable. **Trade-off:** the affordance can
appear when the model ultimately ignores the supplied preference.

### D33: Offline paired generation-use evaluation

**Purpose:** measure whether selected Memory improves behavior rather than only
whether it reached the prompt. **Selected approach:** run paired answers with
the governed Memory context and without it, then combine deterministic checks,
a rubric-based judge, and a human-reviewed calibration sample. Evaluate
appropriate soft influence, over-application, irrelevant mention, current-turn
precedence, answer-quality regression, metadata/privacy disclosure, and
instruction-like content. Do not double-generate every production turn; only
approved offline suites and governed samples use counterfactuals. **Why:** model
self-report and a single-answer judge cannot establish causal utility.
**Trade-off:** paired evaluation roughly doubles generation cost for evaluated
cases and requires judge calibration.

### D34: Precision-first read-quality gates with zero-tolerance safety

**Purpose:** prevent aggregate quality from compensating for privacy or
lifecycle failures. **Selected approach:** require zero cross-owner,
non-retrievable-state, sensitive-state, current-turn precedence, and silent
multi-active-resolution violations. Provisional quality gates are relevance
precision at least 95%, relevance recall at least 80%, correct abstention at
least 95%, and 100% deterministic effective-state/scope truth-table accuracy.
The versioned bilingual dataset starts with at least 200 labeled cases and at
least 30 per mandatory slice. **Why:** V1.5 is precision-first and deterministic
invariants admit no average-error allowance. **Trade-off:** initial coverage is
lower and thresholds require representative labels before product claims.

### D35: Generation-use utility gates plus hard safety gates

**Purpose:** prove Memory improves or preserves answer quality without causing
over-application or disclosure. **Selected approach:** zero current-turn
contradiction, Memory-metadata disclosure, instruction-like Memory compliance,
foreign/sensitive disclosure, and deleted/disabled influence. Provisional
quality gates are at least 90% appropriate soft influence, at most 2%
over-application, at most 1% irrelevant Memory mention, and at least 95% paired
Memory answer win-or-tie. **Why:** merely mentioning a preference is not useful
personalization. **Trade-off:** judge variance requires human calibration and
slice-level reporting.

### D36: Separated latency and classifier-cost budgets

**Purpose:** expose which Read stage adds latency or cost. **Selected approach:**
provisional budgets are deterministic Memory overhead p95 at most 100 ms,
classifier deadline 1.5 seconds, classifier invocation on at most 20% of
eligible turns, classifier input/output at most 1,024/128 tokens,
`MemoryContext` at most 128 tokens, and one turn-intent model call. Also measure
memory-on/off end-to-end delta, cost per 1,000 eligible turns, database
p50/p95/p99, queue wait, and generation wait separately. **Why:** one aggregate
latency number hides the controllable bottleneck. **Trade-off:** these are
starting budgets that may change only through measured review.

### D37: Bounded content-free trace retention

**Purpose:** support debugging and evaluation without creating indefinite
behavioral profiles. **Selected approach:** detailed linkable read traces contain
no raw messages, Memory text, prompts, or answers and expire after a provisional
30 days. User/conversation deletion removes or pseudonymizes linkable IDs;
content-free deletion tombstones remain only when required. Non-linkable
aggregates may remain 90 days. Security evidence follows the separate Security
Policy and deployment/legal review. **Why:** indefinite linkable traces create
privacy risk, while immediate deletion prevents drift/incident analysis.
**Trade-off:** investigations beyond the detailed window rely on aggregates.

### D38: Full-cohort activation with global operational modes

**Purpose:** deliver Read Pipeline to the full target population rather than a
permanent experiment while retaining safe recovery. **Selected approach:**
V1.5 does not build percentage-based cohorts. After offline, integration, load,
security, and generation-use gates pass, all eligible users move to `ACTIVE`.
Global `OFF`, `READ_SHADOW`, and `ACTIVE` modes plus an immediate kill switch
remain mandatory. `READ_SHADOW` may run in pre-production or a bounded
validation window without supplying Memory to generation. **Why:** the product
target is full use by approximately 1,000 users and cohort machinery adds
scope. **Trade-off:** full activation has greater incident blast radius than a
percentage rollout, so hard release gates, monitoring, and tested rollback are
required.

### D39: Explicit 1,000-user load-test envelope

**Purpose:** replace ambiguous account-count language with measurable capacity.
**Selected approach:** the provisional envelope is 1,000 registered/eligible
users, 300 daily active users, 100 concurrent SSE connections, twenty
simultaneous `RUNNING` turns, and ten turn admissions per second for sixty
seconds. **Why:** accounts, active users, connections, admissions, and provider
concurrency stress different resources. **Trade-off:** this is an engineering
baseline rather than a business forecast and must be revised from real traffic
and provider quotas.

### D40: PostgreSQL direct reads before cache

**Purpose:** meet the initial envelope without premature invalidation and stale
state. **Selected approach:** V1.5 reads canonical PostgreSQL state and keeps
only its pinned per-turn snapshot; it adds no Redis or cross-turn process cache.
A version/epoch-aware cache requires a later measured design if database p95
misses D36. **Why:** one structured key and 1,000 users are modest, while cache
invalidation threatens read-your-write, deletion, and multi-instance
consistency. **Trade-off:** PostgreSQL and its pool remain on every relevant
read path.

### D41: Canonical B-tree/partial indexes and current-version uniqueness

**Purpose:** make reads fast while enforcing one current version per assertion
slot. **Selected approach:** final DDL follows the Write schema but must include
current-active uniqueness and B-tree/partial indexes for owner, canonical key,
executable scope/scope ID, and active-state lookup under RLS. Verify the exact
query using `EXPLAIN (ANALYZE, BUFFERS)` on representative data and D39 load.
**Why:** canonical lookup needs relational indexing, not vector similarity.
**Trade-off:** indexes add write/storage cost and must match the real query.

### D42: Bounded runtime and provider concurrency

**Purpose:** protect quotas, connection pools, and latency during bursts.
**Selected approach:** start with a configurable global budget of twenty
simultaneous `RUNNING` turns, one active per conversation, and a provider
semaphore capped by the lower of provider quota and runtime budget. Workers
coordinate through database leases/fences; automatic scaling is deferred.
**Why:** unbounded task creation converts load into failure. **Trade-off:**
conservative limits can increase queue wait and require load-test tuning.

### D43: Zero-tolerance security pages and provisional SLO alerts

**Purpose:** distinguish immediate safety incidents from windowed operational
degradation. **Selected approach:** any cross-owner observation, forbidden
lifecycle/sensitive/deleted prompt use, stale-worker publish, or unaudited
MemoryContext pages immediately. Provisional windowed alerts cover oldest queue
age above 30 seconds, lease reclaim above 1%, Memory degradation above 5%,
classifier timeout/invalid above 5%, deterministic read p95 above 100 ms, trace
failure above 1%, and admission rejection above 1%, with minimum-event guards.
**Why:** API 500 monitoring misses silent personalization/privacy failure.
**Trade-off:** operational thresholds require tuning; zero-tolerance events do
not.

### D44: Global non-destructive Read recovery

**Purpose:** stop unsafe Memory use without disabling chat or deleting
canonical state. **Selected approach:** `ACTIVE`, `READ_SHADOW`, and `OFF` are
checked before read and before publication. `OFF` makes new and queued turns
generate without Memory; running Memory-assisted output is discarded and
recomputed without Memory within deadline or fails controlled. Write has a
separate gate. Recovery proceeds `OFF -> READ_SHADOW -> ACTIVE` after incident
resolution and renewed gates. **Why:** deployment rollback or data deletion is
too slow/destructive for a Read incident. **Trade-off:** every publication path
must honor mode fencing.

### D45: Buffer Memory-assisted content until final safety validation

**Purpose:** make D17 pre-publication deletion/security validation enforceable
for streamed experiences. **Selected approach:** when `MemoryContext` is used,
provider content is buffered server-side while SSE emits status-only progress.
Before any answer content is published, verify fencing, mode, owner, and
deletion/security epoch, persist the terminal result, then deliver content.
Non-Memory turns may stream directly. **Why:** already-streamed tokens cannot be
retracted after a concurrent delete/disable. **Trade-off:** Memory-assisted
turns have worse time-to-first-content and a different streaming profile.

### D46: One bounded transient trace retry, then no-Memory degradation

**Purpose:** preserve `no durable trace -> no Memory` without failing chat for a
recoverable trace-store fault. **Selected approach:** selection/snapshot trace
persistence may retry once only for classified transient database errors within
the Read latency budget. Continued failure sends no `MemoryContext`, generates
without Memory, and emits degradation evidence when observability remains
available. No later selected trace is fabricated. **Why:** post-hoc trace would
misrepresent what crossed the prompt seam. **Trade-off:** temporary trace-store
failure removes personalization for the turn.

### D47: Durable SSE state replay; disconnect does not cancel

**Purpose:** decouple turn correctness from one client connection. **Selected
approach:** durable status events have monotonic event sequence; clients resume
with turn identity and event cursor/`Last-Event-ID`. Disconnect leaves the turn
running; cancellation requires an explicit idempotent endpoint. Final assistant
content is stored once, not duplicated as token rows, and reconnect reads the
terminal result. **Why:** automatic disconnect cancellation is ambiguous across
network drops and multiple clients. **Trade-off:** abandoned turns may consume
provider capacity until explicit cancellation or other governed timeout.

### D48: Typed audited quarantine recovery

**Purpose:** restore integrity without manual database mutation or automatic
unsafe resume. **Selected approach:** quarantine stops new claims for the
conversation. An authorized operator runs a content-free verifier for owner,
turn sequence, active cardinality, idempotency payload, snapshot/version, and
lease/fencing invariants, then selects `CANCEL_AFFECTED`, `REQUEUE_SAFE`, or
`RESUME_UNCHANGED`. Recovery bumps epoch/fence and appends an audit event before
resume. **Why:** time alone cannot repair corruption and direct SQL bypasses
domain evidence. **Trade-off:** requires an operator interface, authorization,
runbook, and tested recovery paths.

### D49: Durable Turn aggregate with database-enforced invariants

**Purpose:** give ordering, queueing, lease, idempotency, snapshot, and recovery
one canonical state owner. **Selected approach:** `ConversationTurn` stores
server identity, direct owner/conversation, turn sequence, idempotency-key hash,
immutable request-payload hash, compact lifecycle/reason, lifecycle timestamps,
attempt/lease/fencing/recovery state, read mode, optional memory epoch, and
optional read-trace identity. Messages store content separately and reference
turn plus position. Database constraints enforce unique conversation sequence,
unique owner/conversation/idempotency hash, at most one running turn per
conversation, terminal timestamps, running lease/fence validity, immutable
payload binding, and RLS. **Why:** deriving these facts from message insertion
order cannot represent concurrency safely. **Trade-off:** schema and migration
complexity increase, but no duplicate shadow coordination store is needed.

### D50: Resource-oriented turn, status, SSE, and cancellation interfaces

**Purpose:** expose durable asynchronous execution without granting clients
server-owned identity or lifecycle authority. **Selected approach:** canonical
interfaces create a turn with `Idempotency-Key`, return `202` plus turn identity,
sequence, status, resource and event locations; owner-scoped status and SSE
reads expose current/terminal state; an explicit cancellation resource is
idempotent. Client payload cannot set owner, sequence, state, lease, fence,
snapshot, or selected Memory. Missing and foreign resources are publicly
indistinguishable. **Why:** one synchronous request cannot safely represent
queueing and reconnect. **Trade-off:** frontend and compatibility migration are
required; first-turn standalone creation remains an open Round-13 contract.

### D51: One deep public Read Pipeline facade

**Purpose:** make it impossible for callers to reorder or omit safety,
effective-state, context, and trace steps. **Selected approach:** one public
`prepare_for_turn(admitted_turn, intent, read_mode) -> MemoryReadResult`
interface returns closed outcome/reason, optional `MemoryContext`, and optional
receipt for snapshot/pre-publication validation. Internal implementation owns
canonical read, eligibility, effective-state resolution, selection/packing,
context composition, and durable trace. `TurnIntentAnalyzer` remains upstream.
**Why:** exposing every internal step creates a shallow interface and lets
orchestration bypass invariants. **Trade-off:** the facade is internally deep
and needs focused integration tests plus injectable adapters.

### D52: Short transaction boundaries around external work

**Purpose:** preserve atomic state without holding locks or connections across
classifier/provider latency. **Selected approach:** admission atomically
allocates turn sequence and writes queued turn, user message, background Memory
outbox, and idempotency binding before `202`; claim atomically verifies queue
head/predecessor and establishes running lease/fence; analysis runs outside a
transaction; read snapshot atomically checks epoch, loads canonical inputs, and
persists selection trace; generation runs outside; terminal commit revalidates
fence/cancel/mode/owner/privacy epoch, writes assistant message, terminal turn,
and terminal event before publication. Invalidated buffered output is discarded
and any no-Memory recomputation occurs outside transactions. **Why:** one long
transaction damages pool/lock behavior; best-effort independent writes create
partial truth. **Trade-off:** lifecycle transitions and retries require explicit
state/fencing tests.

### D53: Atomic first-turn standalone creation and bounded `/chat` compatibility

**Purpose:** preserve immediate authenticated chat while migrating to durable
turn resources. **Selected approach:** canonical turn creation accepts optional
conversation identity. When absent, the admission transaction creates a direct-
owner standalone conversation, first queued turn, user message, background
Memory outbox, and idempotency binding atomically; no hidden workspace exists.
The legacy `/chat` path becomes a time-bounded compatibility adapter over the
same Turn Coordinator, emits deprecation metadata, may wait within its legacy
deadline, and otherwise returns the documented `202` turn location. New clients
use the canonical Turn interface. **Why:** pre-creating a conversation restores
setup ceremony and separate business paths drift. **Trade-off:** legacy clients
must handle the bounded asynchronous fallback during migration.

### D54: Turn/idempotency metadata follows conversation retention

**Purpose:** recognize late retries without retaining plaintext credentials or
duplicated answer content. **Selected approach:** retain idempotency-key hash,
payload hash, turn identity/sequence, terminal state, and required attempt/
fencing/recovery metadata for the conversation lifetime. Clear active lease
ownership/deadline on terminal state. Assistant content remains only in its
message; detailed Read traces keep D37 retention. Conversation deletion removes
or pseudonymizes the binding. **Why:** a fixed short dedupe window can recreate
an old action; metadata is small relative to messages. **Trade-off:** clients
must never intentionally reuse an idempotency key within a conversation.

### D55: Immediate deletion invalidation followed by verified asynchronous purge

**Purpose:** stop all user-visible influence immediately without a long,
failure-prone delete transaction. **Selected approach:** conversation/account
deletion first marks deletion requested, bumps deletion epoch, stops admission,
cancels queued turns, fences running turns, invalidates unpublished snapshots/
results, and enqueues purge atomically. Normal reads stop after commit. A
retryable verified purge removes messages, turns, idempotency hashes, linkable
SSE events, traces/snapshots, derived Memory/evidence, and later projections;
only governed content-free tombstones remain. **Why:** waiting for turns or one
large physical delete weakens immediacy/recovery. **Trade-off:** physical purge
is eventual and requires progress, retry, verification, and incident evidence.

### D56: Memory delete/disable invalidates running snapshots

**Purpose:** prevent publication based on Memory withdrawn during generation.
**Selected approach:** delete/disable mutates lifecycle/setting and bumps the
Memory/privacy epoch in one transaction. A running turn detects the stale epoch
before publication, discards buffered output, and recomputes at most once
without Memory. A rapid Undo does not reintroduce Memory into that already
invalidated turn; the next turn sees the new epoch. **Why:** pinned consistency
cannot override a later privacy withdrawal. **Trade-off:** a concurrent action
can waste one provider call and produce a no-Memory answer for that turn.

### D57: Versioned 320-case bilingual evaluation corpus

**Purpose:** diagnose failures by behavior rather than one aggregate score.
**Selected approach:** use 320 synthetic cases, balanced Vietnamese/English,
with forty primary cases for each of eight slices: self-contained relevance,
irrelevant/correct non-use, current override/durable intent, effective scope/
conflict, follow-up/context sufficiency, owner/lifecycle/sensitivity/deletion,
classifier/fallback failure, and prompt-injection/adversarial use. Split by
scenario/paraphrase family into 160 development, 80 validation, and 80 locked
test cases; paired generation may use a governed representative subset.
**Why:** random examples and template leakage inflate quality claims.
**Trade-off:** labeling and maintenance cost increase, but no real conversation
data enters repository fixtures.

### D58: Human-gold judge calibration

**Purpose:** prevent a judge model from silently defining correctness.
**Selected approach:** maintain sixty blinded paired human-gold cases balanced
by language and use/non-use/override/adversarial behavior. Every hard-safety case
receives human review; at least 20% receives a second review and disagreements
are adjudicated. Pin rubric, prompt, model, and version. Require at least 85%
agreement with adjudicated labels and zero hard-safety false passes;
insufficient review evidence yields `INCONCLUSIVE`. **Why:** self-report and
judge-only scores are not release evidence. **Trade-off:** model/prompt changes
require recurring human calibration.

### D59: Load plus controlled failure/race injection

**Purpose:** prove bounded behavior when dependencies and ordering fail.
**Selected approach:** execute D39 including same-conversation bursts and
cross-conversation parallelism while injecting database latency/deadlock/pool
pressure, classifier/provider faults, trace failure, worker death/lease expiry,
stale fence, Memory/conversation deletion races, SSE reconnect, kill switch,
quarantine recovery, and idempotent redelivery. Hard gates require zero lost
accepted turns, duplicate logical turns, multiple running turns per
conversation, stale output, cross-owner use, and unbounded queue/retry.
**Why:** concurrency invariants cannot be proven by isolated tests.
**Trade-off:** the harness is environment-sensitive and substantial; invalid
infrastructure evidence cannot become PASS.

### D60: Versioned release evidence bundle and owner gate

**Purpose:** make activation reproducible and auditable. **Selected approach:**
produce machine-readable JSON plus human-readable Markdown containing exact
change set/SHA/dirty state, dataset/config/model/judge/runtime versions,
commands/environment, aggregate/per-slice metrics, hard gates, largest
failures, calibration, latency/cost/query plans, load/failure evidence, skipped
checks, and limitations. No raw secrets or real user content appears.
Independent code review and fresh verification precede explicit repository-owner
activation approval. Missing hard-gate evidence yields `INVALID` or
`INCONCLUSIVE`, never PASS. **Why:** “tests pass” does not prove quality,
safety, capacity, or exact evaluated code. **Trade-off:** release preparation
has deliberate evidence overhead.

## D26 Candidate: Completed-context Baseline and Improvement Ladder

The proposed starting envelope is at most two completed turns and 1,024 input
tokens, serialized chronologically. This is a measurable baseline, not a fixed
product truth. Increasing the window blindly can lower quality through stale
topic contamination, lost-in-the-middle effects, prompt-injection exposure,
latency, and cost.

Improvements should follow observed failure classes in this order:

1. **Measure the baseline.** Trace context mode, included turn IDs, token count,
   classifier outcome, abstention reason, antecedent position, latency, and
   correct/incorrect follow-up resolution without logging content.
2. **Tune the bounded envelope.** Change turn/token caps only when labeled data
   shows antecedents consistently outside the current window and quality gain
   exceeds latency/cost regression.
3. **Add structural references.** Give compared hotels/options stable IDs and
   preserve turn linkage so “the second one” can resolve to a structured option
   rather than requiring more prose context.
4. **Select completed turns, not merely the latest turns.** Add a deterministic
   conversation-context selector using recency, explicit references, entity/
   option overlap, and topic continuity under the same token ceiling.
5. **Introduce a bounded working-context projection only if necessary.** A
   validated short projection may preserve active options and unresolved
   references; it is not yet the future durable Conversation Summary memory.
6. **Consider semantic/distant-turn retrieval last.** Embeddings or a semantic
   retriever enter only if evaluation proves material misses remain because the
   needed antecedent is distant and structural selection is insufficient.

Required evaluation slices include self-contained requests, direct pronouns,
ordinal references, option follow-ups, topic shifts, long assistant lists,
bilingual references, insufficient context, and adversarial instruction-like
prior text. Candidate metrics include context-sufficiency accuracy, follow-up
resolution precision/recall, correct abstention, tokens per classified turn,
classifier invocation rate, and added p95 latency/cost.

### D26: Two-turn/1,024-token baseline with evidence-gated improvement

**Purpose:** establish a small, measurable follow-up context envelope and a
disciplined path to improve it. **Selected approach:** begin with at most two
completed turns and 1,024 classifier-input tokens. Apply the improvement ladder
above only when labeled failure slices show the corresponding limitation and
the candidate change improves quality without violating latency, cost,
privacy, or correct-abstention gates. **Why:** blindly increasing context can
reduce quality and auditability. **Trade-off:** some distant references will
initially abstain; quality expansion requires evaluation work before feature
expansion.

## Core Problems the Architecture Must Solve

1. Triggering: determine whether the current request can benefit from memory.
2. Eligibility: enforce owner, lifecycle, expiry, sensitivity, registry, and
   executable-scope constraints before relevance ranking.
3. Effective state: choose the valid conversation override or user default
   without mutating either.
4. Relevance: select only keys useful to the current user task.
5. Abstention: produce an explicit non-use outcome for irrelevant, uncertain,
   conflicting, or unsafe cases.
6. Ranking and limits: order eligible relevant memory and respect item/token
   budgets without allowing rank to bypass policy.
7. Context assembly: serialize normalized semantic data rather than raw source
   transcripts and preserve prompt-authority ordering.
8. Generation use: make preferences soft by default, honor current-turn
   overrides, and avoid unnecessary disclosure that memory exists.
9. Freshness: define when save, delete, undo, scope change, and version change
   become visible to reads.
10. Failure isolation: preserve chat on ordinary memory failure while treating
    cross-owner or policy ambiguity as security failures.
11. Observability: explain selected and non-selected outcomes without storing
    raw prompt, memory, or user content in traces.
12. Evaluation: measure retrieval and use quality, including correct non-use,
    instead of relying on aggregate answer quality alone.

## Proposed Data Flow

```text
authenticated chat turn
-> derive governed ReadRequest
-> deterministic intent/key routing
-> ambiguous only: bounded relevance classification
-> owner-scoped canonical query
-> hard eligibility filter
-> deterministic effective-state resolution
-> relevance selection and abstention
-> token/item budget packing
-> safe structured memory context
-> generation
-> content-safe selection/use trace
```

This flow is proposed, not implemented or approved.

## Concurrency Ownership and Existing Coverage

Foreground turn ordering is not solely a Read Pipeline responsibility. It is a
conversation-runtime concern that the Read Pipeline depends on for a stable
current-turn context and memory snapshot.

| Concern | Owning module/seam | Existing coverage | Remaining gap |
| --- | --- | --- | --- |
| Admit and order foreground turns in one conversation | Conversation Turn Coordinator, extending the Conversation Orchestrator seam | The current orchestrator orders user write, generation, then assistant write inside one `handle_turn` call | No cross-request FIFO, one-active-turn rule, queued state, cancellation, lease, or terminal-state contract |
| Allocate durable message positions | Conversation Unit of Work/read-write adapter | SQLite assigns monotonic per-conversation `sequence` and retries one contested position | Message sequence alone cannot stop two turns from interleaving `user A, user B, assistant B, assistant A` |
| Commit explicit memory changes | Memory Write Pipeline Unit of Work | Approved Write Pipeline requires atomic/idempotent mutation | It does not define foreground turn admission or response order |
| Deliver background memory inference | Memory outbox worker runtime | ADR 0014 defines leases, retries, cancellation, idempotency, and same-identity serialization | This governs background jobs, not synchronous chat turns |
| Choose a memory snapshot for an admitted turn | Read Orchestrator | D06 requires read-your-write on the next eligible turn | Snapshot/watermark semantics depend on unresolved D07 foreground ordering |
| Render queued/cancelled state | Chat UI adapter | No approved target contract | UI cannot be the source of ordering truth because multiple clients may write concurrently |

The current Conversation Persistence Design, ADR 0011, and implementation
preserve ordering inside one turn. ADR 0014 and the Memory Background Shadow
plan govern background Memory jobs. None of those artifacts specifies complete
foreground per-conversation concurrency. D07 is therefore a real architecture
gap, not an already planned Write Pipeline task.

If D07 selects server-enforced FIFO, this specification will record the Read
Pipeline dependency and snapshot contract. A separate ADR must assign durable
ownership of per-conversation foreground admission, ordering, cancellation,
idempotency, and terminal states. The eventual implementation plan must place
that prerequisite before read-your-write verification; it must not hide the
coordination policy inside the Read Adapter.

## Proposed Modules and Dependency Direction

| Module | Interface responsibility | Must not own |
| --- | --- | --- |
| Read Orchestrator | Execute one read request and return context plus trace outcome | SQL details, prompt generation, model mutation authority |
| Request Router | Map turn intent to relevant canonical keys and a relevance outcome | Owner authorization or record access |
| Relevance Classifier Adapter | Return a bounded enum for ambiguous requests | Memory IDs, SQL, final selection |
| Canonical Read Adapter | Query owner-scoped assertion/version projections | Relevance or prompt policy |
| Eligibility Policy | Enforce hard owner/lifecycle/sensitivity/registry gates | Ranking or model calls |
| Effective-state Resolver | Resolve current-turn, conversation, and user precedence | Persistence mutation |
| Selector/Packer | Rank eligible values and enforce budgets | Bypassing hard policy |
| Context Composer | Produce structured untrusted-data context | Raw evidence retrieval or generation calls |
| Read Trace Recorder | Persist content-free outcome evidence | User content, raw memory text, prompts, or answers |

Interfaces will be finalized only after scope, precedence, fallback, latency,
and trace decisions are settled. A module is justified only when its interface
hides meaningful complexity and supplies a real seam for tests or adapters.

## Draft Invariants

1. No query, ranker, classifier, or model receives a foreign owner's memory.
2. `SHADOW`, `PENDING_CONFLICT`, deleted, expired, superseded, restricted, and
   prohibited states never enter generation context.
3. Conversation scope may shadow a user default for that conversation but
   never mutates the user default.
4. Current-turn explicit intent outranks historical preference for that turn.
5. Memory is untrusted data and cannot override system or user instructions.
6. Ordinary read unavailability degrades to no-memory generation; unresolved
   authorization does not.
7. Every selected memory has a deterministic selection reason and effective
   scope.
8. Every non-selection/fallback has a governed content-free reason.
9. Model classification never owns authorization, lifecycle, scope precedence,
   or memory identity.
10. No model text can claim that memory was read, written, updated, or deleted
    as application state.

## Draft Failure Classes

| Failure class | Proposed behavior | Open decision |
| --- | --- | --- |
| Canonical read unavailable | Continue without memory and trace degradation | Retry and latency budget |
| Relevance classifier timeout/invalid output | Deterministic fallback or abstain | Exact fallback per router outcome |
| Owner/policy context missing | Fail closed; no memory context | Whether chat itself continues |
| Foreign-owner row observed | Drop all memory context and emit security evidence | Alert/escalation threshold |
| Conflicting/no effective version | Abstain; no model choice between records | Whether and when UI explains this |
| Context budget exceeded | Deterministic truncation/drop by priority | Initial token/item budgets |
| Trace persistence fails | Chat may continue, operational failure remains visible | Delivery/retry contract |
| Generation ignores/misuses memory | Captured by offline/sample evaluation | Production sampling policy |
| Two turns arrive concurrently in one conversation | Preserve a deterministic conversation order and a defined memory snapshot per turn | D07 ordering/serialization decision |

## Draft Evaluation Dimensions

| Dimension | Question |
| --- | --- |
| Eligibility correctness | Were all and only authorized lifecycle-valid records eligible? |
| Effective-state correctness | Did conversation/current-turn precedence select the intended value? |
| Relevance precision/recall | Did the router and selector retrieve useful keys and abstain appropriately? |
| Correct non-use | Did irrelevant, uncertain, sensitive, pending, stale, and foreign cases remain unused? |
| Generation-use correctness | Did the answer apply the preference softly and consistently with the current request? |
| Privacy/security | Did any foreign, sensitive, raw-evidence, or instruction-like content cross the prompt seam? |
| Reliability | Did ordinary failures degrade without breaking chat or hiding operational evidence? |
| Performance/cost | What latency, model-call, token, and storage overhead did memory add? |

Metric definitions, datasets, sample sizes, provisional budgets, and rollout
gates remain open and will be designed after the product and scope decisions.

## Decision Register

| ID | Decision | Status | Rationale/trade-off location |
| --- | --- | --- | --- |
| D01 | Rule-first relevance routing with bounded LLM classification only for ambiguous turns; deterministic final authority | Agreed 2026-09-08 | Agreed Decision D01 |
| D02 | Execute one key behind extensible semantic interfaces | Agreed 2026-09-08 | Agreed Decisions D02-D06 |
| D03 | Treat hotel atmosphere as a soft preference; current turn may override | Agreed 2026-09-08 | Agreed Decisions D02-D06 |
| D04 | Precision-first rollout with explicit abstention | Agreed 2026-09-08 | Agreed Decisions D02-D06 |
| D05 | Application-owned `Using memory` affordance only on material use | Agreed 2026-09-08 | Agreed Decisions D02-D06 |
| D06 | Explicit committed changes are visible on the next eligible turn | Agreed 2026-09-08 | Agreed Decisions D02-D06 |
| D07 | Server-enforced per-conversation FIFO with one active foreground turn; cross-conversation parallelism | Agreed 2026-09-08 | Agreed Decision D07 |
| D08 | Durable `ConversationTurn`; logical `(turn_sequence, position_in_turn)` transcript order; compact lifecycle | Agreed 2026-09-08 | Agreed Decision D08 |
| D09 | Pin memory revision and selected version IDs when a turn enters `RUNNING` after its predecessor is terminal | Agreed 2026-09-08 | Agreed Decision D09 |
| D10 | Owner/conversation-scoped client idempotency key bound to canonical payload hash | Agreed 2026-09-08 | Agreed Decision D10 |
| D11 | `202` durable turn resource, SSE event delivery, status/reconnect fallback | Agreed 2026-09-08 | Agreed Decision D11 |
| D12 | Idempotent cancellation fences late output and preserves committed Memory until explicit Undo | Agreed 2026-09-08 | Agreed Decision D12 |
| D13 | Ordinary terminal failures release the lane; integrity/security failures quarantine it | Agreed 2026-09-08 | Agreed Decision D13 |
| D14 | Provisional limits: 5 queued/conversation and 20 queued-or-running/owner; excess `429` | Agreed 2026-09-08 | Agreed Decision D14 |
| D15 | Short DB claim, renewable lease, fencing token, no transaction across model call | Agreed 2026-09-08 | Agreed Decision D15 |
| D16 | Two total attempts for transient provider/network failures; memory read degrades; deterministic/security errors do not retry | Agreed 2026-09-08 | Agreed Decision D16 |
| D17 | Pin versioned snapshot; revalidate fencing, owner, enablement, deletion/security epoch before publish | Agreed 2026-09-08 | Agreed Decision D17 |
| D18 | Current-turn value, then conversation scope, then user scope; same-slot multi-active state abstains and quarantines | Agreed 2026-09-08 | Agreed Decision D18 |
| D19 | Shared upstream `TurnIntentAnalyzer`; private detector; Read consumes transient meaning and Write revalidates durable commands | Agreed 2026-09-08 | Agreed Decision D19 |
| D20 | Only `RELEVANT` may select; possible/uncertain abstain; override suppresses historical key | Agreed 2026-09-08 | Agreed Decision D20 |
| D21 | Current message first; add bounded completed turns only for detected ambiguity; no stored Memory; at most one classifier call | Agreed 2026-09-08 | Agreed Decision D21 |
| D22 | PostgreSQL predicates/RLS first, then application revalidation; foreign-row anomaly drops context and quarantines | Agreed 2026-09-08 | Agreed Decision D22 |
| D23 | One relevant-key snapshot query across user/current-conversation scopes; override suppresses same-key historical read | Agreed 2026-09-08 | Agreed Decision D23 |
| D24 | At most one effective item and provisional 128-token Memory-context ceiling; drop whole item on overflow | Agreed 2026-09-08 | Agreed Decision D24 |
| D25 | Versioned canonical `MemoryContext`; no raw evidence/IDs; soft preference below current user authority | Agreed 2026-09-08 | Agreed Decision D25 |
| D26 | At most 2 completed turns/1,024 tokens; tune, structure, select, project, then consider semantic retrieval only through labeled gates | Agreed 2026-09-08 | Agreed Decision D26 |
| D27 | Strict versioned schema; closed enums; optional canonical override/command proposal; no rationale/confidence/IDs | Agreed 2026-09-08 | Agreed Decision D27 |
| D28 | One classifier call; provisional 1.5-second deadline; no semantic repair; invalid/timeout abstains | Agreed 2026-09-08 | Agreed Decision D28 |
| D29 | Private code-reviewed `turn-intent-rules-v1` with bilingual fixtures; no runtime DB rules | Agreed 2026-09-08 | Agreed Decision D29 |
| D30 | Closed read outcomes plus versioned stage reasons; no free-form canonical reasons | Agreed 2026-09-08 | Agreed Decision D30 |
| D31 | Persist content-free selection/snapshot before model; no trace means no Memory; append terminal use evidence | Agreed 2026-09-08 | Agreed Decision D31 |
| D32 | `Using memory` means traced MemoryContext was supplied, not proven causal effect | Agreed 2026-09-08 | Agreed Decision D32 and revised D05 |
| D33 | Offline paired with/without-Memory evaluation plus deterministic checks and human-calibrated judge | Agreed 2026-09-08 | Agreed Decision D33 |
| D34 | Zero safety violations; provisional 95% precision, 80% recall, 95% abstention, 100% deterministic state accuracy; bilingual 200/30 dataset floor | Agreed 2026-09-08 | Agreed Decision D34 |
| D35 | Zero generation safety violations; provisional 90% appropriate influence, 2% over-application, 1% irrelevant mention, 95% paired win-or-tie | Agreed 2026-09-08 | Agreed Decision D35 |
| D36 | Deterministic p95 <=100 ms; classifier <=1.5 s and <=20% eligible turns; bounded tokens/calls with separated latency/cost reporting | Agreed 2026-09-08 | Agreed Decision D36 |
| D37 | Content-free detailed traces 30 days; deletion/pseudonymization; non-linkable aggregates 90 days; security policy separate | Agreed 2026-09-08 | Agreed Decision D37 |
| D38 | Full eligible population after gates; no percentage cohorts; retain global OFF/READ_SHADOW/ACTIVE and kill switch | Agreed 2026-09-08 | Agreed Decision D38 |
| D39 | 1,000 eligible, 300 DAU, 100 concurrent SSE, 20 running turns, 10 admissions/s for 60 s | Agreed 2026-09-08 | Agreed Decision D39 |
| D40 | Direct PostgreSQL reads and per-turn snapshot; no cache before p95 evidence | Agreed 2026-09-08 | Agreed Decision D40 |
| D41 | Current-version uniqueness and B-tree/partial canonical-read indexes verified by query plan/load | Agreed 2026-09-08 | Agreed Decision D41 |
| D42 | Configurable 20-running-turn budget, one/conversation, provider semaphore, DB leases; no initial autoscaling | Agreed 2026-09-08 | Agreed Decision D42 |
| D43 | Immediate security pages plus provisional windowed operational alerts | Agreed 2026-09-08 | Agreed Decision D43 |
| D44 | Global modes checked before read/publish; OFF degrades non-destructively; recover through READ_SHADOW | Agreed 2026-09-08 | Agreed Decision D44 |
| D45 | Buffer Memory-assisted answer until pre-publication safety checks and terminal persistence; status-only progress meanwhile | Agreed 2026-09-08 | Agreed Decision D45 |
| D46 | Retry transient selection-trace write once in budget; otherwise no-Memory degradation and no fabricated trace | Agreed 2026-09-08 | Agreed Decision D46 |
| D47 | SSE disconnect does not cancel; monotonic status replay; final content stored once; explicit cancel endpoint | Agreed 2026-09-08 | Agreed Decision D47 |
| D48 | Quarantine requires authorized verifier, typed recovery action, epoch/fence bump, and audit | Agreed 2026-09-08 | Agreed Decision D48 |
| D49 | Durable direct-owner Turn aggregate for sequence/idempotency/lifecycle/lease/fence/snapshot with DB constraints and RLS | Agreed 2026-09-08 | Agreed Decision D49 |
| D50 | Resource-oriented `202` create, owner-scoped status/SSE, explicit idempotent cancellation; server owns lifecycle fields | Agreed 2026-09-08 | Agreed Decision D50 |
| D51 | One deep `prepare_for_turn` Read facade returning result/context/receipt; analyzer upstream, internals hidden | Agreed 2026-09-08 | Agreed Decision D51 |
| D52 | Atomic admission, claim, read-snapshot, and terminal transactions; analyzer/generation outside transactions | Agreed 2026-09-08 | Agreed Decision D52 |
| D53 | Optional-conversation turn create atomically creates standalone conversation/turn/message/outbox/idempotency; `/chat` is bounded adapter | Agreed 2026-09-08 | Agreed Decision D53 |
| D54 | Hashed idempotency/payload and turn coordination metadata follow conversation retention; no duplicate answer content | Agreed 2026-09-08 | Agreed Decision D54 |
| D55 | Deletion atomically invalidates/fences first, then verified asynchronous purge removes linkable and derived state | Agreed 2026-09-08 | Agreed Decision D55 |
| D56 | Memory delete/disable bumps epoch; stale buffered output is discarded and recomputed once without Memory | Agreed 2026-09-08 | Agreed Decision D56 |
| D57 | 320 synthetic cases, 8x40 slices, bilingual, family-isolated 160/80/80 split | Agreed 2026-09-08 | Agreed Decision D57 |
| D58 | 60 blinded bilingual human-gold pairs, safety review, 20% double review, >=85% judge agreement, zero safety false-pass | Agreed 2026-09-08 | Agreed Decision D58 |
| D59 | D39 load plus controlled DB/model/trace/lease/deletion/SSE/kill-switch/quarantine/idempotency faults with zero invariant breaches | Agreed 2026-09-08 | Agreed Decision D59 |
| D60 | Versioned JSON/Markdown evidence, independent review/fresh verification, explicit owner activation; missing evidence not PASS | Agreed 2026-09-08 | Agreed Decision D60 |
| D61 | Per-user memory enablement and Temporary/Do-not-learn modes | Open | Design-tree audit Round 15 |
| D62 | Same-turn ordering between explicit Write and Read/generation | Open | Design-tree audit Round 15 |
| D63 | Whether Memory influences tool/RAG retrieval or only final generation | Open | Design-tree audit Round 15 |
| D64 | Legacy R6 record coexistence and migration | Open | Design-tree audit Round 15 |

## Explicitly Not Implemented or Proven

1. No V1.5 Read Pipeline package or PostgreSQL read adapter exists yet.
2. The current R6 lexical retriever is legacy evidence, not the target design.
3. No bounded relevance-classifier contract, prompt, timeout, repair, or
   evaluation dataset exists.
4. No effective-state resolver implements current-turn > conversation > user
   precedence for the V2 assertion/version model.
5. No safe structured V1.5 memory prompt contract has been approved.
6. Prompt-injection resistance is not established by newline flattening.
7. No V1.5 retrieval/non-use/generation-use quality baseline exists.
8. No V1.5 latency, token, classifier-call, cost, or trace-retention budget is
   approved.
9. No rollout or rollback gate authorizes enabling memory reads by default.
10. A formal implementation plan does not exist and will not be drafted until
    this specification is approved.
11. No approved ADR or plan currently owns foreground per-conversation FIFO,
    one-active-turn admission, queued/cancelled turn state, or the Read
    Pipeline snapshot boundary for concurrent requests.

## Plan Gate

After the design tree is exhausted, this document will be self-reviewed and
moved to In Review. Only explicit repository-owner approval will authorize a
formal implementation plan. Plan approval remains a separate later gate before
runtime code.

## Required ADRs After Architecture Approval

1. Foreground Conversation Turn Ordering and Snapshot Boundary: server-owned
   per-conversation admission, FIFO ordering, active-turn cardinality,
   cancellation, timeout/recovery, idempotency, and the Read Pipeline snapshot
   dependency.

## Working Glossary

| Term | Meaning in this design |
| --- | --- |
| Eligible memory | A record/version that passes hard owner, lifecycle, sensitivity, registry, and scope policy before relevance |
| Relevant memory | Eligible memory whose canonical meaning can improve the current task |
| Effective memory | The one value that wins deterministic current-turn/conversation/user precedence for a key and condition |
| Abstention | A governed decision to provide no memory context |
| Current-turn override | A present request that changes behavior for this answer without mutating durable memory |
| Relevance classifier | A bounded model adapter used only after deterministic routing cannot decide relevance |
| Selection trace | Content-free evidence of trigger, eligibility, effective scope, selected IDs/keys, reasons, versions, latency, and fallback |
| Use correctness | Whether generation applied selected memory appropriately, distinct from retrieval correctness |

## Approval Record

Not approved. This Draft records one agreed direction and the remaining design
frontier. It authorizes no implementation or implementation plan.
