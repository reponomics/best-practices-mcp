# Inspector qualification

MCP Inspector is an optional tool for contributors who want to explore the server or debug client compatibility. Ordinary contributions require the [automated validation](../../CONTRIBUTING.md#validate-the-implementation), not this walkthrough. Maintainers use the qualification checklist below for relevant release candidates and stable promotion, alongside the [release procedure](../release/releasing.md).

## Launch Inspector

After `make setup`, install Node **24.22.3 or a newer supported 24.x**. On Unix with nvm, use `nvm install 24` and `nvm use 24`; Windows can use a native Node installation. Node is needed only for Inspector, not project setup, automated tests, or default CI. Inspector **2.14.0** is external to the project's locked dependencies and OSV scans.

Launch the local web UI with a disposable absolute storage root. On macOS/Linux:

```sh
QA_ROOT="$(mktemp -d)"
npx -y @modelcontextprotocol/inspector@2.14.0 --protocol-era modern -e "BESTPRACTICES_DATA_DIR=$QA_ROOT" ./.venv/bin/bestpractices-mcp
```

On Windows PowerShell:

```powershell
$qaRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("bestpractices-qa-" + [guid]::NewGuid())
npx.cmd -y @modelcontextprotocol/inspector@2.14.0 --protocol-era modern -e "BESTPRACTICES_DATA_DIR=$qaRoot" .\.venv\Scripts\bestpractices-mcp.exe
```

Keep the UI local and reuse the same disposable root for reconnect checks. No model key, agent, or BadgeApp credentials are needed by Inspector. Public project reads and URL preparation contact BadgeApp; local document and catalog checks are offline. Only `update_draft` writes local drafts. For authenticated form checks, use the separate [browser runbook](live-browser-qa.md).

## Qualify an installed candidate

For release qualification, substitute the absolute executable from the exact installed wheel or sdist outside the source checkout. Record the distribution hash/version, commit when known, executable/interpreter identity, Inspector/Node versions, OS, browser and date under `INTERNAL/live-qa/<candidate>/`. Retain tool arguments/results and exact generated URLs without credentials. A development-checkout session is useful for debugging but does not qualify release artifacts.

## Short tool walkthrough

In the web UI, connect over stdio and inspect the ten tools and their input/output schemas. Confirm the server version and negotiated protocol (`2026-07-28` in modern mode). General catalog access and synthetic document checks below are offline. Before project-specific work, use `find_project` and explicitly select the intended existing entry; confirm its repository identity with `get_project_status`. An empty search requires registration outside the server, not an invented project ID. The server has no active-project selection session.

| Check | Calls and expected observations |
| --- | --- |
| Catalog and explicit document | `get_criteria` with `{}` summarizes six levels; with `{"level":"passing"}` it returns the criterion index. An invalid argument such as `{"level":"bronze"}` returns `invalid_arguments` with the allowed levels. `build_draft` with `{"draft":{},"changes":{"name":"Inspector QA ✨"}}` returns that exact document. Inspect both structured output and its JSON text fallback. |
| Expected error | After project selection, `read_draft` for its ID in a fresh disposable root returns the structured `draft_not_found` error. Confirm the error code; a disconnected client or malformed request is not a successful negative test. |
| Stored draft and reconnect | `update_draft` with the selected `project_id` and `changes: {"description_good_justification":"Inspector QA ✨"}` creates a synthetic local draft. Read it, disconnect/reconnect to the same root, and read it again. Confirm the complete draft is preserved. Do not run concurrent writers against that root. |
| Omitted versus explicit document | Call `validate_draft` with the selected ID and `section: "passing"`, first omitting `draft`, then with `draft: {}`, then with a nonempty explicit document. Check `draft_source.kind` and validation results. `{}` bypasses storage; omitted `draft` reads it. Findings are not operational errors and do not prevent proposal generation. |
| URL and explicit subset | The [browser runbook](live-browser-qa.md)'s script generates the proposal URLs for live QA. Here, build a small document with `build_draft` and supply the returned `draft` explicitly to `prepare_update_url`. For a stored subset, first read the complete draft, construct the desired explicit document while retaining relevant identity fields, generate, and read again to confirm the stored document was not replaced by the subset. |
| Resources | In the Resources view, the list holds `criteria://levels`, one document per level and per level category, and `guide://repository-file`; three templates are listed. Read `criteria://levels` and a category document as Markdown. After the stored-draft check, refresh the list and confirm that `project://<project_id>/<level>` appears for each of the six levels, then read one. A template URI such as `criteria://silver/dco` is readable without being listed. |

Inspector retains earlier responses, so use the latest successful result for the selected project/document. After an uncertain write outcome, call `read_draft` before deciding whether another update is needed.

When copying a URL from Inspector, take the complete `artifact.url` string without JSON quotes, escaping, or truncation. Check `transfer`, `overrides`, and `effective_overrides`; investigate unexpected exclusions or `artifact: null` before proceeding. The browser runbook checks delivery and actual form behavior without saving.

## Repeatable CLI checks

For a discovery check without the UI, run from a development checkout on macOS/Linux:

```sh
npx -y @modelcontextprotocol/inspector@2.14.0 --cli --protocol-era modern --connect-timeout 15000 ./.venv/bin/bestpractices-mcp --method tools/list --strict --format json
```

Windows PowerShell equivalent:

```powershell
npx.cmd -y @modelcontextprotocol/inspector@2.14.0 --cli --protocol-era modern --connect-timeout 15000 .\.venv\Scripts\bestpractices-mcp.exe --method tools/list --strict --format json
```

For qualification, substitute the installed candidate's absolute executable. `--method initialize` reports server identity, capabilities, and negotiated protocol. Discovery should return the ten documented tool names. Inspect `schemaFindings` alongside `result`: warnings leave the exit status unchanged, while error-severity portability findings exit with code 6. See [schema compatibility](../reference/schema-compatibility.md) for the expected schemas and interpretation of findings.

A Unix shell example of an offline typed call is:

```sh
npx -y @modelcontextprotocol/inspector@2.14.0 --cli --protocol-era modern --connect-timeout 15000 ./.venv/bin/bestpractices-mcp --method tools/call --tool-name build_draft --tool-args-json '{"draft":{},"changes":{"name":"Inspector QA ✨"}}' --format json
```

Assert the returned `result.structuredContent.draft` and its equivalent JSON text, not only exit status. Use `--tool-args-json` for exact typed arguments; `--tool-arg key=value` can coerce a JSON-looking string into another type. For complex JSON on Windows, use the UI's structured input unless the command's argument handling has been verified with the installed PowerShell version. Add `-e "BESTPRACTICES_DATA_DIR=ABSOLUTE_DISPOSABLE_PATH"` for storage calls, using the disposable root created above.

Keep JSON stdout separate from diagnostic stderr and preserve the CLI exit status before parsing output. An expected tool refusal requires exit code 5 and the intended structured error. Each CLI invocation creates a new connection; sequential calls with the same disposable root check persistence across restarts. Use the UI or automated MCP tests for same-session behavior.

The pinned upstream [CLI smoke-testing guide](https://github.com/modelcontextprotocol/inspector/blob/4d3464cb3a6dde609d7b5ac24c440b947eb40f23/docs/cli-smoke-testing.md), [CLI reference](https://github.com/modelcontextprotocol/inspector/blob/4d3464cb3a6dde609d7b5ac24c440b947eb40f23/clients/cli/README.md), and [server configuration](https://github.com/modelcontextprotocol/inspector/blob/4d3464cb3a6dde609d7b5ac24c440b947eb40f23/docs/mcp-server-configuration.md) document the Inspector commands.

## Completion

For qualification, record each check as passed, failed, or unexercised, with candidate identity and the platforms and interfaces tested. Complete the separate [live-browser runbook](live-browser-qa.md) for proposal application. Stop Inspector before deleting the disposable QA directory, and retain the qualification evidence.
