# Best Practices MCP

## Description

Best Practices MCP lets an MCP-compatible assistant look up projects on the OpenSSF Best Practices Badge website (BadgeApp), inspect badge criteria and progress, prepare draft answers, and generate proposed updates for review in the browser.

The server provides the tools; your assistant decides how to assess the project and organize the work. It can prepare an edit-page URL or a guarded form-fill script, but does not authenticate to BadgeApp or save changes. You review the actual form before deciding to save.

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
      "args": ["--from", "best-practices-mcp==0.1.1-beta.1", "bestpractices-mcp"]
    }
  }
}
```

This lets the host launch an isolated installation from PyPI. Alternatively, install persistently with `pipx install 'best-practices-mcp==0.1.1-beta.1'` and configure the host to launch the installed `bestpractices-mcp` executable with no arguments.
<!-- x-release-please-end -->

Use an absolute executable path if the host cannot find `uvx` or `bestpractices-mcp` on its PATH. On Windows, JSON paths need escaped backslashes, for example `C:\Users\you` must be written as `"C:\\Users\\you"`. The package name is **`best-practices-mcp`**; the executable name is **`bestpractices-mcp`**.

Reload the host's MCP connections, then try a request such as:

> Find the BadgeApp project for https://github.com/reponomics/PolicyChecks and show its silver-level progress. Do not prepare any changes yet.

The host should discover nine tools. Starting the executable directly in a terminal waits for MCP messages; it is not an interactive CLI. For a source checkout or connection debugging with Inspector, see [Contributing](CONTRIBUTING.md).

## Tools

| Tool | What it does | Network or storage effects |
| --- | --- | --- |
| `find_project` | Find public project candidates by ID, repository/homepage URL, or text; the host selects the intended project. | Public BadgeApp GETs |
| `get_criteria` | Read the bundled criteria by badge level and criterion. | Offline |
| `get_project_progress` | Read a project's saved answers and progress, with source and fetch time. | Public BadgeApp GETs |
| `build_draft` | Create or patch a document supplied by the host. | Offline; no stored files changed |
| `read_draft` | Read the complete locally stored draft for a project. | Local read |
| `update_draft` | Create or patch a locally stored project draft. | Local write; no BadgeApp update |
| `validate_draft` | Check supplied answers against the bundled criteria's mechanical requirements. | Offline; may read a stored draft |
| `prepare_update_url` | Generate a proposed edit-page URL and report included/excluded fields. | Public BadgeApp GETs; no remote write |
| `prepare_update_script` | Generate a guarded browser form-fill script and report included/excluded fields. | Public BadgeApp GETs; does not execute the script |

See the [tool specification](docs/specification.md) and [payload contracts](docs/contracts.md) for arguments, results and errors.

## Usage notes

- **Compatibility:** Python 3.11 is the supported minimum. The CI compatibility matrix targets Python 3.11/3.12 on Linux, macOS and Windows. The protocol baseline is MCP `2026-07-28`; transport is stdio. Node and Ruby are not required to run the server.
- **Catalog and language:** criteria are bundled from a pinned upstream revision, not fetched live. The current catalog is English and generated edit links use English paths. Translation support is [proposed](docs/roadmap.md#proposed).
- **Validation is advisory:** it checks mechanical requirements, not whether claims are true or evidence is sufficient. Validation is optional and does not gate artifact generation.
- **Review in the browser:** artifacts include eligible supplied fields even when they match saved values. Reports describe what was included or excluded, not what BadgeApp will retain or save. BadgeApp documents trimming leading/trailing whitespace from URL-proposed justifications. See [transfer rules](docs/transfer-rules.md) for overrides and script behavior.
- **Authentication stays in your browser:** public reads need no BadgeApp credentials. Applying proposals requires your own authenticated session and appropriate project permissions. The console script is a project-provided fallback, not an upstream-supported API.

### Optional draft storage

A host can keep drafts itself and pass them explicitly, or use one server-stored `.bestpractices.json` per project across badge levels. For validation and artifact generation, an explicit document, including `{}`, bypasses storage; omitting it reads the selected project's stored draft. Only `update_draft` writes files.

Default storage locations are:

| Platform | Data directory |
| --- | --- |
| macOS | `~/Library/Application Support/bestpractices-mcp` |
| Linux | `$XDG_DATA_HOME/bestpractices-mcp` when XDG is absolute; otherwise `~/.local/share/bestpractices-mcp` |
| Windows | `%LOCALAPPDATA%/bestpractices-mcp` |

To choose another location, set `BESTPRACTICES_DATA_DIR` in the server's environment through your MCP host. Use an absolute path; `~` is not expanded. Avoid simultaneous writers from separate server processes or external editors to the same project draft. After an uncertain update result, use `read_draft` before deciding whether to issue another patch. See [persistence boundaries](docs/architecture.md#optional-local-persistence).

## Documentation

- [Documentation index](docs/README.md): the complete guide to maintained documentation and historical records.
- [Design](docs/design.md) and [architecture](docs/architecture.md): responsibilities, data flow and the human-review boundary.
- [Specification](docs/specification.md) and [contracts](docs/contracts.md): tool behavior, exact payloads and operational limits.
- [Upstream compatibility](docs/upstream-compatibility.md), [transfer rules](docs/transfer-rules.md) and [schema compatibility](docs/schema-compatibility.md): supported procedures and interoperability details.
- [Contributing](CONTRIBUTING.md): development setup, tests, Inspector, native Windows commands and package verification.
- [Live browser QA](docs/live-browser-qa.md): a supervised check of generated artifacts against BadgeApp.
- [Release procedure](docs/releasing.md): qualification, publication and release QA.
- [Roadmap](docs/roadmap.md): planned work and proposals under consideration.

## License

Original project code is copyright Reponomics and licensed under the [MIT License](LICENSE). Bundled upstream material has its own license and attribution requirements; see [Third-party notices](THIRD_PARTY_NOTICES.md). References to BadgeApp, OpenSSF and the Linux Foundation describe compatibility and attribution, not endorsement.
