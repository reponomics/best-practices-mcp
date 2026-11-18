# Pre-implementation readiness and review record

Historical initial-implementation record. This preserves planning and review context, including the implementation status at its original checkpoints. Use the [maintained documentation](../../README.md) for current behavior. Detailed execution reports and earlier versions are archived privately; milestone summaries retain substantive findings and outcomes.

Date: 2026-11-09. Scope: review and planning only. **G0 approved:** all three independent reviewers found no unresolved implementation-blocking finding after corrections. Application implementation remains unstarted. This checklist separates completed preparation from tests and deliverables that must be produced during implementation. The [implementation plan](badgeapp-mcp-implementation-plan.md) is the execution sequence; the [contract](badgeapp-mcp-contracts.md) and [upstream baseline](badgeapp-mcp-upstream-baseline.md) close the behavior decisions below.

## Bootstrap assessment

The existing package is an appropriate minimal base: src layout, installed CLI/module entry points, official SDK 2.3.0 over stdio, no dummy tools, Makefile/venv development, real subprocess smoke tests, and an independent SDK client example. No bootstrap code change is required to begin the planned work. The empty tool list and unconsumed storage override are accurately documented.

Observed checks: `make check` passed formatting, lint, dependency consistency, and all three tests; `make example` discovered bestpractices-mcp with MCP 2026-07-28 and no tools. Environment: macOS / Python 3.12.4. `make build` also successfully produced the sdist and wheel; the sdist includes the new planning documents. Local Markdown links and `git diff --check` passed. These establish scaffold functionality and buildability only. They do not establish BadgeApp semantics, an independent host's compatibility, other platforms, or installed catalog packaging. The current example is a discovery demonstration, not the completed reference application.

The originating CLI is Badge Buddy in `../reponomics-plugins`; upstream source is `../best-practices-badge-clone`. These are development references only. Their inspected immutable revisions are recorded in the baseline; installed behavior has no sibling dependency. No existing CLI behavior is a requirement merely because it was previously implemented.

## Findings and dispositions

| ID / severity | Gap found | Resolution and acceptance destination | Preparation status |
| --- | --- | --- | --- |
| P01 / high | Prose tool signatures deferred exact result/error contracts until implementation. | Contract defines all nine success payloads, shared structured errors/text fallback, optional/empty/null inputs, strict types and stable outcomes. G1 translates to schemas and verifies them. | Resolved in plan |
| P02 / high | Identity normalization and mismatch/repair ordering ambiguous. | Contract freezes conservative URL equivalence, refusal of conflicting/unresolved supplied provenance, local id check before patch, honest association labels. G3/G4 fixtures. | Resolved in plan |
| P03 / high | Partial/no-op/unsupported aggregation and script null artifacts ambiguous. | Total outcome classifier and per-field encoding/application dimensions; invalid companion status and '?' are explicitly different. G3 transfer matrix. | Resolved in plan |
| P04 / medium | Unknown existing fields and alias patches had competing interpretations. | Preserve unfamiliar values, reject non-null assignments, allow null removal, normalize each object separately, permit equal duplicates, reject conflicts. G1/G3 fixtures. | Resolved in plan |
| P05 / high | No concrete document/result/network constants or full read-envelope accounting. | Fixed budgets, canonical serialization, complete SDK result measurement, deadlines/retry/cooldown policy, pre-write size checks. G2/G4 boundaries. | Resolved in plan |
| P06 / high | Source pins/catalog extraction/form assumptions lacked a reproducible inventory. | Source pins, exact files, six-level endpoint/control map, provenance/license distinctions and independent oracle matrix. G1/G3 fixtures. | Resolved in plan |
| P07 / medium | URL whitespace and public JSON omission could silently produce wrong predictions. | Upstream Ruby-strip parity and narrowly documented omitted-justification interpretation, separate from document fidelity and validator predicates. G2/G3 fixtures. | Resolved in plan |
| P08 / medium | Reference host remained a UI choice with incomplete observable behavior. | Fixed Python terminal host, command/options/actions, both modes, failure recovery, exact export and scenario checklist. G2–G5 evidence. | Resolved in plan |
| P09 / medium | Package/platform/independent-host acceptance unspecified. | Named Codex desktop target, version capture, minimum Python/platform matrix, isolated wheel/sdist/catalog installation tests. G5. | Resolved in plan; future checks unrun |
| P10 / medium | Repository initially had no project license; reused data/code licenses differ. | MIT / Reponomics selected on November 11, 2026. Preserve upstream notices and verify the final distributions. | License selected; artifact verification remains a publication gate |
| P11 / medium | Stricter URL identity rules could incorrectly filter upstream search results. | Preserve upstream candidates and distinguish url_query match basis from confirmed field equality. Generation identity remains conservative. G2 fixture. | Resolved in plan |
| P12 / medium | Script report could overclaim catching page event-listener exceptions. | Catch direct assignment/dispatch failures, report completed fields, document browser-reported listener exceptions and absence of rollback/save guarantee. G3 fixture. | Resolved in plan |

