# Independent reviews of the Best Practices MCP proposal

Historical initial-implementation record. This preserves planning and review context, including the implementation status at its original checkpoints. Use the [maintained documentation](../../README.md) for current behavior. Detailed execution reports and earlier versions are archived privately; milestone summaries retain substantive findings and outcomes.

Review date: 2026-11-06. Three independent agent reviews covered scope/usability, BadgeApp compatibility, and MCP/storage contracts. This is a review of the design, not a test of an implemented server.

Reviewed artifact: [server specification](badgeapp-mcp-spec.md), SHA-256 `4ed8e9ef9ff02743d9c1b6e53355cdc3125facd175c99e587dc9cc81c9b2cd98`. Line references below refer to that version. Upstream compatibility was checked against BadgeApp revision `100a704da6f6aea7572da16d6f45171f29acb7f5`. No production writes were performed. The specification remains unchanged by this review round.

Subsequent design decision, 2026-11-06: the single configured draft file was replaced in the design by a default/overridden data directory containing `projects/<project_id>/.bestpractices.json`. The host must resolve an existing registered project before application work. The current spec and implementation plan incorporate that decision; the historical line references and single-file descriptions below refer to the reviewed version. Transfer findings remain open, and storage findings apply independently to each project file. This amendment does not claim a second independent review.

## Overall assessment

All three reviewers support the architectural boundary: public reads, document-to-artifact operations, and an optional single configured draft file. None recommends a registry, assessment handles, automatic synchronization, additional tool families, or direct website saving.

The proposal needs targeted corrections before the transfer contract is implemented. The highest-priority finding is a factual error about justification-only URLs. Several other findings are missing contracts or product choices rather than architectural defects.

## Findings to resolve

### R1. Remove the status carrier for justification-only URLs

Priority: high; factual compatibility correction. Spec line 160, with related rules at 162.

