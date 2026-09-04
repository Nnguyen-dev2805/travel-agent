# Incident Response Runbook

## Scope

This runbook owns first response for security and operational incidents in
Travel Agent. It defines detection, severity/scope classification, reversible
containment, privacy-safe evidence, governed eradication, checked recovery, and
post-incident review.

It does not pre-approve permanent code, configuration, architecture, dependency,
data, provider, or Git changes. Repository security policy lives in
[Security Policy](../../SECURITY.md).

## Incident Principles

1. Reduce exposure first using the least destructive reversible action.
2. Preserve enough evidence to review the event without creating a second data
   leak in logs, issues, screenshots, or reports.
3. Never record live secret values. Use credential identifiers or redacted
   fingerprints only when useful.
4. Prefer synthetic/redacted user examples and stable IDs over full content.
5. Separate immediate containment from permanent remediation.
6. Treat Package 5 memory hard-gate failures as zero-tolerance failures; do not
   average them away.
7. Do not restore service merely because a process starts. Verify the affected
   security, integrity, and quality boundary first.

## Severity and Scope Classification

Classify by impact and scope, not by a promised response time:

| Severity | Guidance |
| --- | --- |
| S1 - Critical | Active or credible broad compromise, secret misuse, public exposure of unsafe user-scoped capability, cross-user leakage, destructive integrity loss, or supply-chain compromise with material exposure |
| S2 - High | Confirmed sensitive-data exposure or unauthorized behavior with bounded scope, deleted-memory retrieval, provider compromise affecting protected data, or repeated trust-boundary violation |
| S3 - Moderate | Operational degradation or contained security weakness with no confirmed sensitive exposure, but recovery or review is required |
| S4 - Low | Minor bounded operational issue, false positive, or near miss with no material confidentiality/integrity impact |

Always record affected environment, component, release/commit when known, data
class, user/workspace scope when applicable, and whether exposure is ongoing.
Unknown scope increases caution; it is not evidence of no impact.

## Detect and Record

**Goal:** establish that an incident or credible anomaly exists without copying
sensitive data unnecessarily.

Minimum evidence:

- timestamp and reporter/source;
- symptom/failure class;
- affected component/environment;
- release/commit/artifact identity when known;
- redacted identifiers and minimal excerpt if needed;
- whether the event is still active.

Advance only when there is enough evidence to classify a provisional severity
and scope. If evidence itself contains secrets/private data, redact before it is
stored in a repository artifact.

## Contain

**Goal:** stop or reduce ongoing exposure while preserving the ability to
investigate and recover.

Prefer reversible controls such as disabling the affected feature/path,
stopping the exposed local service, revoking a compromised credential through
its owner/provider, restricting an unsafe environment, or temporarily removing
an untrusted dependency/provider from the active path when an approved fallback
already exists.

Record the containment action, owner, affected scope, and verification that the
unsafe behavior stopped. Do not perform broad data deletion, dependency
upgrades, architecture changes, or Git delivery as improvised containment.

## Preserve Evidence

**Goal:** retain reviewable facts without creating a sensitive-data archive.

Prefer IDs, timestamps, hashes, failure labels, version identifiers, counts,
configuration names without values, and short redacted excerpts. Never preserve
live tokens, complete `.env` output, unnecessary full conversations, or private
screenshots in repository docs/issues.

Evidence must be sufficient to explain scope, sequence, containment, and
recovery checks. If the investigation requires sensitive material, keep it in
an approved private evidence location rather than the public repository.

## Eradicate

**Goal:** remove the root cause after containment.

Permanent remediation that changes code, configuration, authentication,
authorization, storage, data lifecycle, dependencies, deployment architecture,
provider behavior, or repository files must follow the normal approved spec,
architecture/ADR when required, implementation plan, verification, and owner
review gates.

Advance only when the remediation scope and verification method are explicit.
An operational workaround is not evidence that the root cause is eradicated.

## Recover

**Goal:** restore the affected capability only after the compromised boundary is
safe enough for the intended environment.

Recovery evidence should include the exact version/state restored, health and
readiness checks, affected security control verification, data-integrity checks,
and applicable RAG/memory quality/safety gates.

For a public environment, the complete
[Deployment Readiness](./deployment.md) gate still applies. A failed Package 5
memory hard gate blocks recovery of memory-aware behavior.

## Post-incident Review

Review:

1. root cause and contributing conditions;
2. affected users/workspaces/data classes and confidence in the scope;
3. detection gap and why existing checks did or did not catch it;
4. containment speed and side effects without inventing an SLA;
5. evidence quality and privacy handling;
6. recovery verification;
7. regression/evaluation cases required to prevent recurrence;
8. governance work needed for permanent fixes.

Use synthetic or redacted regression fixtures. Do not copy leaked private data
into a permanent test just because it reproduced the incident.

## Scenario Playbooks

Each playbook below separates first response from permanent remediation.

