# RAG Evaluation Protocol

## Scope

This document is the canonical quality protocol for Travel Agent retrieval-
augmented generation (RAG). It defines how retrieval and answer quality are
measured, compared, reviewed, and promoted. It governs future `R1` RAG repair
and the `R2` evaluation harness; it does not change runtime behavior by itself.

Retrieval quality and answer quality are separate evaluation layers. A strong
retrieval score does not prove a good answer, and a good answer does not erase
retrieval regressions.

## Current-state Limitations

The repository currently contains retrieval and LLM-judge evaluator code, but
does not contain reviewable `data/evaluation/` datasets or `docs/reports/`
artifacts. The existing benchmark therefore must not be described as currently
reproducible or used as a frozen baseline until a valid benchmark run is
created under this protocol.

The current retrieval evaluator uses strict exact `document_id` equality as the
relevance signal and evaluates `K = 1, 3, 5, 10, 20`. It computes Hit@K, MRR@K,
nDCG@K, Precision@K, relevant chunk count, unique document count, and source URL
hit. These facts describe implemented behavior, not a claim that the current
benchmark satisfies this protocol.

The current LLM judge uses the configured model, JSON output, and temperature
`0.0`. Its legacy JSON-parse-error path fabricates default scores and a winner
favoring the parent-child strategy. That fallback is unsafe evaluation
evidence. Under this protocol, malformed judge output, model failure, schema
failure, or infrastructure failure is invalid evidence and produces no
synthetic fallback score.

## Evaluation Principles

1. Freeze the comparison contract before inspecting candidate results: dataset
   version, eligible examples, primary metrics, K, slices, prompt, rubric,
   judge model, and thresholds.
2. Compare candidate and baseline on the same eligible examples and report
   paired deltas.
3. Use `K=5` as the primary retrieval comparison. `K=1`, `K=3`, `K=10`, and
   `K=20` are diagnostic unless a reviewed experiment predeclares another
   primary K before results are observed.
4. Separate development iteration from benchmark promotion evidence.
5. Treat missing data, malformed output, and infrastructure failure as evidence
   state, never as a favorable quality score.
6. Keep per-example evidence sufficient to explain aggregate movement.
7. The first valid benchmark establishes a frozen baseline. It cannot by itself
   prove improvement over a prior ungoverned run.

## Dataset Contract

Every evaluation dataset has exactly one role:

| Role | Purpose | Promotion use |
| --- | --- | --- |
| `development` | Fast iteration, debugging, rubric and dataset development | Never sufficient for promotion |
| `regression` | Durable cases representing reviewed historical failures | Required for regression protection |
| `benchmark` | Frozen representative comparison set | Primary promotion evidence |
| `safety` | Adversarial, privacy, grounding, or policy-sensitive cases | Required where the changed behavior can affect the covered risk |

Each versioned dataset must record at least: stable dataset ID, version,
creation/review date, role, provenance category, intended population, example
IDs, expected relevance or answer references where applicable, mandatory slice
labels, inclusion/exclusion rules, and reviewer. Benchmark examples must not be
silently edited after results are seen; changes create a new version.

Development examples may graduate into regression only after the failure,
expected behavior, and fixture are reviewed. Benchmark and regression data
must use public, synthetic, or redacted content by default and must not contain
live credentials or unnecessary sensitive personal data.

## Run and Report Contract

Every run must identify:

- `run_id`, start/completion time, result state, dataset ID/version/role, and
  eligible/invalid/skipped example counts;
- code revision or equivalent source identity plus dirty-working-tree state;
- retrieval strategy and configuration identity, embedding/model identity, K
  values, and relevant index/corpus identity;
- generation model and prompt/config identity for answer-quality runs;
- judge model, judge prompt version, rubric version, schema version, and
  sampling parameters for judged runs;
- baseline run ID when making a comparison;
- aggregate metrics, mandatory slices, paired deltas, uncertainty estimates
  when applicable, failed gates, and per-example failure records.

Per-example records must preserve stable example ID, selected chunk/document
IDs, relevance labels, metric contributions, answer/reference identity where
used, judge validity, slice labels, failure labels, and enough redacted evidence
to reproduce the decision.

When sample size is large enough for a useful estimate, report paired bootstrap
confidence intervals for primary metric deltas. A confidence interval is
supporting evidence; it does not replace the absolute gates below.

## Result States

