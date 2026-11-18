# Best Practices MCP

[![OpenSSF Best Practices — project 16754](https://www.bestpractices.dev/projects/16754/badge.svg)](https://www.bestpractices.dev/en/projects/16754/passing) [![OpenSSF Baseline — project 16754](https://www.bestpractices.dev/projects/16754/baseline.svg)](https://www.bestpractices.dev/en/projects/16754/baseline-1) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/reponomics/best-practices-mcp/badge)](https://scorecard.dev/viewer/?uri=github.com/reponomics/best-practices-mcp)

## Description

Best Practices MCP lets an MCP-compatible assistant look up projects on the OpenSSF Best Practices Badge website (BadgeApp), inspect badge criteria and progress, retrieve badge images and README snippets, prepare draft answers, and generate proposed updates for review in the browser.

The server provides the tools; your assistant decides how to assess the project and organize the work. It can prepare an edit-page URL, but does not authenticate to BadgeApp or save changes. You review the actual form before deciding to save.

Maintained by Reponomics. This is an independent project, not affiliated with, sponsored by, endorsed by, or an official project of OpenSSF, the Linux Foundation, or the OpenSSF Best Practices Badge project or its contributors.

## Quickstart

Use an MCP host that supports local **stdio servers**, with Python **3.11 or newer** available. The project you are assessing can use any programming language.

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if needed, then add the following server to your host's MCP configuration. Hosts with a settings form can use the same command and arguments; the configuration file location and surrounding format depend on the host.

<!-- x-release-please-start-version -->
```json
{
  "mcpServers": {
    "bestpractices": {
      "command": "uvx",
      "args": ["--from", "best-practices-mcp==0.6.0", "bestpractices-mcp"]
    }
  }
}
```

This lets the host launch an isolated installation from PyPI. Alternatively, install persistently with `pipx install 'best-practices-mcp==0.6.0'` and configure the host to launch the installed `bestpractices-mcp` executable with no arguments.
<!-- x-release-please-end -->

Use an absolute executable path if the host cannot find `uvx` or `bestpractices-mcp` on its PATH. On Windows, JSON paths need escaped backslashes, for example `C:\Users\you` must be written as `"C:\\Users\\you"`. The package name is **`best-practices-mcp`**; the executable name is **`bestpractices-mcp`**.

Reload the host's MCP connections, then try a request such as:

> Find the BadgeApp project for https://github.com/reponomics/PolicyChecks and show its silver-level progress. Do not prepare any changes yet.

Starting the executable directly in a terminal waits for MCP messages; it is not an interactive CLI. See [Contributing](CONTRIBUTING.md) for development setup or the [Inspector guide](docs/inspector-qa.md) for interactive debugging.

## Tools

| Tool | What it does | Network or storage effects |
| --- | --- | --- |
| `find_project` | Find public project candidates by ID, repository/homepage URL, or text; the host selects the intended project. | Public BadgeApp GETs |
| `get_criteria` | List the bundled criteria of a badge level, or read the full text of selected criteria or a category. | Offline |
| `get_project_status` | Read a project's badge level, the percentage and achievement date at each of the six levels, and its last update time. | Public BadgeApp GET |
| `get_project_answers` | Read the answers a project has saved for one badge level, optionally filtered by criterion or status, with source and fetch time. | Public BadgeApp GET |
| `get_project_badge_svg` | Retrieve a badge SVG and dynamic README embed snippet for one badge family. | Public BadgeApp SVG GET |
| `build_draft` | Create or patch a document supplied by the host. | Offline; no stored files changed |
| `read_draft` | Read the complete locally stored draft for a project. | Local read |
| `update_draft` | Create or patch a locally stored project draft. | Local write; no BadgeApp update |
| `validate_draft` | Check supplied answers against the bundled criteria's mechanical requirements. | Offline; may read a stored draft |
| `prepare_update_url` | Generate a proposed edit-page URL and report included/excluded fields. | Public BadgeApp GETs; no remote write |

See the [tool specification](docs/specification.md) and [payload contracts](docs/contracts.md) for arguments, results and errors.

## Usage notes

- **Compatibility:** Python 3.11 is the supported minimum. The CI compatibility matrix targets Python 3.11/3.12 on Linux, macOS and Windows. The protocol baseline is MCP `2026-07-28`; transport is stdio. Node and Ruby are not required to run the server.
- **Catalog and language:** criteria are bundled from a pinned upstream revision, not fetched live. The current catalog is English and generated edit links use English paths. Translation support is [proposed](docs/roadmap.md#proposed).
- **Validation is advisory:** it checks mechanical requirements, not whether claims are true or evidence is sufficient. Validation is optional and does not gate artifact generation.
- **Review in the browser:** artifacts include eligible supplied fields even when they match saved values. Reports describe what was included or excluded, not what BadgeApp will retain or save. BadgeApp documents trimming leading/trailing whitespace from URL-proposed justifications. See [transfer rules](docs/transfer-rules.md) for override behavior.
- **Authentication stays in your browser:** public reads need no BadgeApp credentials. Applying proposals requires your own authenticated session and appropriate project permissions.

### Project status and README images

After selecting a project, `get_project_status(project_id=123)` reports the badge level it holds, the percentage complete and achievement date at each of the six levels, and when the entry was last updated; `fetched_at` records when the response was retrieved. It is the tool for any question about where a project stands. Use `get_project_answers` with a level for the answers saved to individual criteria.

`get_project_badge_svg(project_id=123, family="best_practices")` returns SVG text, a dynamic image URL and a Markdown snippet. The host can insert the snippet in a README or save the SVG. Prefer the dynamic URL for a badge that follows future project changes; downloaded SVG is a snapshot. The server does not render SVG or modify repository files. The tool supports `best_practices` and `baseline` and creates no drafts.

### Optional draft storage

A host can keep drafts itself and pass them explicitly, or use one server-stored `.bestpractices.json` per project across badge levels. For validation and artifact generation, an explicit document, including `{}`, bypasses storage; omitting it reads the selected project's stored draft. Only `update_draft` writes files.

Default storage locations are:

| Platform | Data directory |
| --- | --- |
| macOS | `~/Library/Application Support/bestpractices-mcp` |
| Linux | `$XDG_DATA_HOME/bestpractices-mcp` when XDG is absolute; otherwise `~/.local/share/bestpractices-mcp` |
| Windows | `%LOCALAPPDATA%/bestpractices-mcp` |

To choose another location, set `BESTPRACTICES_DATA_DIR` in the server's environment through your MCP host. Use an absolute path; `~` is not expanded. Avoid simultaneous writers from separate server processes or external editors to the same project draft. After an uncertain update result, use `read_draft` before deciding whether to issue another patch. See [persistence boundaries](docs/architecture.md#optional-local-persistence).

If you prefer a dot directory in your home directory, add an `env` entry to the server configuration, for example `"env": {"BESTPRACTICES_DATA_DIR": "/home/yourname/.bestpractices-mcp"}`. Replace that example with your actual absolute home path (on macOS, typically `/Users/yourname/.bestpractices-mcp`). Changing the setting does not move existing drafts: either keep using their original directory or stop the server instances and move the existing `projects` directory into the new data directory, taking care not to overwrite drafts already there.

## Share your experience

Help improve best-practices-mcp by [sharing how you used it](https://github.com/reponomics/best-practices-mcp/issues/new?template=usage_report.yml). A brief account in your own words is enough: what you tried, how it went, which assistant/model(s) you used if known, and any additional feedback. Successful, partial, and unsuccessful interactions are all welcome.

Reports are voluntary and self-reported. We may summarize them in the [interaction log](docs/interaction-log.md), with a link to the original issue.

## Documentation

- [Documentation index](docs/README.md): the complete guide to maintained documentation and historical records.
- [Design](docs/design.md) and [architecture](docs/architecture.md): responsibilities, data flow and the human-review boundary.
- [Specification](docs/specification.md) and [contracts](docs/contracts.md): tool behavior, exact payloads and operational limits.
- [Upstream compatibility](docs/upstream-compatibility.md), [transfer rules](docs/transfer-rules.md) and [schema compatibility](docs/schema-compatibility.md): supported procedures and interoperability details.
- [Contributing](CONTRIBUTING.md): development setup, validation and submitting changes.
- [Live browser QA](docs/live-browser-qa.md): a supervised check of generated artifacts against BadgeApp.
- [Release procedure](docs/releasing.md): qualification, publication and release QA.
- [Release verification](docs/verification.md): verify downloaded assets, publisher identity, provenance and SBOMs, and understand the limits of these claims.
- [Roadmap](docs/roadmap.md): planned work and proposals under consideration.

## License

Original project code is copyright Reponomics and licensed under the [MIT License](LICENSE). Bundled upstream material has its own license and attribution requirements; see [Third-party notices](THIRD_PARTY_NOTICES.md). References to BadgeApp, OpenSSF and the Linux Foundation describe compatibility and attribution, not endorsement.
