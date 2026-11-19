# Roadmap

This document says what the project intends to do, and what it does not intend to do, over the next year. No item has a release date. A proposal is not a commitment, and it does not change what the server supports today. [CHANGELOG.md](../../CHANGELOG.md) lists what each release contained.

## Planned

- **MCP prompts for common tasks.** Prompts that a person can pick in a host: report the status of a project, list what is left at a level, and work through a level.

## Proposed

- **Offline criteria search.** Find criteria by topic or wording across the packaged catalog, with an optional level filter and bounded results showing matching requirement text and details.
- **A tool for project metadata.** One tool that sets the name, description, license and languages in a draft. See the [proposal](project-metadata-tool.md).
- **Richer project search.** Search by URL prefix, and filters for badge status and progress. See the [proposal](api-coverage.md).
- **Ecosystem statistics.** One bounded tool for BadgeApp's public participation figures. See the same [proposal](api-coverage.md).
- **Translated criteria.** Criteria text and edit links in languages other than English.
- **A different default data directory.** A dot-directory in the user's home. See the [research](draft-storage-location.md).

## Implemented

- **Badge images.** `get_project_badge_svg`, for both badge series. See [ADR 0001](../adr/0001-badge-image-and-status-tools.md).
- **Project status for every level.** `get_project_status`, from one read of the project record.
- **Markdown resources.** The criteria and a project's saved answers as documents that a person can attach in a host.

## Deferred

- **A feed of recent project activity.** Deferred until monitoring is a demonstrated need.
- **Bulk export and portfolio dashboards.** A host can combine the existing tools first.
- **Criteria fetched live from the site.** The server keeps its packaged catalog.

## Not planned

- Signing in to BadgeApp, saving an application, registering a project, or managing accounts. [Design decisions](../reference/design.md) gives the reasons.
- A tool that judges whether an answer is correct, or that advises how to satisfy a criterion.
- A generic tool that calls any BadgeApp route, or one tool for each upstream endpoint.
- A hosted or network transport.

## Cancelled

- **The compact badge status tool.** `get_project_status` replaced it.
- **The reference terminal host.** See [ADR 0004](../adr/0004-remove-reference-host.md).
- **The console script tool.** See [ADR 0003](../adr/0003-remove-console-script-tool.md).