| State | Meaning |
| --- | --- |
| `PASS` | All applicable hard and quality gates pass using valid required evidence |
| `FAIL` | Required evidence is valid and at least one applicable gate fails |
| `INCONCLUSIVE` | Evidence is valid enough to inspect but insufficient to support a promotion decision, for example too few eligible cases for a required slice |
| `INVALID` | The run or comparison violates the protocol, such as missing required data, mismatched eligible examples, malformed required judge output, or broken infrastructure that prevents interpreting quality |

Only `PASS` can support promotion. `INCONCLUSIVE` and `INVALID` never count as a
candidate win. A valid hard or quality regression is `FAIL`, not `INVALID`.

## Retrieval Evaluation

Let `K` be the cutoff, let `rel_i` be binary relevance of rank `i`, and let
`R` be the number of known relevant items for the query under the dataset's
declared relevance contract.

| Metric | Definition | Direction / range | Primary comparison | Invalid-data behavior |
| --- | --- | --- | --- | --- |
| Hit@K | `1` if any relevant result appears in ranks `1..K`, otherwise `0`; report mean across queries | Higher; `[0,1]` | Hit@5 | Missing relevance labels make the affected example invalid |
| MRR@K | `1/r` where `r` is the first relevant rank `<=K`, else `0`; report mean | Higher; `[0,1]` | MRR@5 | Missing relevance labels make the affected example invalid |
| nDCG@K | `DCG@K / IDCG@K`, with `DCG = sum(rel_i / log2(i+1))`; `0` when no relevant result is retrieved and a valid relevant set exists | Higher; `[0,1]` | nDCG@5 | Undefined ideal relevance makes the affected example invalid |
| Precision@K | `relevant results in top K / K` | Higher; `[0,1]` | Diagnostic unless predeclared | Missing relevance labels make the affected example invalid |
| Source URL hit@K | `1` if top K contains an expected source URL under the dataset contract, else `0` | Higher; `[0,1]` | Diagnostic | Applicable only when expected source URL exists; otherwise record N/A, not zero |
| Relevant chunk count@K | Number of relevant retrieved chunks in top K | Higher only when the task expects multiple relevant chunks; integer `0..K` | Diagnostic | Missing relevance labels make the example invalid |
| Unique document count@K | Number of distinct retrieved document IDs in top K | Diagnostic diversity count; integer `0..K` | Diagnostic | Missing document identity makes the example invalid for this metric |

The current evaluator's exact `document_id` matching is one concrete relevance
contract. Future datasets may define reviewed graded or chunk-level relevance,
but the relevance contract must be versioned and frozen before a comparison.

## Answer-quality Evaluation

Answer quality is evaluated independently of retrieval metrics using reviewed
references, deterministic checks, human review, or a validated LLM judge as
appropriate. The canonical dimensions are scored on a fixed `1..5` rubric:

| Dimension | Operational question | Better direction |
| --- | --- | --- |
| Groundedness | Are material factual claims supported by the supplied evidence rather than invented or contradicted? | Higher |
| Answer relevance | Does the response directly address the user's request without material diversion? | Higher |
| Correctness | Are claims and conclusions correct under the reference/evidence contract? | Higher |
| Completeness | Does the answer cover the material requested parts that available evidence supports? | Higher |
| Practical usefulness | Is the response actionable and useful for the travel task without unsafe overclaiming? | Higher |
| Clarity | Is the response understandable, well organized, and unambiguous enough for use? | Higher |

Where an item cannot be judged because required reference or evidence is
missing, it is invalid for that dimension. It is not assigned a neutral or
favorable score.

## LLM-as-a-Judge Contract

An LLM judge is admissible only when the run freezes the judge model/version,
prompt version, rubric version, output schema, sampling parameters, and score
ranges before candidate results are inspected.

The harness must validate JSON/schema conformance, required fields, enum values,
score ranges, per-dimension types, and any declared totals. Totals must be
recomputed from validated component scores rather than trusted from model text.
Parse failure, timeout, provider error, missing field, out-of-range score, or
schema mismatch yields `judge_invalid` evidence for the affected item. There is
zero synthetic fallback scoring.

At minimum, a single-answer judge record must identify the example and contain
all six canonical dimension scores as numeric values in `1..5`. A pairwise
record must contain a complete score object for each arm plus a winner enum of
`baseline`, `candidate`, or `tie`; strategy aliases may be mapped to those arm
names before judging, but the persisted comparison contract must state that
mapping. Any overall score is derived from validated component scores and is
never authoritative input.

