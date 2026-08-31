# Third-party Notices

## Purpose and Scope

This file is the canonical human-reviewable inventory for verified third-party
notices and attribution obligations associated with material included or
redistributed by this repository.

It is not a lockfile, dependency resolver, software bill of materials (SBOM),
automated vulnerability database, or complete transitive release audit.
Release-time artifact scanning and legal review remain separately governed work.

## Project License Boundary

Project-authored source and documentation are licensed under `Apache-2.0` by the
root [LICENSE](LICENSE) unless an approved file or subtree explicitly states
different terms.

The root license does not relicense third-party code, dependencies, models,
datasets, generated artifacts, copied assets, or external travel content that
the project does not own. Those materials retain their own terms and require
separate provenance review before redistribution.

## Included or Redistributed Material

The repository includes a Claude workspace skill mirror at
[.claude/skills](.claude/skills), copied from the local project skill source at
`.agents/skills`.

| Component or asset | Category | Upstream/source identity | License or notice evidence | Project use/distribution |
| --- | --- | --- | --- | --- |
| `.claude/skills/anti-ui-slop` | Agent tooling skill | Local project skill source copied from `.agents/skills/anti-ui-slop` | `.claude/skills/anti-ui-slop/LICENSE`, `.claude/skills/anti-ui-slop/NOTICE`, `.claude/skills/anti-ui-slop/MODIFICATIONS.md`, `.claude/skills/anti-ui-slop/MANIFEST.json` | Mirrored for Claude Code skill access in this repository |
| `.claude/skills/archify` | Agent tooling skill | Local project skill source copied from `.agents/skills/archify` | `.claude/skills/archify/LICENSE`, `.claude/skills/archify/skill-release.json` | Mirrored for Claude Code skill access in this repository |

Other mirrored skills in `.claude/skills` did not expose a top-level
`LICENSE`, `NOTICE`, `COPYING`, `MODIFICATIONS`, `MANIFEST.json`, or
`skill-release.json` file during the bounded Claude workspace sync review.
Their provenance remains tied to the copied `.agents/skills` source until a
deeper skill-origin audit is approved.

Evidence reviewed:

- Repository file inventory excluding ignored `frontend/node_modules/`,
  `data/processed/`, and `data/chromadb/` paths.
- Source-tree search for existing SPDX, copyright, license, and notice text.
- Absence of committed image, dataset, model, and binary artifact candidates in
  the bounded source-tree inventory.
- Claude workspace sync inventory comparing `.agents/skills` and
  `.claude/skills`, plus direct search for mirrored skill license, notice,
  copying, modification, manifest, and release metadata files.

This section is bounded to the Package 7 and Claude workspace sync review
evidence. It is not a future release certification.

## Declared Dependencies

The project declares Python dependencies in [requirements.txt](requirements.txt)
and [backend/requirements.txt](backend/requirements.txt). These files use
version ranges and do not resolve an exact transitive dependency graph, so they
are not sufficient evidence for a complete license inventory.

The frontend declares direct npm dependencies in
[frontend/package.json](frontend/package.json) and has resolved npm metadata in
[frontend/package-lock.json](frontend/package-lock.json). Package 7 inspection
found resolved package license identifiers including `MIT`, `ISC`,
`Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `Python-2.0`, `CC-BY-4.0`, and
`(MIT OR CC0-1.0)`.

These manifests and lockfiles are evidence sources only. They do not replace
release-specific obligation review for the exact artifact being distributed.

## Models, Datasets, and Content

Ignored local paths such as `data/processed/` and `data/chromadb/` are not part
of this source-tree notice inventory. Any future committed or redistributed
model, embedding artifact, vector store, dataset, crawl output, benchmark, or
external travel content requires verified provenance, license terms, and
required attribution before release or distribution.

## External Runtime Services and Content

The application can call external model services and may retrieve or process
external travel content in development workflows. External services and runtime
content are not relicensed by the project simply because the application can
call or retrieve from them.

Production or release use of external services/content requires separately
approved data-flow, privacy, provenance, and operational review.

## Unresolved Provenance

The `.claude/skills` mirror is copied from local project skill material and has
not received a full origin-by-origin legal audit. Release or redistribution
work that includes this mirror must review every mirrored skill's upstream
origin, license terms, generated artifacts, and notice obligations.

Unresolved or conflicting provenance for any future dependency, model, dataset,
content, generated artifact, or bundled asset blocks affected redistribution and
release work until reviewable evidence exists.

## Release-time Review Boundary

Before publishing a release, maintainers must review the exact release artifact,
resolved dependency graph, bundled assets, model/data/content provenance, and
required notices. That release-time review belongs to the later open-source
release-readiness gate and cannot be replaced by this bounded Package 7 file.

## Updating This Inventory

Update this file in the same reviewed change that adds, removes, redistributes,
or changes third-party material with notice or attribution implications. Each
verified entry should identify the component or asset name, category,
upstream/source identity, license identifier or license name, required notice or
attribution, project use/distribution, and evidence location.
