# ADR 0001: Separate badge images from compact status observations

- **Status:** Accepted for implementation by the user on 2026-11-14; implemented by the two badge tools.
- **Date:** 2026-11-13
- **Related:** [Roadmap](../roadmap.md#priority-2-separate-badge-image-and-quick-status-tools), [human-review boundary](../design.md#prepare-changes-leave-the-final-save-to-the-human), [current tool specification](../specification.md).

## Context

BadgeApp exposes each project's Best Practices and Baseline badges in SVG and compact JSON forms. These support two concrete tasks: obtaining a badge for a README, and quickly inspecting a project's badge progress and last update time. The current `get_project_progress` already provides an all-level summary when no level is selected, and detailed progress and saved criterion answers when a level is selected. Both modes fetch the full project JSON record. The compact status tool therefore adds a smaller upstream response and a family-specific observation contract, not summary access for the first time.

The design question is whether to combine image and status retrieval, separate them by user task, or create individual tools for values such as progress and `updated_at`. A further consideration is whether an agent can use update time to follow up after a user saves proposed changes.

Research uses upstream revision [`31325acd7963e0c9203da0ff798802a766237517`](https://github.com/ossf/best-practices-badge/tree/31325acd7963e0c9203da0ff798802a766237517). This is the scoped compatibility reference for the four added badge endpoints; it does not update the catalog/transfer baseline or establish the deployed production revision. The [controller](https://github.com/ossf/best-practices-badge/blob/31325acd7963e0c9203da0ff798802a766237517/app/controllers/projects_controller.rb) serves both formats; the [metal JSON view](https://github.com/ossf/best-practices-badge/blob/31325acd7963e0c9203da0ff798802a766237517/app/views/projects/badge.json.jbuilder) and [Baseline JSON view](https://github.com/ossf/best-practices-badge/blob/31325acd7963e0c9203da0ff798802a766237517/app/views/projects/baseline_badge.json.jbuilder) define their distinct payloads.

## Decision

Provide two tools, both accepting an explicitly selected `project_id` and a `family` (`best_practices` or `baseline`). The SVG tool requires an explicit family. The status tool defaults an omitted family to `best_practices` and returns the effective family, allowing a project-wide update-time question without an unnecessary family choice. Keep progress, badge state and update time together in a single compact status observation. Do not add field-specific tools such as `get_project_updated_at` or `get_badge_percentage`.

| Tool | User task | Source and result |
| --- | --- | --- |
| `get_project_badge_svg(project_id, family)` | “Add my project's badge to the README.” | Fetch `/projects/{id}/badge.svg` or `/projects/{id}/baseline.svg`; return a bounded SVG artifact, media type, dynamic image URL, project-page URL and Markdown embed snippet. |
| `get_project_badge_status(project_id, family="best_practices")` | “Show my badge progress and when the record was last updated.” | Fetch `/projects/{id}/badge.json` or `/projects/{id}/baseline.json`; return identity, effective family, family-specific badge/progress fields, upstream `updated_at`, source URL and MCP `fetched_at`, with separately identified service credit. |
| Existing `get_project_progress` | “Inspect saved answers and detailed progress for this project.” | Continue using the full project record, with level and criterion selection. Use directly when detailed answers are needed. |

Each new tool makes one logical endpoint request, subject to existing bounded transport retries. Neither automatically calls the other or fetches the full project record. Neither changes files, saves remotely, initializes drafts or maintains polling state.

### SVG and embedding

Prefer the dynamic ID-based image URL in generated README Markdown so it can reflect subsequent badge changes. A downloaded SVG is a snapshot; `/badge_static/{value}` is unsuitable for a project's evolving badge. The host decides whether to insert the snippet or save the SVG artifact.

The shared transport supports explicit SVG routes and media-type handling. It returns SVG as data without executing, rendering or sanitizing it. Decoded SVG bodies are limited to 1 MiB, with the complete serialized MCP-result budget checked separately. UTF-8 and SVG-root XML validation reject DTD/entity declarations. The artifact carries the original decoded SVG text in `artifact.svg`, plus media type, suggested filename and UTF-8 byte count, in structured content and the equivalent JSON text fallback. Fixed origin, rate limiting and the no-redirect policy are unchanged.

### Compact status contract

Both JSON variants supply `id`, `name`, `updated_at` and `badge_level`. Best Practices adds `tiered_percentage`. Baseline instead adds `badge_percentage`, which measures Baseline level 1; its `badge_level` can be an achieved level or a display value such as `baseline-pct-65`.

Keep those distinctions explicit rather than invent a universal percentage. Preserve upstream values and identify unrecognized badge values without treating them as an earned badge or zero progress. Do not populate unavailable detailed level percentages. Distinguish the upstream record's update time from the MCP fetch time; neither is proof that a cached response reflects every recent edit. Missing or malformed timestamps must be explicit, not replaced by the fetch time.

Neither badge JSON response supplies the full record's project-entry attribution/license fields. Provide source URL, fetch time and documented service-level credit separately; mark per-record attribution as unavailable from this endpoint rather than inventing pass-through values or fetching the full record to obtain them. Both families expose the underlying project's `updated_at`, not a family-specific change timestamp. Their independently cached responses need not show the same observed value at a given moment.

Progress and update time belong together because they answer one question about the same project/family observation: what badge status does BadgeApp report, and when was its project record updated? Their shared small upstream response supports that boundary but does not by itself justify combining operations. Field-specific tools would repeat requests, consume the shared rate limit and could observe different versions of the record. They would add tool-selection complexity without a distinct user task or upstream efficiency benefit. Returning the complete compact response also lets an agent interpret update time in the context of the observed badge state.

### Reviewed discovery descriptions

Here, “combined” means badge state, progress and update time in one status observation. SVG retrieval remains a separate tool. The reviewed descriptions below define the discovery boundaries; exact result schemas are in the [implementation contract](../contracts.md#badge-observations-and-svg-artifacts).

**Name:** `get_project_badge_status`. **Title:** Get project badge status.

> Return a compact public badge-status observation for one selected BadgeApp project from the OpenSSF Best Practices Badge API (https://www.bestpractices.dev). Includes project identity, effective badge family, reported badge level, family-specific progress, project-record update time and source/fetch metadata. The family defaults to Best Practices, which reports tiered progress; Baseline reports level-1 completion. Responses may be cached, and update time does not establish whether proposed answers were saved. All-level summaries, individual-level progress and saved criterion answers are available through get_project_progress; SVG badges and README embedding are available through get_project_badge_svg.

| Argument | Constraint | Description |
| --- | --- | --- |
| `project_id` | Required positive integer | ID of the existing BadgeApp project selected by the host. |
| `family` | Optional enum: `best_practices`, `baseline`; default `best_practices` | Badge family to observe; the effective family is returned. Each call fetches one family. |

Example call: `get_project_badge_status(project_id=123)` observes Best Practices. An explicit `family="baseline"` returns Baseline's distinct measurement rather than substituting metal-series progress. The badge-tool annotations are read-only, non-destructive, idempotent and open-world. Idempotence describes absence of additional side effects, not identical values across calls.

Reciprocal discovery text for existing `get_project_progress`:

> Read a selected BadgeApp project's saved progress and answers from its public project record. With no level, returns percentage summaries across all six supported levels. With a level, includes that level's progress and criterion answers; criterion_ids narrows the returned criteria. Includes source and observation provenance. Compact badge-family status and project-record update time are available through get_project_badge_status; SVG badges and README embedding are available through get_project_badge_svg.

| Review prompt | Expected routing |
| --- | --- |
| “When was project 123 last updated?” | `get_project_badge_status(project_id=123)`; project-record update time, with explicit default family and cache caveat. |
| “What Best Practices badge does it report?” | Compact status with `best_practices`. |
| “What Baseline badge does it report?” | Compact status with `baseline`; the accompanying percentage refers only to level 1. |
| “How close is it to silver?” or “What is its Baseline level-2/3 percentage?” | `get_project_progress` with the named level. |
| “Show progress across all six levels.” | `get_project_progress` without a level. |
| “Were my proposed criterion answers saved?” | Detailed saved-answer readback, without a mandatory status preflight. |
| “Add its badge to the README.” | `get_project_badge_svg`; the host handles the edit. |

These cases informed a [bounded routing exercise](../planning/badge-tools-routing-review.md) on 2026-11-14: a fresh-context subagent chose the intended first tool and arguments for all ten supplied prompts. This single exercise is not a guarantee of routing across hosts or models. Detailed host workflow instructions belong outside the discovery descriptions.

### Scorecard precedent and limits

[Scorecard PR #5402](https://github.com/ossf/scorecard/pull/5402) merged on 2026-11-03. Its imported [design audit](https://github.com/ossf/scorecard/blob/ab792da5b906666164d82faa3378374fc664aad0/docs/design/mcp-design-audit.md) favors tools scoped to an action, descriptions that distinguish related tools and bounded results. The audit predates the import and is not a fresh endorsement by BadgeApp maintainers. The accepted [`get_repo_score` tool](https://github.com/ossf/scorecard/blob/ab792da5b906666164d82faa3378374fc664aad0/cmd/internal/mcp/server/tools_results.go) combines score summaries with scan date and provenance while separating detailed check retrieval. The [PR's metadata review](https://github.com/ossf/scorecard/pull/5402#discussion_r4451249701) reinforces preserving interpretive context in compact outputs.

Our inference is that a cohesive status observation can contain several fields without becoming a general-purpose tool. This supports evaluating the combined status candidate, not treating Scorecard acceptance as approval of this design. Its main unresolved review question is whether users can reliably distinguish it from the existing all-level summary; the smaller upstream payload is a benefit, not sufficient justification by itself.

An independent second source-and-contract review on 2026-11-13 found no architectural blocker but requested reciprocal progress-tool discovery text and explicit attribution sourcing. Both revisions are included above, together with a documented default family for timestamp-only questions. The reviewer favored keeping progress and update time in one observation. That review did not establish empirical host/model selection accuracy. The user authorized implementation on 2026-11-14; the subsequent routing exercise provides the limited evidence described above.

### Following up after a save

Update time is a useful hint for deciding to inspect saved answers, not an acceptance receipt. A newer timestamp does not identify the actor or changed fields. An unchanged timestamp or percentage does not prove failure: responses may be cached, justification edits need not change progress, and upstream criteria recalculation can change percentages without updating `updated_at`.

For a specific proposal, the host should read the relevant level and criteria through `get_project_progress` after the user/host saves, and compare the observed saved values with the proposal. It can report matching values, differing values or an inconclusive observation. Even matching values do not prove that a particular save caused them. A quick-status call is optional context, never a required gate for this readback, and a mismatch must not trigger an automatic save retry.

Do not add a timestamp-derived `accepted` boolean, a separate acceptance-checking tool or hidden polling. Comparing explicit observations in the host preserves the existing boundary: the server exposes saved data without predicting BadgeApp's save-time processing or claiming causal knowledge of a submission.

## Alternatives considered

| Alternative | Assessment |
| --- | --- |
| Separate tools for update time, badge level and percentage | Reject. They return fields from the same compact response and do not create distinct workflows or reduce upstream work. |
| One combined SVG-and-status tool | Reject. README embedding and status inspection are independently useful; combining them forces extra retrieval or introduces modes with unrelated result formats. |
| Add a compact mode to `get_project_progress` | Viable, but not preferred. The compact endpoint has family-specific fields and omits detailed level data; a separate, clearly described status tool makes that contract visible. Share implementation helpers where appropriate. |
| Use only the existing progress tool | Avoids a new tool, but still retrieves the large project record for a small status question. The compact upstream endpoint provides a concrete efficiency benefit. |
| Only construct an SVG URL | Enough for basic Markdown embedding, but does not provide the requested SVG contents for a host that needs the artifact. Return the URL and contents in the image tool. |

## Consequences and acceptance

This adds two discoverable tools, with intentional overlap between compact status and detailed progress. Descriptions and examples must make selection clear: image/embedding, quick status, or detailed saved answers. Consumers needing only `updated_at` use the status tool and select that field; consumers needing saved answers call `get_project_progress` directly.

Implementation requires strict input/result schemas, narrowly expanded route allowlists, SVG handling, family-specific JSON mapping, explicitly sourced credit and documentation updates. Acceptance covers both families, default/effective-family reporting, missing projects, malformed responses, bounded SVG artifacts, media types, Markdown escaping, dynamic image links, unknown badge values, percentage meanings, absent per-record attribution and no unintended secondary requests. Include changed/unchanged/missing/invalid timestamps and cached or justification-only changes; no quick-status result may assert proposal acceptance. Evaluate the paired discovery descriptions against the routing cases above. Use deterministic HTTP/adapter/stdio tests and bounded read-only compatibility checks. The supported surface now contains eleven tools; richer discovery filters and ecosystem statistics remain separate roadmap proposals.
