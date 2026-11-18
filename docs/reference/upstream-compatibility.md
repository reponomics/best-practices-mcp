# Upstream compatibility

This document says which parts of BadgeApp the server depends on and how the server reads them. [Upstream updates](../maintenance/upstream-updates.md) describes how the pinned copy of the upstream sources is kept current. [Criteria catalog](catalog.md) describes how the catalog is generated from those sources.

## Sources and authority

The server follows the procedures that BadgeApp documents. The repository keeps a pinned copy of four upstream documents in `vendor/badgeapp/docs/`:

- [API documentation](../../vendor/badgeapp/docs/api.md)
- [Automation proposals](../../vendor/badgeapp/docs/automation-proposals.md)
- [Automation approach](../../vendor/badgeapp/docs/automation-approach.md)
- [Repository JSON guidance](../../vendor/badgeapp/docs/bestpractices-json.md)

These documents are the authority for the server's behavior. BadgeApp's source code is not. Where a project document relies on a detail that was read from upstream source, that document says so.

The pinned copy identifies the documents that the server was written and tested against. It does not say which revision the website runs.

[ADR 0001](../adr/0001-badge-image-and-status-tools.md) records the upstream evidence for the badge image routes.

## Requests

Every request is a GET to `https://www.bestpractices.dev`. The server sends no authentication and no cookies, and it does not follow redirects. All reads share one pacing and retry policy. [Contracts](contracts.md#limits) gives its values.

| Use | Route |
| --- | --- |
| Project record, for status, saved answers and the target check of a proposal URL | `/projects/{project_id}.json` |
| Search by repository or homepage URL | `/projects.json?url={query}&page={page}` |
| Search by text | `/projects.json?q={query}&page={page}` |
| Badge image | `/projects/{project_id}/badge.svg` and `/projects/{project_id}/baseline.svg` |

The server sorts query keys and encodes a space as `%20`. A URL in a search is a query value. The server never fetches it.

## How the server reads a response

- **Status.** The server copies `badge_level`, `updated_at` and, for each level, the percentage and the times when the level was achieved and lost. It derives nothing from them. `updated_at` is the time when the record last changed. It is not a receipt for a submission.
- **Saved answers.** BadgeApp stores a status for every criterion, and `?` is the status of an unanswered criterion. A justification can be absent, which means that it is empty. If a response lacks a status that the catalog expects, the server reports that status as not retrieved. It does not invent a value.
- **Search.** The server returns the candidates that BadgeApp returns, in the same order. It does not choose between them.
- **Proposal target.** Before the server builds a proposal URL, it reads the project record to confirm that the project exists and matches the draft. It does not compare the draft with the saved answers.
- **Badge image.** The server returns the SVG text as data. It checks the content type, the encoding and the XML root, and it rejects a document that has a DTD or entity declarations.
- **Unexpected values.** A field with an unexpected type is an invalid response. An unfamiliar string value, such as a new badge level, is passed through unchanged.

## Proposal URLs

A proposal URL points to `/en/projects/{project_id}/{section}/edit`. The section is one of the six level names, or `choose` when the person selects the section on the site. The public JSON routes have no locale. The edit links use the English path.

[Transfer rules](transfer-rules.md) states which fields a proposal URL carries and how overrides are expressed. BadgeApp decides how to apply a proposal when a person opens the form. The server does not predict that result. The [live browser runbook](../testing/live-browser-qa.md) checks it against the real form.
