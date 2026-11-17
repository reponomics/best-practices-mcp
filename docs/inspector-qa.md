# Inspector qualification

Use MCP Inspector for independent-client checks and exploratory tool calls. This is optional for ordinary contributors and a maintainer check for relevant release candidates and stable promotion. It supplements the automated MCP and installed-package suites; it does not replace storage failure, cancellation, atomicity, exact serialization, or protocol regressions. [ADR 0004](adr/0004-remove-reference-host.md) explains the reference-host removal.

## Candidate and setup

Follow the [Inspector launch instructions](../CONTRIBUTING.md#inspect-the-implemented-tools), including Inspector **2.14.0**, Node **24.22.3 or a newer supported 24.x**, modern protocol mode, and an explicit disposable absolute `BESTPRACTICES_DATA_DIR`. Keep the Inspector web UI local. No agent, model key, or BadgeApp authentication belongs in Inspector; authenticate only in the BadgeApp browser when performing live QA. Inspector is an external tool, not part of this project's locked dependencies, OSV scans, or release attestations.

For package qualification, use the absolute executable from the exact installed wheel or sdist, outside the source checkout, rather than a development editable installation. Record the distribution hash/version, commit when known, executable/interpreter identity, Inspector/Node versions, OS, browser and date under `INTERNAL/live-qa/<candidate>/`. Retain tool arguments/results and the exact generated URLs without credentials. Identify source-checkout checks as such; they do not qualify published bytes. Reconnect to the same disposable root when checking persistence; never substitute the normal user draft directory.

## Short tool walkthrough

In the web UI, connect over stdio and inspect the ten tools and their input/output schemas. Confirm the server version and negotiated protocol (`2026-07-28` in modern mode). General catalog access and synthetic document checks below are offline. Before project-specific work, use `find_project` and explicitly select the intended existing entry; confirm its repository identity with `get_project_progress`. An empty search requires registration outside the server, not an invented project ID. The server has no active-project selection session.

| Check | Calls and expected observations |
| --- | --- |
| Catalog and explicit document | `get_criteria` with `{}` lists six levels. `build_draft` with `{"draft":{},"changes":{"name":"Inspector QA ✨"}}` returns that exact document. Inspect both structured output and its JSON text fallback. |
| Expected error | After project selection, `read_draft` for its ID in a fresh disposable root returns the structured `draft_not_found` error. Confirm the error code; a disconnected client or malformed request is not a successful negative test. |
| Stored draft and reconnect | `update_draft` with the selected `project_id` and `changes: {"description_good_justification":"Inspector QA ✨"}` creates a synthetic local draft. Read it, disconnect/reconnect to the same root, and read it again. Confirm the complete draft is preserved. Do not run concurrent writers against that root. |
| Omitted versus explicit document | Call `validate_draft` with the selected ID and `section: "passing"`, first omitting `draft`, then with `draft: {}`, then with a nonempty explicit document. Check `draft_source.kind` and validation results. `{}` bypasses storage; omitted `draft` reads it. Findings are not operational errors and do not prevent proposal generation. |
| URL and explicit subset | For live QA, use the document and selected criteria from the [browser runbook](live-browser-qa.md). Supply the returned `draft` explicitly to `prepare_update_url`. For a stored subset, first read the complete draft, construct the desired explicit document while retaining relevant identity fields, generate, and read again to confirm the stored document was not replaced by the subset. |

Use only the latest successful result for the selected project/document. Inspector can retain old responses; it does not enforce the retired host's cached-result policy. On a timeout, lost response, or uncertain write error, call `read_draft` before deciding whether another update is needed. There is no automatic client rollback or guaranteed retry prevention.

Treat `artifact.url` as the exact artifact. Copy its complete string, not surrounding JSON quotes, an escaped JSON representation, truncated display text, or a reconstructed link. Check `transfer`, `overrides`, and `effective_overrides`. Do not edit the URL to work around an unexpected exclusion or `artifact: null`; investigate the result. The browser runbook tests two delivery routes, chooser forwarding, override-all, and the observed unknown-reset failure without saving. Discovery must require `section` on validation/preparation and expose the three override modes; verify success schema version 2 and shared error version 1. Missing section and contradictory mode/field combinations must fail input validation. Unknown-only proposals must retain `?` and return the same nonblocking warning as validation.

## Repeatable CLI checks

The CLI is useful for recorded assertions without opening the Inspector UI. From a development checkout on macOS/Linux, a discovery check is:

```sh
npx -y @modelcontextprotocol/inspector@2.14.0 --cli --protocol-era modern --connect-timeout 15000 ./.venv/bin/bestpractices-mcp --method tools/list --strict --format json
```

Windows PowerShell equivalent:

```powershell
npx.cmd -y @modelcontextprotocol/inspector@2.14.0 --cli --protocol-era modern --connect-timeout 15000 .\.venv\Scripts\bestpractices-mcp.exe --method tools/list --strict --format json
```

For candidate qualification, substitute the installed candidate's absolute executable. `--method initialize` can be used first to inspect server identity, capabilities, and negotiated protocol without invoking a tool. Discovery should return exactly the ten documented tool names, not merely a count. Check the optional `schemaFindings` array as well as `result`: warnings do not fail the process, while error-severity portability findings exit with code 6. A schema portability finding is not automatically an MCP conformance violation.

A Unix shell example of an offline typed call is:

```sh
npx -y @modelcontextprotocol/inspector@2.14.0 --cli --protocol-era modern --connect-timeout 15000 ./.venv/bin/bestpractices-mcp --method tools/call --tool-name build_draft --tool-args-json '{"draft":{},"changes":{"name":"Inspector QA ✨"}}' --format json
```

Assert the returned `result.structuredContent.draft` and its equivalent JSON text, not only exit status. Use `--tool-args-json` for exact typed arguments; `--tool-arg key=value` can coerce a JSON-looking string into another type. For complex JSON on Windows, use the UI's structured input unless the command's argument handling has been verified with the installed PowerShell version. Add `-e "BESTPRACTICES_DATA_DIR=ABSOLUTE_DISPOSABLE_PATH"` for storage calls, as in the contributor examples.

When recording scripted checks, keep JSON stdout separate from diagnostic stderr, set a bounded connection timeout, and retain the CLI's exit status before parsing output. An expected tool refusal requires exit code 5 and the intended structured error; an arbitrary nonzero exit is insufficient. Do not let a successful formatter or pipeline hide a failed command. Each CLI invocation creates a new connection, so sequential calls with the same data root can check persistence across server restarts; same-session behavior remains covered by automated MCP tests or the UI. No OAuth or remote transport configuration is needed for this stdio server.

The pinned upstream [CLI smoke-testing guide](https://github.com/modelcontextprotocol/inspector/blob/4d3464cb3a6dde609d7b5ac24c440b947eb40f23/docs/cli-smoke-testing.md), [CLI reference](https://github.com/modelcontextprotocol/inspector/blob/4d3464cb3a6dde609d7b5ac24c440b947eb40f23/clients/cli/README.md), and [server configuration](https://github.com/modelcontextprotocol/inspector/blob/4d3464cb3a6dde609d7b5ac24c440b947eb40f23/docs/mcp-server-configuration.md) describe these behaviors. Its HTTP/OAuth and MCP App examples are outside this project's stdio tool surface; do not copy that infrastructure into the qualification procedure.

## Completion

Record each exercised check as passed, failed, or unexercised. Include exact candidate identity and limitations: CLI-only results do not establish UI usability, a macOS run does not establish Windows command compatibility, and a smoke check does not establish agent behavior. Complete the separate live-browser matrix for actual proposal application, then stop Inspector and retain the evidence. Delete only the disposable QA storage when no longer needed. No package release or website save is part of this procedure.
