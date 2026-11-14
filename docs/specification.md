# Server specification

The server exposes eleven tools for public BadgeApp reads, portable documents, optional local drafts, advisory validation, and reviewable update artifacts. The [implementation contracts](contracts.md) define exact payloads, errors and limits; [design decisions](design.md) explain the boundaries; [upstream compatibility](upstream-compatibility.md) identifies the source baseline and [transfer rules](transfer-rules.md) describe proposal semantics.

## 1. Purpose and boundary

The server makes BadgeApp's criteria, public application data, and update mechanisms available to MCP hosts. It prepares changes that a host or user can apply through BadgeApp and provides local draft storage keyed by BadgeApp project ID. Hosts can instead supply documents explicitly.

The server owns field interpretation, structural validation, artifact construction, and configured draft-file operations. The host owns advisory reasoning, evidence gathering, choosing answers, browser interaction, executing generated scripts, publishing repository files, and saving forms. The server does not decide whether claims are true or award a badge.

V1 provides:

- Criteria lookup for every supported badge level.
- Project discovery and public application progress, independent of a local checkout or repository hosting provider.
- Compact badge-family status observations and SVG artifacts with dynamic README embed snippets.
- Proposal URLs and browser form-fill scripts for a project and level.
- Creation and modification of portable `.bestpractices.json` documents.
- Mechanical validation of supplied draft answers against the selected level's criterion flags, without fetching evidence or gating artifact generation.
- Persistence of one draft per registered project under a default or environment-configured data directory.

Before beginning application work, the host must resolve an existing BadgeApp `project_id`. If no project entry exists, the user must register it in BadgeApp and the host must then resolve its ID before starting the draft/form workflow. Registration remains outside this server. General criteria lookup and project discovery are available before this step; anonymous application drafts and temporary project IDs are outside v1.

