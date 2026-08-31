---
name: Experiment
about: Propose a controlled experiment with baseline, metrics, and promotion gates
title: ""
labels: ""
assignees: ""
---

Suspected vulnerabilities or confidential security evidence belong in
[SECURITY.md](../../SECURITY.md), not in this public issue. Use synthetic,
minimal, or redacted evidence. Do not include credentials, private user data,
sensitive production traces, or unnecessary full prompts/conversations.

Creating an issue does not authorize implementation or production promotion.
Experiment results are evidence only. Maintainers classify any follow-up
product, runtime, evaluation-protocol, architecture, or release work through the
normal governance gates.

## Hypothesis

What claim should the experiment test?

## Baseline

What current behavior, metric, dataset, prompt set, retrieval configuration, or
workflow is the comparison point?

## Intervention or Independent Variable

What single change is being tested against the baseline?

## Fixed Conditions and Dataset or Provenance

Which prompts, data, fixtures, source material, model settings, retrieval
settings, or environment conditions remain fixed? State dataset/content
provenance and any known limitations.

## Metrics

Which quantitative or qualitative metrics will be recorded?

## Safety Gates

Which security, privacy, data-isolation, memory, evaluation, or operational
conditions stop or reject the experiment?

## Promotion Threshold

What result would justify a separately governed proposal to promote, continue,
or productize the idea?

## Expected Failure Interpretation

How should weak, mixed, unsafe, or inconclusive results be interpreted?

## Result Location

Where will the completed result, evidence, and analysis be recorded?

## Promotion Decision

After completion, maintainers record one decision: `reject`, `continue
experimenting`, or `propose separately governed product/runtime work`.

## Scope

What is included in this experiment?

## Non-goals

What implementation, productization, release, or evaluation-protocol change is
outside this experiment?

## Exit Criteria

List observable criteria a reviewer can verify before closing the experiment.

## Dependencies and Related Artifacts

Link related issues, specs, plans, ADRs, documents, experiments, or external
references.

## Maintainer Classification and Governance Routing

Maintainers record the change level, required spec, implementation plan,
architecture approval, ADRs, evaluation evidence, and repository-owner approval
gate here after intake review.
