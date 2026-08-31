---
name: Technical debt
about: Describe a bounded maintenance risk and measurable improvement
title: ""
labels: ""
assignees: ""
---

Suspected vulnerabilities or confidential security evidence belong in
[SECURITY.md](../../SECURITY.md), not in this public issue. Use synthetic,
minimal, or redacted evidence. Do not include credentials, private user data,
sensitive production traces, or unnecessary full prompts/conversations.

Creating an issue does not authorize implementation. Maintainers classify the
change and identify the required specification, architecture, plan, evaluation,
security, and owner-review gates before implementation starts.

## Current Evidence and Affected Boundary

What code, documentation, workflow, interface, or operational boundary is
showing maintenance cost or risk?

## Cost, Risk, or Maintenance Burden

What slows development, hides defects, increases review risk, or makes future
changes harder?

## Desired Measurable Improvement

What measurable boundary, quality, speed, clarity, or reliability improvement
should exist after the work?

## Scope

What is included in this debt work?

## Non-goals

What cleanup, redesign, or behavior change should remain outside this request?

## Exit Criteria

List observable criteria a reviewer can verify before closing the debt item.

## Dependencies, Compatibility, and Migration

Name affected dependencies, compatibility assumptions, migration needs, or
consumer impacts.

## Verification Expectations

Name the tests, static checks, review methods, or evaluation evidence that
should prove the improvement.

## Rollback Expectations

Describe how the change could be backed out before Git delivery or after a
deployment when applicable.

## Dependencies and Related Artifacts

Link related issues, specs, plans, ADRs, documents, experiments, or external
references.

## Maintainer Classification and Governance Routing

Maintainers record the change level, required spec, implementation plan,
architecture approval, ADRs, evaluation evidence, and repository-owner approval
gate here after intake review.