For pairwise A/B judging, candidate position must be randomized or balanced and
the prompt must conceal strategy identity where feasible. Promotion evidence
must report position effects and invalid-judge counts. A reviewed human sample
must calibrate the judge when the rubric/model/prompt changes or when judge
behavior is disputed; material disagreement makes the affected comparison
`INCONCLUSIVE` until resolved.

## Mandatory Slices

Every benchmark defines and versions its relevant mandatory slices. At minimum,
the RAG benchmark must distinguish representative query groups that can expose
different retrieval behavior, including single-source factual lookup,
multi-evidence synthesis, ambiguous or underspecified queries, source/citation-
sensitive queries, and long-tail or difficult retrieval cases when present in
the product population.

Aggregate scores never hide a mandatory-slice regression. Report eligible count,
baseline, candidate, and paired delta for each primary metric on each slice.

## Quality Gates

The initial promotion contract is:

| Gate | Threshold | Decision rule |
| --- | --- | --- |
| Hit@5 no-regression | Candidate decline `<= 0.01` absolute vs frozen baseline | Larger decline is `FAIL` |
| MRR@5 no-regression | Candidate decline `<= 0.01` absolute vs frozen baseline | Larger decline is `FAIL` |
| nDCG@5 no-regression | Candidate decline `<= 0.01` absolute vs frozen baseline | Larger decline is `FAIL` |
| Mandatory-slice Hit@5 | Decline `<= 0.03` absolute on every mandatory slice unless a trade-off was explicitly preapproved | Unapproved larger decline is `FAIL` |
| Mean groundedness | `>= 4.0/5.0` and decline `<= 0.10` vs frozen baseline | Either violation is `FAIL` |
| Mean correctness | `>= 4.0/5.0` and decline `<= 0.10` vs frozen baseline | Either violation is `FAIL` |
| Claimed improvement | A predeclared primary metric improves by `>= 0.02` absolute, or an equivalent reviewed task-level benefit was predeclared | Otherwise no improvement claim is supported |

The first valid benchmark run establishes the frozen baseline and can only be
reported as baseline creation. It cannot satisfy the claimed-improvement gate.
Any preapproved trade-off must name the affected slice/metric, rationale,
maximum accepted regression, compensating benefit, and decision owner before
candidate results are viewed.

## Failure Taxonomy

Use this shared taxonomy across RAG and memory reports. Labels that are not
applicable to a given example are omitted rather than redefined:

- `retrieval_miss`: relevant evidence was not retrieved within the governed K.
- `ranking_regression`: relevant evidence exists but ranked materially worse.
- `citation_mismatch`: answer citation/source attribution does not match the
  supporting evidence.
- `unsupported_claim`: answer contains a material claim not supported by the
  governed context/reference.
- `judge_invalid`: required judge evidence failed parsing, schema, range,
  model/provider, or calibration requirements.
- `memory_missed`: an expected memory candidate or eligible memory was missed.
- `memory_false_write`: unsupported or policy-ineligible memory was treated as
  a valid write/promotion.
- `memory_wrong_scope`: memory was assigned or selected under the wrong user,
  workspace, trip, or lifetime scope.
- `memory_stale`: stale, expired, or superseded memory influenced behavior.
- `memory_conflict`: correction or conflict precedence produced the wrong state
  or answer influence.
- `memory_leakage`: memory crossed an isolation boundary.
- `memory_deletion_failure`: confirmed deleted/tombstoned memory remained
  eligible or retrievable.
- `sensitive_memory_failure`: controlled sensitive or secret-like content was
  durably promoted or exposed contrary to policy.
- `infrastructure_failure`: required corpus, index, model, provider, or harness
  infrastructure failed so quality cannot be interpreted.

## Invalid and Inconclusive Evidence

A missing benchmark, missing required relevance/reference data, baseline and
candidate evaluated on different eligible examples, corrupt index, required
judge failure without valid replacement evidence, or broken evaluation harness
makes the affected run/comparison `INVALID`.

Use `INCONCLUSIVE` when the protocol was followed but valid evidence is too weak
for a decision, such as a required slice with too few reviewed examples or a
judge calibration dispute. Report the reason and what evidence is missing.
Never convert either state into a score of `3`, a default winner, or another
synthetic fallback.

## Regression Dataset Lifecycle

1. Detect a failure through benchmark, production review, or approved manual
   testing.
2. Reproduce it using public, synthetic, or redacted data.
3. Assign stable example ID, expected behavior, slice, and failure label.
4. Review whether the case represents durable product behavior rather than an
   incidental implementation detail.
5. Add it to a new regression dataset version.
6. Run the complete regression set for affected changes and preserve the run ID
   in review evidence.