Authenticated REST changes, project creation, browser control, hosted transport, project registries, automatic synchronization, background watchers, and advisory prompts are outside v1. Direct REST saving is deliberately excluded, not a deferred implementation commitment: upstream documents REST writes but no longer encourages them for changes because they require authentication and bypass review in the BadgeApp UI. The MCP prepares changes for human review and leaves the final save to the human in BadgeApp. Any future direct-save tool requires a separately approved scope and design change. See the maintained [design rationale](design.md#prepare-changes-leave-the-final-save-to-the-human) and upstream [automation proposals](https://github.com/ossf/best-practices-badge/blob/868e1677339a3fdb48851b0c2ae8862c553115eb/docs/automation-proposals.md).

## 2. Runtime and configuration

Use Python 3.11 or newer, the official MCP Python SDK v2, and local stdio transport. Target MCP **2026-07-28**. Use SDK protocol implementations rather than reproducing discovery, metadata, or result envelopes. See the [Python SDK](https://github.com/modelcontextprotocol/python-sdk) and [MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools).

The server uses the platform's conventional per-user application-data directory for `bestpractices-mcp` by default. The only user-facing storage override in v1 is:

```text
BESTPRACTICES_DATA_DIR=/absolute/path/to/bestpractices-mcp
```

Host configuration after installing the executable:

```json
{
  "mcpServers": {
    "bestpractices": {
      "command": "bestpractices-mcp",
      "env": {
        "BESTPRACTICES_DATA_DIR": "/home/user/badge-drafts"
      }
    }
  }
}
```

The directory belongs to the server's filesystem. An override must be an absolute path; do not search the current directory or infer a Git repository. An unset variable selects the default data directory. Resolving the storage root does not create it. File and directory creation occurs only during an explicit draft update; document-only workflows do not touch storage. Invalid directory configuration is reported at startup; file-content and permission errors are reported when storage is accessed.

Paths are derived directly from the canonical decimal project ID:

```text
<data directory>/
  projects/
    123/
      .bestpractices.json
    456/
      .bestpractices.json
```

The storage key is the production BadgeApp `project_id`, not a repository URL, local directory, project name, or badge level. Each project has one multi-level draft. No registry or separate mapping database is required.

Public network requests target the production BadgeApp service. Tests inject a transport; v1 does not need a user-configurable arbitrary API origin. Diagnostics go to stderr, never into the stdio protocol stream. Development uses `venv`, pip, and a Makefile with toolchain variables and annotated help targets.

## 3. Data model

### Criteria catalog

The packaged catalog is generated from an identified upstream revision with provenance and license notices. It is served offline, without scraping the live site or downloading a catalog on each request. The installed server has no dependency on a plugin or sibling source checkout.

Initial levels are `passing`, `silver`, `gold`, `baseline-1`, `baseline-2`, and `baseline-3`. Use `level` consistently in the MCP API; map it to BadgeApp's `section` terminology internally. Criterion lookup is level-qualified because wording and requirements can differ across levels. Include the catalog revision in criteria, validation, and artifact results; do not describe a packaged catalog as necessarily current with the live site.

### Draft document

The document is a flat `.bestpractices.json` object, not an MCP-specific envelope:

```json
{
  "name": "Example project",
  "description_good_status": "Met",
  "description_good_justification": "https://example.org/project describes the project.",
  "floss_license_status": "?"
}
```

Criterion fields use `<criterion_id>_status` and `<criterion_id>_justification`. Canonical statuses are `Met`, `Unmet`, `N/A`, and `?`. The writable project metadata fields are `name`, `description`, `license`, and `implementation_languages`. Justifications and metadata are strings, including deliberately empty strings. Normalize supported Baseline display aliases to canonical field names; reject conflicting aliases rather than choosing one value.

A draft can contain answers for multiple levels. The same canonical field has one value even if its criterion appears in multiple levels; this format cannot represent conflicting answers for that field by level. Preserve unrelated existing fields through transformations, including unfamiliar fields from imported public records, and report fields the server cannot interpret. Reject newly introduced unknown fields in patches to catch misspellings.

Incomplete answers are allowed in storage. Invalid types and status values are errors; absent required explanations, unsupported `N/A`, and missing evidence URLs are reported as level-qualified validation issues. Transfer eligibility is evaluated separately. Validation never establishes the truth of a claim.

### Project identity

Every project-specific public read, stored-draft operation, and generator requires an explicit positive integer `project_id`. The host first resolves and verifies the registered project through `find_project` or `get_project_progress`, then passes the same ID throughout that application's workflow. A remembered numeric ID must be verified before beginning work in a new workflow. Local draft operations remain local: they validate the ID's representation but do not add a network lookup on every edit or require a server-side registration session. The host is responsible for satisfying the registration precondition.

For stored drafts, the project directory provides the association. No identity envelope is added to the flat document. Explicit documents use the supplied `project_id` as the target; they do not inherit an association from any stored file. `build_draft` remains a pure transformation without an ID argument, but the host's registration prerequisite still applies to application work using it.

If a draft contains the public record's `id`, compare it with the requested project and reject a mismatch, including during stored-draft reads and updates. During generation, if it contains `repo_url`, compare it with the fetched project's repository URL using conservative URL normalization; report an unresolved or conflicting association rather than guessing. These fields are provenance, not editable answer fields, and are never encoded into proposal URLs or scripts. Report whether the association comes from the storage project key, document provenance, or the caller's explicit target. Storage association does not establish the truth or origin of the answers. A project name alone is not identity evidence.

### Saved application data

Live responses are observations, with `project_id`, source URL, and `fetched_at`. They are not merged into a draft automatically and are not persisted as a separate snapshot. Distinguish upstream-reported percentages from any locally derived counts. A missing upstream field remains missing rather than becoming `?` silently.

## 4. Tool surface

The signatures below describe domain inputs and outputs, not raw MCP wire envelopes. All tools have typed input and output schemas. `?` after an argument denotes optionality.

| Tool                    | Inputs                                                | Result and effects                                                                                                                                                     |
| ----------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `get_criteria`          | `level?`, `criterion_ids?`                            | Supported-level index when no level is supplied; otherwise selected definitions, requirements, canonical fields, and catalog provenance. Local catalog read.           |
| `find_project`          | `query`, `page=1`                                     | Candidate IDs, names, repository/homepage URLs, match basis, and pagination. Public network read.                                                                      |
| `get_project_progress`  | `project_id`, `level?`, `criterion_ids?`              | Saved answers and explanations, summaries, public metadata, and observation provenance. Public network read.                                                           |
| `get_project_badge_status` | `project_id`, `family="best_practices"` | Compact badge-family state/progress, project-record update time and observation metadata. One public JSON read. |
| `get_project_badge_svg` | `project_id`, `family` | SVG text artifact, dynamic image URL, project-page link and Markdown snippet. One public SVG read; no repository edit. |
| `build_draft`           | `draft`, `changes={}`                                 | Updated document, structural validation issues, and serialized byte count. Pure transformation. Use `{}` to create a document.                                         |
| `read_draft`            | `project_id`                                          | Complete project document, location, and structural validation issues. Local read.                                                                                     |
| `update_draft`          | `project_id`, `changes`                               | Applied patch, whether a draft was created, structural validation issues, and location. Writes only that project's draft.                                              |
| `validate_draft`        | `project_id`, `level`, `draft?`                       | Structured findings from mechanical criterion checks, with checked/skipped scope and catalog provenance. Local catalog/document read; no network or writes.            |
| `prepare_update_url`    | `project_id`, `level`, `draft?`, `override_fields=[]` | One exact proposal URL with encoded byte length, or no artifact with an explicit reason, plus a field-level transfer report. Public network read; optional local read. |
| `prepare_update_script` | `project_id`, `level`, `draft?`                       | JavaScript artifact and a field-level transfer report. Public network read; optional local read.                                                                       |

The tool list does not depend on which projects have local files. Separate resource templates and draft-listing tools are not needed for initial completeness; hosts select projects through BadgeApp lookup rather than through local draft discovery.

### Lookup details

`get_criteria` returns official wording, details, requirement category, applicability/justification flags, and source references where available. A criterion filter requires a level. Unknown levels or criterion IDs return actionable errors. Requesting a level without a criterion filter returns its complete definitions.

`find_project` treats an HTTP(S) URL as an exact repository/homepage URL query, a positive numeric identifier as an ID lookup, and other text as a textual search. Return candidates rather than selecting the first match. URL queries do not fetch the supplied URL itself. Do not restrict discovery to GitHub or claim that arbitrary URL spellings are equivalent. Preserve upstream pagination; return `next_page` when known and explicitly mark uncertainty instead of inventing a total or completeness claim. Zero matches is a normal empty result. The [BadgeApp API](https://github.com/ossf/best-practices-badge/blob/main/docs/api.md) documents `.json` resources, exact URL queries, textual search, and paginated results.

`get_project_progress` without a level returns available level summaries and project metadata. With a level, it returns saved criterion status/justification pairs and a flat `answers` object suitable for document operations; an optional criterion filter narrows those answers and requires a level. Include project identity separately so hosts need not parse prose. Read-only operations never initialize or modify a draft.

### Badge status and image retrieval

Both badge tools accept `family` as `best_practices` or `baseline`. `get_project_badge_status` defaults an omitted family to `best_practices` and returns the effective family; `get_project_badge_svg` requires a family. Each retrieves one representation from one allowlisted endpoint with no full-record lookup or automatic call to the other tool. [ADR 0001](adr/0001-badge-image-and-status-tools.md) records the action boundaries and reviewed discovery descriptions.

`get_project_badge_status` returns compact project identity, the raw upstream badge value, a recognized/unknown state, the family-specific progress measure and the upstream project-record update time. Best Practices reports tiered progress; Baseline reports level-1 completion, even if a higher badge is earned. Missing values remain unknown and unrecognized badge strings remain visible. The result explicitly distinguishes a valid, missing or malformed timestamp string from the MCP fetch time. Badge endpoints do not supply project-entry attribution/license, so the observation identifies service credit separately and leaves those record fields null.

`get_project_badge_svg` returns the original decoded SVG text as a bounded artifact with media type and UTF-8 byte count, together with the dynamic image URL, project-page URL and Markdown embed snippet. The server validates the content type, UTF-8 encoding and SVG XML root, rejects DTD/entity declarations, and neither renders nor sanitizes the image. The artifact is data in the structured response and JSON text fallback. The host decides whether to insert the snippet or save the SVG; downloaded SVG is a snapshot, while a dynamic URL can follow later badge changes. Neither badge tool touches drafts or repository files.

Use `get_project_progress` for all-six-level percentages, individual-level progress such as silver or Baseline level 2/3, and saved criterion answers. `updated_at` can prompt a later readback but cannot establish acceptance of proposed fields. Public responses may be cached; timestamp changes do not identify which fields changed, and unchanged timestamps do not prove a save failed. The host can compare relevant observed saved answers with proposed values directly, without waiting for a changed badge timestamp or automatically retrying a save.

### Document mutation details

`build_draft` and `update_draft` share one patch implementation. Each non-null `changes` value sets a writable field; a JSON `null` removes an existing field locally, including unfamiliar or provenance fields. Removing a field does not request deletion from BadgeApp. Reject a patch containing an unknown new field, conflicting alias, or invalid type/value as a whole. Preserve all other fields. Reapplying the same patch is a content no-op, including removal of an already absent field.

For a structurally readable document, apply the patch in memory before validating the resulting recognized fields. This allows a patch to repair an invalid stored value. `read_draft` returns readable documents with diagnostics for invalid recognized values; malformed JSON, non-object roots, and conflicting aliases are read errors. A mutation commits only when the resulting recognized field types and status values are valid. Incomplete answers are stored without criterion-completeness diagnostics. Hosts can request those separately through `validate_draft` with a level.

Return the full resulting document from `build_draft`, because its caller owns persistence. Return the applied patch, `created` boolean, and location from `update_draft`, without echoing the whole document; callers can request `read_draft` when needed. No prior read is required for an update. `read_draft` returns the full document and never truncates it silently. Draft tools do not accept or return revision tokens or content hashes.

The document returned by `build_draft` can be serialized by the host as `.bestpractices.json`. Preserve the document according to the patch contract; do not remove fields merely because the repository importer may ignore them. The tool does not assess or explain expected import effectiveness, enforce upstream repository-file limits, or add advisory import findings. The host chooses the destination and whether to publish it. File placement, import behavior, and upstream limits belong in documentation, including [upstream repository JSON guidance](https://github.com/ossf/best-practices-badge/blob/main/docs/bestpractices-json.md).

### Mechanical validation

`validate_draft(project_id, level, draft?)` uses the explicit document when supplied, otherwise that project's stored draft. It reads the packaged catalog and checks only supplied criterion answers relevant to the requested level. It makes no BadgeApp request, resolves no evidence URLs, writes no files, and invokes no model. The host's existing project-resolution prerequisite still applies.

For each supplied answer, apply the selected level's flags. Published catalog booleans include upstream's implicit requirements: `met_url_required` entails `met_justification_required`, and `na_justification_required` entails `na_allowed`. An omitted entailed YAML key does not indicate absence of that requirement; generation makes it explicit without changing the vendored source.

- Check recognized field types and status values.
- For `N/A`, check `na_allowed`; if `na_justification_required` is true, check for a usable justification.
- For `Met`, check a justification when `met_justification_required` is true and the presence of a URL when `met_url_required` is true. Prefer the stronger URL finding when a URL is required; do not also emit its entailed missing-justification finding.
- Match the pinned upstream predicates: usable justification is a string of at least five characters that does not begin with the exact prefix `// `; do not strip it before counting. URL presence requires a string that does not begin with `// ` and contains a match for `https?://[^/. ]+\.[^ ]`. This deliberately permissive text check neither parses a complete URL nor fetches it or assesses what it proves. These predicates are compatibility rules for the identified upstream revision; changes require updated fixtures and provenance.

Return `findings` with criterion ID, field, rule/code, and the relevant requirement. Examples include `na_not_allowed`, `missing_required_justification`, and `missing_required_url`. Report `checked_criteria` and `skipped_criteria` with reasons. Unrepresented criteria are outside the checked scope. If the supplied status is absent or `?`, report that conditional status-dependent checks were skipped; do not guess it or fetch a saved answer to complete the document. Other-level fields remain outside scope. No result implies that the whole application is complete or that a claim is true.

A completed check returns normally even when it finds problems; findings are data, not tool-execution errors. An unreadable source, wrong document root, invalid level, or conflicting aliases still prevent the check from running and return an operational error. Checkable field/type/status problems are returned as findings. Artifact generators do not require a prior validation call, a clean result, or a bypass flag. They remain able to prepare incomplete answers accepted by the BadgeApp edit flow.

This validator does not check undocumented field-length limits or predicted repository-import effectiveness. Its scope is the catalog's mechanical criterion requirements and the supplied answer shape.

## 5. Project-keyed draft storage

This is a convenience adapter around the document operations, with one file per project. There is no mutable active-project setting: each call selects its project explicitly. Different projects can be used concurrently through the same server instance.

### Input precedence

For validation and both generators:

1. If `draft` is supplied, use that document exclusively. An explicit `{}` is an empty document, not a request to fall back.
2. Otherwise, read `<data directory>/projects/<project_id>/.bestpractices.json` at call time.
3. If that file is absent, return `draft_not_found` with guidance to initialize the project draft or supply an explicit document.

An explicit document is never merged with, or written to, a stored draft. Reject explicit JSON `null` for `draft` rather than treating it as omission. Only `update_draft` writes draft files or creates storage directories. Each generator uses one complete document snapshot and reports whether its source was the explicit input or the project's stored file. Later draft updates do not change an already generated artifact.

### Creation and writes

`read_draft(project_id)` on a missing file returns `draft_not_found` with the project ID. It does not create storage. `update_draft(project_id, changes)` applies the patch to the document present when the operation executes. If absent, apply the patch to an empty object and create the data root, project directory, and file as needed. No prior read, revision token, or create-mode argument is required. Invalid existing JSON is an error, never an empty draft. A missing local draft is distinct from an unregistered BadgeApp project.

Each server process keeps an in-memory mutex keyed by project ID. Hold it only while loading, patching, structurally validating, size-checking, and writing that project's document. Calls updating other projects do not share this guard. Overlapping updates within one server must have an outcome equivalent to applying the patches one at a time: disjoint changes survive; for the same field, the later applied patch wins. No arrival order is promised. The guard protects a file operation, not a protocol session or a multi-call workflow; every request remains self-contained.

Serialize the complete result to a temporary file in the destination directory, flush it, and atomically replace the destination. Preserve existing permissions; create new drafts with owner-only read/write permissions where supported. A validation, size, or write failure before replacement leaves the previous file unchanged. Report success only after replacement succeeds. No-op updates need not rewrite an existing file. Reject symlink draft destinations rather than replacing a link unintentionally. Release the in-memory guard on success or failure and clean up temporary files on handled failures.

A read overlapping a server update may observe the complete document before or after replacement, never JSON partially written by that update. Reads do not take a filesystem lock or require client sequencing.

V1 does not coordinate separate server processes or external editors writing the same project file. Hosts must avoid simultaneous writers to the same project in a shared data directory. Two independent servers can otherwise read the same starting document and replace it separately, losing even unrelated changes from one writer. Atomic replacement prevents partial files; it does not merge these independent writes. Different data roots provide independent drafts when hosts need them. There are no filesystem lock files, cross-process locking dependencies, revision checks, or `draft_conflict` results.

If a response is lost after replacement, the outcome is uncertain to the caller; the host can read the draft to inspect it. The server does not automatically retry an ambiguous mutation. No operation writes both the filesystem and BadgeApp.

## 6. Artifact generation

Both generators validate the target, load the selected draft, fetch a fresh public record to verify the registered project and available identity, and encode eligible supplied fields relevant to the requested level. A missing document field means no proposed change. Include the four supported metadata fields where the target form supports them. Public answer values do not determine artifact inclusion: preserve eligible supplied values even when they match the public record.

Do not add generator field selectors or a staged-submission state model. Normal host guidance is to update answers as work proceeds. If a user wants only a subset of locally stored answers transferred, the host may read the draft, construct the desired subset, and supply it as the explicit document. That accepted host responsibility does not change the stored draft and does not require a special MCP interface. The host remains responsible for opening artifacts and saving the website form.

Public read failure prevents artifact generation because the registered target and supplied identity cannot be verified. Return the upstream error. No draft updates result from fetching live data.

The generator must not impose stricter criterion-completeness requirements than BadgeApp's edit/save flow. An omitted required justification or evidence URL does not fail generation or cause an otherwise transferable answer to be omitted. Such gaps affect criterion credit. Only the separate `validate_draft` tool reports these mechanical completeness findings; generators neither report them nor use them as gates.

Distinguish criterion-credit requirements from actual BadgeApp field constraints and transport limits. Unsupported `N/A` is an upstream model constraint, not merely incomplete evidence. Any excluded field must have a specific acceptance or representation reason, not a judgment that the claim lacks sufficient support. An invalid unrelated answer does not block the requested level. Report partial transfer explicitly. Structurally unreadable input is a whole-call error.

Do not turn this distinction into a requirement to mirror BadgeApp's model validators. In particular, implementation-derived field-length limits do not cause generation rejection, omission, or an advisory report. BadgeApp handles those constraints when the user saves. Runtime results describe the operation performed, its artifacts, and concrete operational failures; broader guidance belongs to host skills or documentation.

Do not compare supplied answers with saved companion fields, synthesize omitted justifications as blank, or predict how BadgeApp will populate the edit form. Neither artifact generation nor structural validation determines whether claims are true. Advisory assessment of evidence belongs to the host.

Every result identifies the target, level, catalog revision, draft source, website observation time, and identity-check outcome. The transfer report accounts for supplied fields as encoded, outside the selected level, unsupported, invalid for transfer, or otherwise omitted with a specific reason. It reports artifact inclusion, not predicted form effects. Never describe an artifact as a successful website update.

### Proposal URLs

Generate documented project/level edit URLs with correctly encoded values. Default to upstream's unforced proposal behavior. Preserve supplied text exactly, including whitespace, control characters and empty strings. BadgeApp interprets the query and applies its documented retention, normalization and override rules when the form is opened; the MCP does not evaluate those effects against saved answers.

The tool description explains that BadgeApp documents trimming leading and trailing whitespace from URL-proposed justification text when applying it to the edit form. This is general guidance about the URL interface; it does not add per-field classifications, normalize artifact values, or introduce additional result fields.

For a justification-only request, encode only the supplied justification; no status carrier is needed. Encode eligible supplied fields even if their values equal saved answers. An omitted or unknown status does not by itself disqualify a supplied justification. The host chooses explicit overrides using the documented website procedures and reviews actual results in the browser.

`override_fields` accepts exact canonical fields explicitly supplied in the draft and relevant to the requested level, not arbitrary globs or `*`. Reject unrelated entries. Report the sorted, deduplicated `requested_overrides`, and report as `effective_overrides` only explicitly requested fields encoded in the URL's `overrides` parameter. Do not add a justification override because its status is overridden. BadgeApp handles the documented implication from status overrides to paired justifications; preserving all eligible supplied fields leaves that interpretation to the site. A transfer row's `override` flag describes the explicit encoded parameter, not a prediction of replacement. This is artifact preparation, not authorization to save a form.

Return at most one URL artifact per call, with `url` containing the exact generated string and `encoded_size_bytes` containing its UTF-8 byte length after URL encoding. Count the URL itself, not the surrounding JSON serialization or display markup. Do not impose a guessed URL-length limit, automatically split changes, truncate evidence, or implement a URL-delivery retry interface. Partial transfer refers to omitted requested changes, not URL length. Display, copying, opening, and responses to delivery failures belong to the host.

Treat the structured URL string as the authoritative artifact. The host should open or copy that exact value without model reconstruction, display truncation, extra escaping, or accidental punctuation. A copied URL failing while direct opening works is not sufficient evidence of a size limit: first distinguish transport/presentation changes from a rejection of the exact same URL. A host may provide direct opening, an exact copy control, or a downloadable artifact; these remain host operations.

When no URL is generated, return `artifact: null` with a machine-readable reason and explanation distinguishing no supplied transferable answers from supplied work that could not be represented. Otherwise, `artifact` contains the `url` and `encoded_size_bytes` fields described above. Matching a saved answer is never grounds for omission. V1 does not support using `?` to reset live answers: omit unknown status placeholders and report them, evaluating supplied justifications independently. The upstream proposal guide and automation-approach decision matrix disagree about unknown-status resets; the [transfer rules](transfer-rules.md#unknown-status-limitation) record the chosen boundary. Any reset support requires a separate reviewed contract change. Do not silently infer reset intent from a reusable draft.

### Form-fill scripts

Return JavaScript as content with a suggested filename and instructions. Bind the script to the expected BadgeApp origin, project ID, and level; verify these before changing any form field. A wrong page causes a clear failure without changes.

Serialize data safely as JSON rather than interpolating answer text into executable code. Preflight intended form controls before writing, report missing controls, and avoid knowingly filling only part of the requested set. Set values and dispatch appropriate input/change events; return a runtime report of filled and missing fields. A DOM script is not a transactional browser API, so runtime errors must remain visible.

The script does not fetch credentials, submit the form, navigate, or save the application. It can carry long answers and wording replacements, including a supplied justification without an explicit draft status; in that case it changes only the textarea, without borrowing a status or running completeness checks. V1 still reports unknown-status resets as unsupported. Unlike unforced URL proposals, executing the script replaces the specified form values; its report and instructions must state that behavior. If an explicit unknown placeholder accompanies a justification, leave the status control alone and evaluate the supplied justification independently.

## 7. Errors, protocol behavior, and limits

Use SDK-supported structured results with brief readable summaries. Domain failures are tool execution errors with a stable `code`, explanatory `message`, relevant field/path details, and a recovery action. Examples include `invalid_document`, `invalid_field`, `invalid_level`, `draft_not_found`, `draft_write_failed`, `document_too_large`, `project_not_found`, `project_mismatch`, `upstream_unavailable`, and `rate_limited`. Protocol/schema errors remain distinct from domain errors. A valid empty search or a generation result with no eligible supplied fields is not an error.

Mark public/catalog/file reads and artifact generators read-only. Mark `update_draft` as a local mutation; do not mark it read-only just because it never contacts BadgeApp. Reapplying a patch without intervening edits is a content no-op, but that does not authorize automatic retries after an uncertain outcome. Describe effects accurately in tool metadata. Supply the protocol's discovery/list caching hints through the SDK. Internal reuse of the loaded catalog is an application implementation detail; MCP's specified cache hints do not cover `tools/call` results. Do not add resources solely to obtain caching. See [MCP caching](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching).

Use `.json` URLs for structured API reads and explicit `.svg` badge URLs for image artifacts, finite timeouts, bounded GET retries, and shared request pacing of at most one request per second per server process. Respect upstream rate-limit responses and `Retry-After`; concurrent tool calls must share the limiter. Several independent processes can still aggregate traffic. Never retry writes to the local draft automatically after an ambiguous outcome.

Publish bounded document/response sizes as implementation limits. Decoded SVG responses have a 1 MiB limit, separate from the 8 MiB JSON body limit and 16 MiB complete serialized MCP-result limit. Oversized documents or artifacts fail explicitly rather than being truncated. Criteria and progress filters reduce response size; discovery uses upstream pagination. Do not add output-format knobs merely to duplicate structured data. Do not log draft bodies, generated scripts, or full proposal query strings by default.

Check the resulting draft size before committing an update. Every document successfully written by `update_draft` must remain returnable by `read_draft` under the server's own response policy, accounting for its result envelope and any compatibility representation. If the update would violate that invariant, return an error without changing the file. This is a server storage/response guarantee, not enforcement of upstream BadgeApp field/import limits.

Keep `read_draft(project_id)` as a complete-document read. Do not add filtered reads to optimize a presumed model-context cost: the recipient is the host, which controls what is presented to its model or UI. No demonstrated document-size need justifies another read mode in v1.

## 8. Example workflows

### Host-owned document

1. `find_project(query="https://example.org/project")` returns candidate IDs. The host selects the correct registered entry. If there is no match, the user registers the project in BadgeApp and the host repeats lookup before proceeding.
2. `get_project_progress(project_id=123, level="passing")` returns saved answers.
3. `get_criteria(level="passing", criterion_ids=["description_good"])` supplies official requirements.
4. The host develops an answer with the user and calls `build_draft(draft={}, changes={...})`.
5. `prepare_update_url(project_id=123, level="passing", draft={...})` returns proposals and any omissions.
6. The host opens the selected URL or saves the returned document when requested.

No storage environment variable or local checkout is required.

### Server-managed project drafts

1. The host launches the server with its default data directory or a `BESTPRACTICES_DATA_DIR` override, then resolves and selects registered project 123.
2. `read_draft(project_id=123)` optionally retrieves the existing document; a missing file returns `draft_not_found`.
3. `update_draft(project_id=123, changes={...})` applies a small patch, creating the project draft if absent. Step 2 is not a prerequisite.
4. `prepare_update_url(project_id=123, level="passing")` reads that file without retransmitting it through tool arguments.
5. If URL transfer cannot carry some changes, `prepare_update_script(project_id=123, level="passing")` returns a form-fill artifact from the same file.
6. After any save performed by the host/user, `get_project_progress` can inspect the actual saved result. This does not synchronize the local draft automatically.

Restarting the server preserves each project's draft. After resolving the registered project, the host reads its draft by ID. Working on project 456 selects a different file without restarting or reconfiguring the server. There is no handle to reopen, active-project session to recover, or hidden draft copy.

Separate generator calls read independently. If either the file or the live application changes between URL and script generation, results may differ. There is no shared cross-call snapshot or draft version token.

## 9. Implementation and acceptance

Catalog access, public API reads, document operations, artifact generation and optional local persistence are separate from MCP registration. The [architecture](architecture.md) maps these responsibilities to modules and the reference host.

Acceptance checks must cover:

- Every supported level, level-qualified repeated criteria, catalog provenance, and offline criteria lookup.
- Non-GitHub project URLs, ambiguous/empty/paginated searches, missing projects, real saved justifications, and missing upstream fields.
- Registration/ID resolution before host application work, ambiguous lookups requiring selection, and no local draft creation when registration has not been completed.
- Document-only operation with default storage untouched; explicit document precedence including `{}`; no hidden file reads or writes.
- Default and overridden data roots, multiple project IDs in one server instance, independent files, small patches, explicit directory/file creation without a prior read, restart persistence, unknown-field preservation, alias conflicts, null removals, and validation without partial writes.
- Deliberately overlapping same-process updates preserve disjoint patches, including first-file creation. Same-field updates produce a valid one-at-a-time outcome without asserting arrival order. Different projects have separate guards. Reads see complete JSON and injected pre-replacement failures preserve the previous draft. No cross-process merge guarantee is tested or claimed.
- Identified document/target mismatches and honest distinction between storage-key association and explicit caller-supplied targeting.
- Missing required justifications/evidence URLs remain transferable wherever the BadgeApp edit/save flow accepts them; completeness findings are available only through the separate validator and never gate generation. No status is invented for a justification-only request, and replacement of existing wording requires the appropriate explicit URL override.
- Mechanical validation reports missing required `N/A`/`Met` explanations and required URL text according to the selected level. It skips conditional checks without a known supplied status, performs no network calls or writes, and does not gate generators. Repeated criterion IDs are checked with the requested level's flags.
- URL encoding, exact explicit overrides, inclusion of all eligible fields regardless of saved values, conservative unknown-status handling, exact UTF-8 byte counts after encoding, and explicit no-artifact reasons. Long URLs are returned intact without automatic batching or a guessed URL-length rejection threshold.
- Script target guards, missing controls, text escaping, metadata fields, and absence of submit/navigation behavior.
- JSON document fidelity: preserve fields through explicit patches, return the resulting document without advisory import findings, and do not apply upstream repository-import limits as local draft/generation limits.
- MCP discovery and typed results in an actual target host, bounded errors/retries, shared network pacing, and protocol-clean stdout.
- A realistically sized assessment edited through small `update_draft` calls and used by both generators without repeated full-document arguments.

Use deterministic fixtures for routine tests, with expectations derived from documented upstream procedures, criteria YAML and explicitly agreed contract rules. Validate the approved form behavior against controlled test instances. Synthetic forms verify script guards and assignments, while the locally supervised live browser runbook checks the real integration. Import and Save/Submit internals remain outside the MCP contract. Read-only live smoke tests can confirm public API compatibility; no production saves are needed for acceptance. Exercise the live browser runbook after the first beta publication and before stable promotion; repeat it for subsequent release candidates. Keep the SDK and compatibility fixtures pinned and review updates against these boundaries.

The [implementation contract](contracts.md) fixes initial document/response-size limits; implementation must verify their full-envelope accounting and record tested host compatibility before release. These are implementation limits, separate from BadgeApp's field and repository-import limits, which may be documented without becoming server checks.