The spec allows a generator to borrow the saved status to carry a justification and rejects such proposals if the saved status is unknown. Upstream accepts a justification parameter independently. Its controller uses the current project status when none is supplied, and its tests cover both filling a blank justification and replacing existing wording without a status parameter. [Controller](https://github.com/ossf/best-practices-badge/blob/100a704da6f6aea7572da16d6f45171f29acb7f5/app/controllers/projects_controller.rb#L1827), [tests](https://github.com/ossf/best-practices-badge/blob/100a704da6f6aea7572da16d6f45171f29acb7f5/test/controllers/projects_controller_test.rb#L3601)

Adding a carrier is unnecessary and can propose an unintended status change if the application changes between generation and opening the URL. This restriction came from the existing helper's behavior, not BadgeApp's requirements.

Recommended resolution: emit only the requested justification, with an exact justification override when needed. Remove `status_required_for_proposal` and borrowed-carrier rules. Test known and unknown saved statuses. Known-status cases have explicit upstream tests; support with unknown status follows from controller inspection and should receive a dedicated compatibility test.

### R2. Treat incomplete answers separately from invalid transfers

Priority: medium; product decision before implementation. Spec lines 75 and 152.

The spec permits incomplete drafts but blocks artifact generation for a criterion lacking required explanation or evidence. That prevents users from moving partial work into the BadgeApp form and completing it there. BadgeApp distinguishes field validity from whether an answer earns criterion credit; the latter is evaluated separately. [Criterion evaluation](https://github.com/ossf/best-practices-badge/blob/100a704da6f6aea7572da16d6f45171f29acb7f5/app/models/project.rb#L1829)

Recommended resolution: incomplete evidence should produce diagnostics rather than a transfer veto. Block malformed fields and values the chosen mechanism cannot represent. Determine `N/A` behavior from the particular upstream mechanism rather than grouping all criterion-credit failures together. Choose one default; no extra “allow incomplete” option is needed.

### R3. Define concrete result variants and content compatibility

Priority: medium; shared host/server contract gap. Spec lines 89–100, 138, 154, 166, and 178.

The prose promises typed output but leaves essential variants unspecified. In particular, an empty artifact list may mean that all answers already match, or that every requested change was omitted. Calling both “no change” hides unfinished work. Missing-file errors must carry the initialization revision, and identity mismatch, unresolved identity, and an unbound document need distinct outcomes.

Recommended resolution: add representative JSON or schema definitions for normal, partial, empty, and error results. Distinguish no differences, complete transfer, partial transfer, and no transferable changes. Define error placement and `isError` behavior. Specify a serialized text-content fallback for structured results, or explicitly require and test structured-content-capable hosts; brief text summaries alone may omit the draft or artifact a host needs. [MCP structured results](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#structured-content)

### R4. Add actual field constraints to transfer eligibility

Priority: medium; upstream compatibility gap. Spec lines 71, 152, and 174.

The inspected upstream limits justifications and descriptions to 8,192 characters; name, license, and implementation languages to 254 characters; and validates implementation-language formatting. Scripts avoid URL-length limits but do not bypass these field constraints. [Project constants](https://github.com/ossf/best-practices-badge/blob/100a704da6f6aea7572da16d6f45171f29acb7f5/app/models/project.rb#L65), [validators](https://github.com/ossf/best-practices-badge/blob/100a704da6f6aea7572da16d6f45171f29acb7f5/app/models/project.rb#L369)

Recommended resolution: include field constraints in the versioned compatibility model and transfer report. Preserve draft text where practical, but report values that cannot be accepted by the target mechanism. Never silently truncate evidence or offer a script as a remedy for an upstream field-size violation.

### R5. Make repository-import compatibility findings explicit

Priority: medium; available facts should replace a deferred decision. Spec lines 120 and 231.

The inspected importer reads `.bestpractices.json` or `.project.d/bestpractices.json`, has a 100,000-byte limit, and processes status and justification fields. It does not import the four editable project metadata fields. It also accepts standalone justifications, including a justification alongside an ignored unknown status. [Importer](https://github.com/ossf/best-practices-badge/blob/100a704da6f6aea7572da16d6f45171f29acb7f5/app/lib/repo_json_detective.rb#L49)

Recommended resolution: require these distinctions in JSON compatibility findings. Preserve the portable document, but identify metadata/provenance ignored by import, unknown statuses, and size failures. Test the exact size boundary and encoding against the pinned importer. This does not require a new tool.

### R6. Allow selective proposals without retransmitting a stored draft

Priority: medium; workflow decision. Spec lines 99–100 and 148.

A file may contain ten pending answers at one level while the user wants to propose only two. The generators currently select the entire level. The workaround is to read the full document, construct a subset, and pass it back, which recreates the transport burden the file interface was intended to remove.

Recommended resolution: consider a shared optional selector for the two generators, with explicit criterion and metadata semantics. If deferred, document the whole-level behavior plainly. Validate the choice with a realistically sized draft in the example host; do not add a separate staging store.

### R7. A successful write must leave a readable draft

Priority: medium; storage invariant. Spec lines 116–118, 142, and 184.

Independent file-size and response-size limits could allow a saved document that `read_draft` cannot return, particularly after result envelopes, diagnostics, and compatibility content are included.

Recommended resolution: check supported size before replacement and guarantee that every document accepted by `update_draft` can be returned by `read_draft`. Choose bounded diagnostics and compatible payload limits without silently truncating the document. These can remain implementation constants.

### R8. Make the interprocess locking promise portable or explicitly bounded

Priority: medium; release gate for file-backed operation. Spec lines 140–144 and 214.

The existing storage primitive skips `fcntl` locking where it is unavailable and falls back to thread locking. Reusing that behavior would violate the spec's unconditional promise to serialize cooperating processes. Atomic replacement does not itself prevent lost updates between two readers of the same revision. Badge Buddy source reference: `plugins/badge-buddy/scripts/ossf_review/storage.py` in the separate `ossf-best-practices-plugin` repository.

Recommended resolution: use a supported portable locking implementation or state supported platforms and reject unsupported file-backed writes. Do not silently weaken the guarantee. The document-only mode need not inherit this storage limitation.

## Optional refinements

- **Filtered reads:** allow `read_draft` to return selected answers while retaining the revision of the complete file, or first demonstrate that full-document reads remain usable during restart and conflict recovery. Small patch writes alone do not establish a low-context resume workflow. Spec lines 118 and 140.
- **Caching terminology:** distinguish internal catalog reuse from protocol caching. MCP cache hints cover discovery/list/resource operations, not `tools/call` results. No resource interface needs to be added just for caching. Spec line 180; [cacheable results](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching#cacheable-results).

## Implementation-plan addition

A reference/example host is an implementation deliverable, separate from the MCP server. This is recorded in the [implementation plan](badgeapp-mcp-implementation-plan.md).

The host should use the actual MCP client protocol, exercise both document-only and configured-file workflows, display changes and omissions, and hand off artifacts. Include restart, conflicts, a large draft, and partial transfer. It should prove that the server is usable independently of Badge Buddy without becoming another advisory assistant, storage framework, or website automation service.

## Recommended next revision

See the [proposed response](badgeapp-mcp-review-response.md) for a concrete disposition of each finding and the [transfer reference](badgeapp-mcp-transfer-rules.md) for upstream guidance and MCP-specific recommendations.

Correct R1 and encode the upstream constraints in R4–R5. Resolve the incomplete-answer policy and result shapes in R2–R3. Decide selective generation in R6 using the example-host workflow. Add the storage guarantees in R7–R8 to implementation acceptance. Keep the eight-tool architecture and single-file boundary; none of the reviews justifies broader server scope.