| Scenario | Detect and scope | Reversible containment | Redacted evidence | Recovery criteria | Permanent-fix routing |
| --- | --- | --- | --- | --- | --- |
| Credential or token exposure | Identify credential owner/type, exposure surface, first/last known exposure, and whether misuse is suspected; never record the value | Revoke/disable or rotate through the owning provider/account; stop the path still emitting it | Credential name/ID, redacted fingerprint if approved, timestamps, exposure location, rotation/revocation result | Old credential is unusable, replacement is injected through approved secret handling, logs/docs no longer expose it | Root cause change through normal spec/plan; add regression/secret-safety checks where appropriate |
| Private/user data in logs, issues, traces, screenshots, or reports | Identify data class, artifact/location, affected scope, and access audience | Restrict/remove public exposure using the platform's reversible/private controls where available; stop further logging/capture | Artifact IDs, redacted field names, minimal sample, affected count/scope | Exposure path is closed, unnecessary copies are removed or access-restricted under approved process, telemetry behavior is verified | Logging/trace/privacy changes through governed implementation; add redaction tests |
| Unauthorized access or cross-user/cross-workspace leakage | Identify users/workspaces, resource IDs, read/write path, and whether leakage is ongoing | Disable the affected user-scoped feature or exposure path; restrict access using already-approved controls | Stable user/workspace/resource IDs, counts, redacted examples, release identity | Isolation tests pass, affected access path is verified, applicable memory leakage gates are `0` | Authentication/authorization/isolation changes are Level 3 when required and need approved design/ADRs |
| Deleted or tombstoned memory becomes retrievable | Confirm deletion state, memory ID/scope, retrieval path, and whether answer behavior used it | Disable memory retrieval or the affected memory feature when a reversible feature boundary exists | Memory ID, tombstone/deletion state, retrieval selection IDs, no private value unless strictly necessary | Deleted-memory retrieval count returns to `0` and deletion lifecycle verification passes | Memory storage/deletion fix under approved memory/storage spec and Package 5 regression case |
| Unsafe public exposure of unauthenticated or wildcard-CORS API | Identify exposed origin/network path, API version, authentication state, and CORS behavior | Remove public exposure or stop the affected service at the existing network/process boundary; do not "accept risk" via documentation | Endpoint/origin identifiers, configuration names, timestamps, access evidence without credentials | Public path is no longer reachable until auth/authz, restrictive CORS, TLS, and other deployment gates pass | Production security/deployment architecture through approved Level 3 work and required ADRs |
| Data corruption, accidental deletion, or vector-store integrity loss | Identify store/path, last known-good state, affected collections/records, and whether writes continue | Stop writes/indexing to the affected state; preserve current state before rebuild/restore | Store/collection IDs, hashes/counts, redacted validation errors, backup/version identity | Integrity checks pass against known source/evaluation evidence and restore/rebuild provenance is reviewable | Data/index/storage repair through approved workflow; destructive recovery requires explicit target and recoverability evidence |
| External model/provider outage or suspected compromise | Distinguish availability failure from suspected confidentiality/integrity compromise; identify requests/data classes sent | For outage, disable/reduce affected capability if no approved fallback; for compromise, stop data transmission and revoke affected credentials as appropriate | Provider/model identifiers, timestamps, request IDs, error class, data-class summary without prompt bodies | Provider path is trusted/reachable again, credentials are safe, degraded behavior is verified, required quality checks pass | Provider/adaptor/security changes through approved design; no silent provider swap |
| Malicious retrieved content or prompt injection crosses trust boundary | Identify source document/URL ID, retrieved chunk, instruction-like content, tool/memory/action influenced, and affected requests | Disable the affected source/retrieval/action path or feature gate using an existing reversible control | Source/chunk IDs, redacted malicious excerpt, selected-context IDs, affected action IDs | Retrieved content is treated as data, unsafe action/write no longer occurs, regression case passes | Context/tool/memory trust-boundary changes through approved spec/architecture and evaluation regression |
| Dependency or container-image compromise | Identify package/image/version/digest, affected runtime/builds, provenance, and exposure window | Stop using the suspected artifact; roll back to an already-approved known-good artifact when available | Package/image identity, digest/hash, advisory/reference, affected build IDs; no credentials | Known-good artifact is restored, build/runtime verification passes, secret/data exposure review is complete | Pin/upgrade/replace through governed dependency or architecture change with supply-chain verification |

## Permanent-fix Governance

Containment authority does not become permanent-change authority. Code,
configuration, dependency, data-model, storage, authentication, authorization,
deployment, provider, or observability changes must return through the
repository's normal specification and implementation-plan process. Architecture
changes require the corresponding architecture approval and ADRs.

Incident urgency may justify stopping an unsafe service or revoking a credential
through its operational owner. It does not authorize destructive Git history
rewrites, broad data deletion, or unreviewed production architecture changes.

## Escalation and Stop Conditions

Stop and escalate the incident decision when:

- scope is unknown and the next action could destroy evidence or data;
- a real secret or private user dataset would need to be copied into a public
  artifact to continue;
- containment would remove persistent data without a recoverability check;
- recovery depends on an unapproved production architecture/provider choice;
- a Package 5 hard safety gate still fails;
- a permanent fix lacks the required spec, plan, architecture approval, or ADR;
- public production would resume while any mandatory deployment gate remains
  missing or unknown.

The safe result under unresolved evidence is continued containment or a blocked
capability, not an unsupported production-readiness claim.
