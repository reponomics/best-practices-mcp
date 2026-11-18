# Decisions from the MCP design reviews

Historical initial-implementation record. This preserves planning and review context, including the implementation status at its original checkpoints. Use the [maintained documentation](../../README.md) for current behavior. Detailed execution reports and earlier versions are archived privately; milestone summaries retain substantive findings and outcomes.

Consolidated 2026-11-09. Decisions from the incremental discussion of [R1–R8 and optional findings](badgeapp-mcp-review.md), incorporated into the server specification. The validator's scope is mechanical criterion checks; no server implementation has been added by these documentation changes.

## Incremental decisions

- **Finding 1, agreed and incorporated:** justification-only proposals need no status carrier. Filling blank wording needs no override; replacing or clearing existing wording does. A blocked status change blocks its accompanying justification even when that justification is forced. The generator must make those distinctions explicit.
- **Finding 2, principle agreed and incorporated:** do not fail or omit an edit for a criterion-completeness condition that BadgeApp's UI accepts. Missing required explanation/evidence can prevent credit without invalidating an edit. Completeness checks must not become a stricter submission policy.
- **Finding 2, narrow validator included:** add `validate_draft(project_id, level, draft?)` for mechanical checks against the level's criterion flags. Check required explanation and URL presence without fetching URLs, reading the live application, or assessing evidence. Findings are data and never gate generation.
- **Draft/validation scope, confirmed:** one draft per project; validation evaluates requirements for the requested level, including shared criterion IDs whose requirements differ across levels.
- **Finding 3, empty-result principle agreed and incorporated:** generators must explain whether nothing needs changing, no transferable answers were supplied, or requested work could not be represented.
- **Finding 3, URL output agreed and incorporated:** return one exact URL as structured data together with its UTF-8 byte length after encoding. No guessed URL-length limit, automatic splitting, or URL-delivery retry interface in v1. No generated URL is represented by `artifact: null` with an explicit reason. Display/copy/open behavior and handling delivery failures belong to the host; the reported copy failure does not establish a size problem.
- **Findings 4–5, documentation-only:** do not add field-limit or repository-import advice to tool results, and do not enforce those implementation-derived constraints in generators. Return the requested artifact/document; BadgeApp handles its own acceptance when used. Preserve document fields rather than filtering them based on predicted import behavior. Background facts can stay in documentation. These findings do not expand the mechanical validator's scope.
- **Finding 6, no server change; agreed:** do not add field selectors to generators. Updating answers as work proceeds is the normal host workflow. For exceptional selective transfer, the host may read the draft, construct a subset, and pass that explicit document; this is an acceptable burden. No staging mechanism is needed.
- **Finding 7, agreed and incorporated:** a successful draft write must remain readable under the server's response policy. Check before writing; failure leaves the file unchanged.
- **Finding 8, agreed after focused review:** [the independent recommendation](badgeapp-mcp-concurrency-review.md) is incorporated into the spec, retaining the internal guard. Remove draft revision tokens/checks and cross-process lock files. Use one internal per-project in-memory guard around read/patch/validate/atomic replacement so one server preserves disjoint patches. No prior read, client sequencing, or arrival-order guarantee. Independent processes/editors must not write the same project file simultaneously; that coordination is outside v1.
- **Finding 9, withdrawn:** retain full-document reads. The documents have not been shown to need filtering, and a host receiving a document does not necessarily put it into model context. The earlier context-cost argument assumed a host implementation unnecessarily.
- **Finding 10, agreed and incorporated:** distinguish protocol discovery/list/resource caching from internal catalog reuse; do not add a resource interface for caching.
- **Review status:** discussion of findings 1–10 is complete. The specification includes the narrow, non-blocking mechanical validator. Detailed result examples and implementation constants can be completed without reopening the resolved product boundaries.

## Finding 2: mechanical validation interface

Include `validate_draft(project_id, level, draft?)`, using the same explicit-document-or-project-file rule as generators. It is read-only and never a prerequisite for artifact generation. It checks supplied answers for the requested level and reports scope explicitly; it does not claim to certify the entire badge application.

The validator checks recognized field types/status values, allowed `N/A`, required justifications, and required URL presence using the selected level's catalog flags. Findings identify the criterion, field, and rule. It does not assess whether linked material supports the claim and does not resolve or fetch links. Previously proposed live-application merging is removed: the validator checks the supplied/stored document only. Missing/unknown statuses cause conditional checks to be reported as skipped, not guessed; absent criteria are outside scope. Report draft source and catalog revision. Read/source failures are operational errors, while completed checks with findings are normal results.

For example, `Met` with an explanation that lacks a required URL can produce a `missing_required_url` finding. The host can show that finding, revise the explanation, or proceed to artifact generation unchanged. No “force”, “ignore validation”, approval token, or validation-success prerequisite is needed. Passing checks means only that the implemented mechanical checks found no issue, not that the response is correct in substance.