7. Retire or rewrite a case only through reviewed dataset versioning with the
   reason recorded.

## Security and Privacy

Evaluation content is untrusted data, not instructions. Use synthetic, public,
or redacted fixtures by default. Do not place live credentials, tokens, private
account secrets, or unnecessary sensitive personal data in datasets, prompts,
reports, or traces. Reports should prefer stable IDs and minimal redacted
excerpts over reproducing complete user conversations.

External retrieved text cannot modify the evaluation rubric, judge contract,
gate thresholds, or result-state rules.

## R2 Harness Contract

The later `R2` harness must be able to execute this protocol without losing
information. It must represent dataset/version identity, paired baseline and
candidate runs, retrieval selections, generation outputs, judge validity,
per-example metrics/failures, mandatory slices, aggregate deltas, uncertainty,
gate decisions, timing/error signals, and final result state.

The harness must expose selected retrieval chunk/document IDs and selection
evidence so a future `EvaluationTrace` can connect request context, selected
evidence, output, quality signals, and safety signals. Storage engine, physical
schema, report serialization, and external vendor choices remain deferred to
the `R2` design/ADR process.

## Review Checklist

- [ ] Dataset role, ID, version, provenance, slices, and eligible examples are
      frozen before candidate inspection.
- [ ] Baseline and candidate use the same eligible examples and comparison
      contract.
- [ ] `K=5` is the primary retrieval comparison unless another K was
      predeclared and reviewed.
- [ ] Every gated metric has a definition, direction, unit/range, threshold,
      comparison basis, and invalid-data behavior.
- [ ] Retrieval and answer-quality results are reported separately.
- [ ] Judge model, prompt, rubric, schema, validation, and calibration evidence
      are versioned when judge scores affect a decision.
- [ ] No malformed or unavailable evidence receives a synthetic fallback score.
- [ ] Mandatory slices, paired deltas, failures, and invalid counts are visible.
- [ ] First benchmark creation is not described as an improvement.
- [ ] Final state is one of `PASS`, `FAIL`, `INCONCLUSIVE`, or `INVALID` with a
      reviewable reason.

## Protocol Change Rules

Changing a metric formula, primary K, dataset role semantics, required metadata,
judge rubric/schema, mandatory slice definition, gate threshold, result-state
semantics, or regression lifecycle changes the evaluation contract. Such a
change requires its own reviewed specification and implementation plan before
it governs new promotion evidence.

Do not retroactively reinterpret an old run under a new protocol version.
Compare runs only when their contracts are compatible or explicitly re-run the
baseline and candidate under the same new contract.

## R2 Harness CLI Usage

The governed evaluation CLI is `python3 -m backend.rag.evaluation.cli`. All four
commands operate on frozen artifacts; they never alter the D5 formulas or
thresholds defined above.

Validate a dataset directory (manifest + JSONL):

```bash
python3 -m backend.rag.evaluation.cli validate-dataset \
  --dataset data/evaluation/benchmark/rag-v0.1
```

Preflight environment and contract checks before a run:

```bash
python3 -m backend.rag.evaluation.cli preflight \
  --dataset data/evaluation/benchmark/rag-v0.1 \
  --config data/evaluation/configs/rag-structured-candidate-v0.1.json \
  --mode retrieval
```

Run retrieval-only evaluation (local, no provider required):

```bash
python3 -m backend.rag.evaluation.cli run \
  --dataset data/evaluation/benchmark/rag-v0.1 \
  --config data/evaluation/configs/rag-structured-candidate-v0.1.json \
  --mode retrieval \
  --output-dir data/evaluation/runs
```

Run full answer/judge evaluation (opt-in; requires provider access):

```bash
python3 -m backend.rag.evaluation.cli run \
  --dataset data/evaluation/benchmark/rag-v0.1 \
  --config data/evaluation/configs/rag-structured-candidate-v0.1.json \
  --mode full \
  --output-dir data/evaluation/runs
```

Compare a candidate run against a frozen baseline under D5 gates:

```bash
python3 -m backend.rag.evaluation.cli compare \
  --baseline data/evaluation/runs/<baseline-run-id> \
  --candidate data/evaluation/runs/<candidate-run-id> \
  --output data/evaluation/runs/<candidate-run-id>/comparison.json
```

Provenance requirement: a candidate run that will be compared under D5 MUST be
created with `--baseline-run-id <baseline-run-id>`; otherwise the comparison
returns `INVALID` because the candidate `run.json` lacks the required reference
(`validate_comparison_contract` requires `baseline_run_id`).