These resolutions add precision and common infrastructure, not new MCP capabilities. Rejected scope additions remain rejected: selectors/batching, revision tokens/cross-process coordination, completeness gates, filtered reads, browser execution, authenticated saving, registration, registries and sync, advisory/model workflows, arbitrary origin settings, and general chat/web products.

## G0 actionable preparation checklist

- [x] Inventory tracked bootstrap code, tests, package metadata and design documents; preserve existing working state.
- [x] Run existing scaffold verification in the project's venv and record its limits.
- [x] Confirm authoritative scope and the exact nine planned tools.
- [x] Define typed contract shapes, stable errors, explicit/null/omitted behavior, and representative cases.
- [x] Close identity, patch normalization, transfer classification, and script failure ambiguities.
- [x] Choose server resource budgets and finite HTTP behavior without imposing upstream completeness/import limits.
- [x] Identify upstream and originating CLI revisions; inspect relevant docs/code locally and record discrepancies without enforcing plugin parity.
- [x] Specify reproducible catalog inputs, level/field/control map, attribution, and independent compatibility fixtures.
- [x] Fix the reference host's implementation form and protocol-only boundary; specify both document and stored workflows.
- [x] Define milestones, dependencies, owner roles, primary gates, failure policy, platform/package and independent-host acceptance.
- [x] Separate approval to implement, actual implementation acceptance, and publication/licensing authorization.
- [x] Obtain renewed independent review of the completed planning documents and resolve all blocking findings.
- [x] Record G0 decision for planning revision G0-2026-11-09 and commit the preparation artifacts. Git history identifies the exact document revision.

## Independent review record

Three subagents reviewed independently, without feature edits:

| Reviewer | Initial remit | Initial verdict | Final review |
| --- | --- | --- | --- |
| contract_review | Spec, previous decisions, nine-tool semantics, host/server boundary | Core scope sound; concrete contract gaps P01–P05 needed closure. | **APPROVE G0**, 2026-11-09: initial findings closed; no blocking contract or scope ambiguity. |
| bootstrap_review | Package, tests, SDK baseline, milestone/reference-host acceptance | Bootstrap checks pass; P05/P06/P08–P10 require concrete planning gates. | **APPROVE G0**, 2026-11-09: bootstrap, architecture, limits, host and acceptance gates ready. |
| upstream_review | Pinned upstream docs/code/catalog/forms and originating CLI | Scope agrees with upstream; P07/P11/P12 and schema consistency required corrections. The local clone is behavior-equivalent for relevant sources. | **APPROVE G0**, 2026-11-09: corrected provenance, discovery, metadata, omission and script-report semantics verified. |

Approval means reviewers find no unresolved blocking design ambiguity in this bounded implementation plan. It is not user acceptance of unbuilt behavior, an assurance that future tests pass, or authorization to publish. Reviewer findings that expose an actual implementation defect later must still be fixed; this record does not waive gates.

## Implementation handoff

G0 is approved; the next authorized implementation task can start M1. The first change should implement typed contracts and reproducible catalog packaging, with schema/source fixtures, rather than adding a new workflow capability. Read the spec, contract, upstream baseline and milestone plan together. Keep each gate's tests and evidence with its implementation change. All M1–M6 boxes and runtime acceptance cases remain outstanding until executed; do not convert this planning checklist into a claim that the MCP itself is finished.

## MCP revision confirmation follow-up

On 2026-11-09, the official latest specification resolved to MCP 2026-07-28. A focused review corrected two planning details: advertised output schemas must include both structured success and domain-error payloads, and SDK CacheHint uses scope rather than cache_scope as its constructor argument. The contract reviewer independently confirmed both corrections and retained G0 approval. The architecture now contains the version-specific wire-conformance checklist required at G1.

A direct stdio probe of the existing scaffold, without an initialize handshake, successfully called server/discover and tools/list. Both returned resultType=complete and the required caching fields; tools/list remained empty. An unsupported protocol version returned error -32022. Stdout contained protocol JSON and stderr was empty. This confirms those scaffold behaviors; feature-result schemas and independent-host conformance remain implementation acceptance work.

## Subsequent implementation

[Milestone records](README.md#milestone-records) summarize implementation, substantive review findings, fixes and qualification. The current behavior is documented separately in the [maintained documentation](../../README.md).