The rationale for a separate tool is that a host can run these inexpensive mechanical checks before requesting a URL or script. Reuse existing criterion flags and presence-check helpers; do not add a rules engine, model calls, network checks, or an advisory layer. Generation remains independent of the validator's findings.

## Agreed dispositions

| Finding                         | Response                   | Concrete revision                                                                                                                                                                                                                                                                                                    |
| ------------------------------- | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1: justification-only URLs     | Accept; factual correction | Emit only supplied justification. Remove status carriers and `status_required_for_proposal`. Evaluate justification independently when status is omitted or `?`. Follow the upstream decision matrix linked in the [transfer reference](badgeapp-mcp-transfer-rules.md).                                             |
| R2: blocking incomplete answers | Accept                     | Missing required evidence or explanation is reported only by optional `validate_draft`, never as a generation gate. Malformed values and unsupported `N/A` remain invalid for transfer. This does not require mirroring upstream model validators or adding field-length/import gates. No “allow incomplete” switch. |
| R3: concrete result variants    | Accept                     | Define typed payloads and examples before server/host implementation. Distinguish `no_changes`, `complete`, `partial`, and `no_transferable_changes`; distinguish encoded fields from expected application to the form. Define error results and content fallback.                                                   |
| R4: field constraints           | Documentation only; agreed | No field-limit gate or advisory report in generators. BadgeApp performs its own save validation. Implementation-derived limits may be recorded as background documentation.                                                                                                                                          |
| R5: JSON import findings        | Documentation only; agreed | No import-effectiveness report or upstream import-size gate in document tools. Preserve the flat document. Document importer behavior and placement separately if useful.                                                                                                                                            |
| R6: selective generation        | No server change; agreed   | No generator selectors. The host can construct and pass an explicit subset document when needed. The ordinary workflow updates answers as work proceeds.                                                                                                                                                             |
| R7: writable implies readable   | Agreed and incorporated    | Check resulting size before committing. Every server-written draft must be readable under the server's response policy. Reject an oversized write without changing the file.                                                                                                                                         |
| R8: portable locking            | Resolved by focused review | No draft revisions or cross-process locks. One process-local guard per project protects the complete patch/write operation; atomic replacement protects file integrity. Independent writers are not coordinated.                                                                                                     |

The distinction in R2 is grounded in upstream model validation versus criterion-credit evaluation: unsupported `N/A` is rejected by the model, while missing criterion evidence can prevent credit without being an invalid field update. [Status validation](https://github.com/ossf/best-practices-badge/blob/100a704da6f6aea7572da16d6f45171f29acb7f5/app/models/project.rb#L423), [criterion evaluation](https://github.com/ossf/best-practices-badge/blob/100a704da6f6aea7572da16d6f45171f29acb7f5/app/models/project.rb#L1829)

## Result semantics

Use two distinct dimensions rather than one misleading success flag:

- **Artifact completeness:** `no_changes` when supplied meaningful values already match, `no_supplied_transferable_answers` when the input contains no transferable answers, `complete` when all requested changes can be encoded, `partial` when some cannot, and `no_transferable_changes` when requested work exists but none can be encoded. Unknown/unsupported-only input must have an explicit reason rather than masquerading as matching saved answers.
- **Expected application:** report per-field whether a URL is expected to fill, replace, remain divergent, or be skipped under upstream rules. A completely encoded unforced proposal can still leave existing answers unchanged. These are predictions from the fetched observation, not proof of application or saving.

Provide examples for document reads, missing drafts, successful writes, validation/write failures, partial artifacts, and identity errors. There are no draft revision or conflict results. Keep SDK protocol envelopes separate from domain schemas. Include serialized structured results in text content for compatibility where hosts do not expose `structuredContent`, and account for that representation in size limits.

## Explicit subsets and overrides

There is no generator selector parameter. A host requiring selective transfer constructs an explicit document containing the intended fields. Supplying a justification alone is valid; supplying both fields preserves their upstream coupling. Exact override requests must remain within supplied, in-scope fields. Compute effective override scope before pruning unchanged fields, so pruning cannot silently change the user's requested replacement behavior.

Example: a stored draft has ten changed criteria, but the user wants to transfer only the contribution answer. The host reads the draft and passes `draft={"contribution_status": "Met", "contribution_justification": "..."}` to the generator. The stored draft is untouched.

## Optional findings

**Filtered draft reads (finding 9):** withdrawn. Keep `read_draft(project_id)` returning the complete document. Full host input is not inherently full model-context input; no demonstrated document-size issue justifies this additional interface. This also aligns with finding 6's accepted host-side subsetting workflow.

**Caching terminology (finding 10):** agreed and incorporated. Discovery/list/resource caching and application catalog reuse are different. This tool-only v1 does not gain protocol tool-result caching simply by shipping a catalog, and needs no new resources for that purpose.

## Implementation consequence

The current specification contains nine tools, including the narrow mechanical validator. The [example host](badgeapp-mcp-implementation-plan.md) should demonstrate that incomplete answers can be transferred and that running validation is optional. Selective transfer uses an explicit host-prepared document, not an additional server selection feature.
