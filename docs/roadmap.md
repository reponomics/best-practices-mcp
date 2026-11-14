# Roadmap

Planned items are accepted directions for future work, without a committed release date. Proposed items remain under consideration and do not change the supported contract.

## Implemented

- **Badge SVG and compact status tools.** `get_project_badge_svg` and `get_project_badge_status` implement [ADR 0001](adr/0001-badge-image-and-status-tools.md), accepted on 2026-11-14. They cover both badge families while keeping image retrieval separate from progress/update-time observations.

## Planned

- **Deprecate the interactive reference host application.** Replace the full terminal workflow with a small executable SDK integration example. Preserve server behavior coverage through the existing SDK-based tests, and use MCP Inspector for independent-client smoke checks and exploratory QA. The current host remains available until that transition is implemented.

## Proposed

- **Support translations.** Explore localized criteria and language selection for BadgeApp interactions. Define language coverage, fallback behavior and translation maintenance before adding this capability; the current catalog and generated edit links use English.
- **BadgeApp API coverage.** Expand public reads around project discovery and ecosystem reporting, following the remaining proposals below. Badge image and compact status tools are implemented; other tool names and contracts remain provisional. Endpoint availability alone is not a reason to add a tool.

### API coverage expansion proposal

Research baseline: **2026-11-13**, upstream revision [`31325acd7963e0c9203da0ff798802a766237517`](https://github.com/ossf/best-practices-badge/tree/31325acd7963e0c9203da0ff798802a766237517). This research is the scoped reference for the implemented badge endpoints and the remaining proposals; it does not change the catalog/transfer baseline or establish the revision deployed in production. See [upstream compatibility](upstream-compatibility.md). Review used the [API documentation](https://github.com/ossf/best-practices-badge/blob/31325acd7963e0c9203da0ff798802a766237517/docs/api.md), [OpenAPI specification](https://github.com/ossf/best-practices-badge/blob/31325acd7963e0c9203da0ff798802a766237517/best_practices.openapi.yaml), and [routes](https://github.com/ossf/best-practices-badge/blob/31325acd7963e0c9203da0ff798802a766237517/config/routes.rb), with targeted controller/model/view inspection. No production requests were used to establish behavior.

#### Coverage and evidence

Before this expansion, the nine-tool surface fetched only `/projects/{id}.json` and `/projects.json` with `q` or `url`, plus `page`. The eleven-tool surface also fetches the four badge JSON/SVG routes below. `get_project_progress` already returns all six level percentages and available overall progress fields; adding another full-record progress reader would duplicate it. The opportunity is to expose useful search controls and smaller or different datasets.

| Upstream surface | Current coverage | Proposed disposition |
| --- | --- | --- |
| `/projects.json`: `q`, `url`, `page`, `pq`, `status`, `gteq`, `lteq` | Text/exact-URL discovery and pagination only | Extend `find_project` for cohort discovery; resolve filter semantics first. |
| `/projects/{id}.json` | Identity, progress and artifact identity checks | Retain existing tools; reuse collection summaries rather than fetching every matching record. |
| `/projects/{id}/badge.svg`, `/projects/{id}/baseline.svg` | Implemented by `get_project_badge_svg` | Bounded SVG artifact and dynamic README embedding for either badge family. |
| `/projects/{id}/badge.json`, `/projects/{id}/baseline.json` | Implemented by `get_project_badge_status` | Compact progress and last-updated observation for either badge family; detailed criteria remain in `get_project_progress`. |
| `/project_stats/{total_projects,nontrivial_projects,silver,gold}.json` | None | Candidate aggregate reporting tool, subject to response-size and compatibility gates. |
| `/en/project_stats/{activity_30,daily_activity,reminders,silver_and_gold,percent_earning,user_statistics}.json`; `/en/project_stats.json` and `.csv` | None | Inventory for later reporting needs; no separate tool per chart or unrestricted full-history export. |
| `/en/feed` (Atom) | None | Defer a recent-project-activity tool until monitoring is a demonstrated need. |
| `/projects.csv`; project section HTML/Markdown; `/en/criteria` and `/en/criteria/{level}` | None as fetched representations | Keep structured JSON and the pinned criteria catalog. Additional representations do not independently justify tools. |
| Collection redirects `as=badge`, `as=baseline`, `as=entry`, `as=edit` and section chooser pages | Existing tools resolve IDs and generate direct edit links | Keep explicit candidate selection and direct ID-based routes; do not add redirect wrappers. |
| Users, sessions, account management, project creation/update/deletion, permissions and administrative pages | Intentionally outside scope | No expansion under this proposal; authenticated writes require a separate design decision. |

The OpenAPI file is an inventory aid, not a sufficient executable contract. It describes three GET path families, uses optional path parameters, marks `as` required for collection queries, and provides only a minimal project schema. Its localized paths also need reconciliation with canonical locale-independent JSON routes. Do not generate an MCP tool per OpenAPI operation.

Two substantive discrepancies must be resolved before exposing status/progress filters: the docs/spec list `silver` and `gold` status values, but the inspected [controller](https://github.com/ossf/best-practices-badge/blob/31325acd7963e0c9203da0ff798802a766237517/app/controllers/projects_controller.rb) accepts only `in_progress` and `passing`; the docs describe `gteq`/`lteq` as passing percentages, but the [model](https://github.com/ossf/best-practices-badge/blob/31325acd7963e0c9203da0ff798802a766237517/app/models/project.rb) applies them to `tiered_percentage`. In that source, `passing` includes higher achievements. Record an explicit compatibility decision supported by documentation clarification and bounded read-only observations before promising exact-level filters or naming these bounds. Do not silently copy source behavior into the public contract or post-filter a single page and imply a complete cohort.

#### Priority 1: richer project discovery

**User need:** “Find projects in this repository namespace that are close to a badge,” or “Show projects that have earned at least passing.” Extend `find_project` rather than introduce overlapping `search_projects` and `list_projects` tools.

- Preserve existing `query`/`page` calls and automatic ID, exact-URL and text interpretation. Add an explicit prefix-search mode mapped to `pq`; a URL prefix identifies candidates, not verified organizational ownership.
- Permit filter-only discovery through a typed optional filter object. Require a query or at least one filter; do not introduce an accidental unfiltered database crawl. Reject filters combined with numeric ID lookup and reject contradictory bounds before a request.
- After the discrepancy gate, expose only supported status choices and clearly named progress bounds. If unresolved, ship prefix discovery independently and keep status/bounds deferred. Baseline filtering is not established by the documented collection API.
- Return compact candidate identity plus available badge/progress summaries from the same collection response. Include effective filters, source URL, fetch time and attribution. Keep missing fields unknown, preserve upstream ordering and make no additional detail request per candidate.
- Fetch one upstream page per call; preserve continuation uncertainty. Validate continuation links against every effective filter, not just the old `q`/`url` pair. Do not claim a total or completeness from the returned page size.

Acceptance examples: repository-prefix search; a verified near-passing range; an empty result; ambiguous identity; invalid filter combinations; continuation with unchanged filters; changed or omitted upstream fields. Explicitly test zero bounds and canonical query encoding: the inspected controller accepts positive integers for `gteq`/`lteq` and redirects after dropping invalid values, including zero. Decide which bounds to reject locally or normalize without changing their meaning; never follow a redirect that silently removes a requested filter. Add sorting or ID-set queries only after documenting their contract and establishing a user need; they exist in source but are not specified by the reviewed API search documentation.

#### Priority 2: separate badge image and quick-status tools

**Implemented.** [ADR 0001](adr/0001-badge-image-and-status-tools.md) records the accepted tool boundaries, discovery descriptions, alternatives, timestamp semantics and acceptance criteria. Both tools take an explicitly selected `project_id` and a `family` of `best_practices` or `baseline`. SVG retrieval requires a family; compact status defaults an omitted family to `best_practices` and reports the effective family.

- **`get_project_badge_svg(project_id, family)` — “Add my project's badge to the README.”** Return a bounded SVG artifact, its dynamic image URL, project-page URL and Markdown embed snippet. The host handles repository edits. Prefer the dynamic URL for an evolving README badge; downloaded SVG is a snapshot.
- **`get_project_badge_status(project_id, family="best_practices")` — “Quickly show progress and last updated.”** Return the compact JSON observation with project identity, effective family, family-specific badge/progress fields, upstream `updated_at`, source URL and fetch time. Identify service credit separately from per-record attribution, which this endpoint does not supply. Keep these fields together; separate update-time or percentage tools would repeat the same upstream request without serving a distinct task.

Retain `get_project_progress` for detailed level progress and saved criterion answers. Each new tool fetches only its own representation. Update time can prompt a host to re-check saved answers, but cannot prove proposal acceptance; direct criterion readback remains necessary for checking specific proposed fields. SVG media-type handling and family-specific JSON mappings preserve bounded transport and explicit timestamp uncertainty, without adding polling or automatic save retries.

#### Priority 3: bounded ecosystem statistics

**User need:** “How has badge participation changed over time?” Investigate `get_badge_statistics(metric, start_date, end_date, max_points)` with a small metric enum, initially project-entry counts and metal-series completion counts. Map each metric to one allowlisted endpoint rather than accept arbitrary chart paths. The [statistics model](https://github.com/ossf/best-practices-badge/blob/31325acd7963e0c9203da0ff798802a766237517/app/models/project_stat.rb) makes important distinctions: `total_projects` is a snapshot count of entries, not cumulative registrations; the passing 100% series in `nontrivial_projects` counts tiered progress at least 100; the silver/gold 100% series count completion of those levels without checking lower-level prerequisites. Name those metrics accordingly, not as counts of earned silver/gold badges. Threshold series can overlap and must not be added as mutually exclusive categories.

The [statistics controller](https://github.com/ossf/best-practices-badge/blob/31325acd7963e0c9203da0ff798802a766237517/app/controllers/project_stats_controller.rb) returns historical series without date-range pagination. Date filtering would therefore be local and would not reduce upstream transfer size. Measure representative payloads before accepting this tool; retain the existing transport limit and fail explicitly on oversized data. Do not raise limits merely to support unlimited history. Define deterministic point selection, report returned/source date coverage and any reduction, and keep fetch time separate from measurement timestamps. These are BadgeApp participation metrics, not measures of software quality or all open-source projects.

Start with locale-independent numeric datasets. Localized chart labels, activity rates, reminder effectiveness, user statistics, full exports and Baseline trends remain deferred until each has a clear reporting question and verified source support. Aggregate reporting does not require selecting an individual project or creating a draft. Acceptance covers missing dates, empty ranges, units, threshold semantics, oversized responses and explicitly reduced output.

#### Deferred and excluded work

- **Recent activity:** `/en/feed` could support `list_recent_project_updates(limit)` for discovering newly active projects. The inspected source limits it to 50 recently updated entries; it is not an audit log, a criterion diff, or a reliable “all changes since” cursor. Adoption requires a bounded Atom parser, safe handling of untrusted HTML, explicit feed-window limitations and a decision about whether a one-shot feed read is useful without adding server polling state.
- **Bulk export and portfolio dashboards:** compose bounded discovery and progress calls in the host first. CSV duplicates available project data; automated all-page downloads, persistent subscriptions and arbitrary batch sizes would add separate resource/lifecycle requirements.
- **Live criteria and translations:** retain the existing catalog revision/provenance contract. Browser criteria pages are not established as a replacement structured API; localization remains the separate proposal above.
- **Authentication and mutations:** no login/session tools, user-directory harvesting, project registration, direct saving, deletion, permission management or administrative automation. Preserve the existing [human-review design boundary](design.md#prepare-changes-leave-the-final-save-to-the-human).

#### Delivery sequence and shared gates

1. **Establish contracts.** Capture a small pinned endpoint/parameter/response matrix and synthetic fixture provenance; resolve the documented discrepancies for each proposed feature. Use limited, paced production GETs only as supplementary compatibility evidence. Update the supported baseline through its normal review process when needed.
2. **Deliver richer discovery separately.** The two badge tools are implemented. Discovery remains a separate proposal with strict input/result schemas, explicit route/query allowlists, adapter mappings, documentation and deterministic tests; its filter discrepancy is unresolved.
3. **Decide statistics after a boundedness spike.** Confirm payload sizes, metric definitions and output reduction before committing to a new tool. Keep activity feeds and other representations deferred.

Every addition reuses the shared GET client, one-request-per-second limiter, retry/cooldown rules, fixed production origin, body/result budgets and no-cookie/no-redirect policy. Add only specific supported routes and parameters; no generic `call_api` escape hatch. Preserve source attribution and explicitly label unknown, stale or incomplete information. Reads must not initialize or synchronize drafts. The badge-tool inventory and examples are maintained in the eleven-tool specification. Remaining proposals do not change that supported contract until separately implemented.
