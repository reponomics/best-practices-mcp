# Reference host removal audit

Audit date: 2026-11-15. Source baseline: main commit `252b16e` after removal of `prepare_update_script`. This is the implementation inventory for proposed [ADR 0004](adr/0004-remove-reference-host.md); the host has not yet been removed. Counts describe this baseline, not a coverage target.

## Code, tooling, and package surface

| Files or surface | Required disposition |
| --- | --- |
| `examples/host.py` (647 lines), `tests/test_host.py` (718 lines) | Delete after migrating the two server-relevant integration assertions below. The host is the only file in `examples/` and has no installed entry point. |
| `Makefile` | Remove `example`, `host`, `host-stored`, `test-host`, their phony declarations, and `examples` from Ruff commands/help. A nonexistent path must not break formatting or quality checks. |
| `.pre-commit-config.yaml` | Remove `examples` from the quality hook matcher. Keep the always-run offline suite, including documentation-only commits. |
| `MANIFEST.in` | Remove `recursive-include examples *.py`. The host is sdist content, not runtime wheel package data. Keep server catalog/provenance/license data. |
| `scripts/check_package.py` | Remove the required `/examples/host.py` archive member. Retain offline installed-wheel MCP discovery, catalog, license and network-barrier checks. |
| `scripts/release_check.py`, `tests/test_release_check.py` | Remove the exact-content host requirement from `verify_sdist`, host fixture setup/member, and `test_sdist_must_preserve_reference_host_and_project_notice` (its body only checks the host). Preserve project metadata and notice-integrity requirements and their tests. |
| `scripts/check_fresh_package.py` | Remove the host copy from `copy_probe_inputs`. Continue extracting `package_probe.py` and `tests/fixtures/read_server.py` from the candidate sdist. |
| `scripts/package_probe.py` | Remove the `host.py --discover` subprocess, its assertion, unused `subprocess` import, and `reference_host_discovery` result member. Retain `catalog_and_storage`, `synthetic_public_workflow`, installed entry-point checks, equivalent text/structured results, both draft-source modes and restart persistence. |
| `scripts/verification_support.py`, `tests/test_verification_support.py` | Remove the retired `examples` input category and `test_example_host_changes_change_fingerprint`. Retain general code/configuration, deletion, new-file and evidence freshness coverage. |
| `tests/fixtures/read_server.py` | Retain: direct-MCP and package tests share it. Prune any exclusively host-driven fixture branches only after tracing the surviving consumers. |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | Remove the reference host from product scope; retain questions about the user's actual MCP client. |
| `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `tests/test_fresh_package.py`, release/bundle/workflow tests | Existing jobs indirectly use the Make/probe paths above. Keep the six compatibility jobs and fresh wheel/sdist qualification. Check their results after removal; no new workflow or weakened gate is needed. |
| `scripts/release_bundle.py`, SBOM/OSV/attestation/verification machinery | No direct host dependency. Qualification consumes overall success and archive identities; no checked-in consumer requires `reference_host_discovery`. Keep the evidence and integrity checks. |
| `pyproject.toml`, `uv.lock`, dependency policies and notices | No host-exclusive dependency to remove. Standard-library imports need no inventory; `mcp` remains required. Keep pre-commit's `nodeenv` correction and generic `node_modules` exclusions. |
| `scripts/check_coverage.py`, `tests/test_ci_tooling.py` | Retain subprocess instrumentation: SDK-based subprocess tests survive. Record that the deferred AnyIO warning remains a separate cleanup. Coverage measures the server package, not the host. |

## Behavior and coverage mapping

| Behavior currently exercised by host tests | After removal |
| --- | --- |
| Search ambiguity, pagination, project-ID validation, observation metadata, public-read errors | Retain `test_read_tools.py::test_read_workflow_wire_results_and_catalog_schemas`, `test_badgeapp.py` search/identity/attribution tests, and `test_http.py` pacing/cooldown/bounds tests. Selection prompts and remembered selection retire; Inspector instructions require explicit resolution and selection. |
| Tool discovery, schemas, modern/legacy protocol, text fallback and structured errors | Retain `test_stdio.py`, `test_protocol.py`, `test_sdk_adapter.py`, contract suites and direct-MCP tests. Inspector provides an independent-client check. Defensive handling of hypothetical other servers in the custom host retires. |
| Caller-owned document editing/removal, validation, invalid patches, unknown JSON, size/Unicode/depth bounds | Retain `test_document_tools.py`, `test_drafts.py`, `test_documents.py`, and `test_validation.py`. The host's import-size policy, file dialogs and mutable session state retire. |
| Exact URL values, overrides, whitespace, optional validation | Retain `test_proposals.py` and `test_transfer_contract.py`; migrate the meaningful wire-level portion of `test_real_generation_without_validation_exports_exact_artifacts` into `test_document_tools.py`, as specified below. |
| Explicit versus omitted drafts, stored snapshots and subsets | Retain `test_storage_tools.py::test_stored_workflow_restart_explicit_precedence_and_stable_discovery`; migrate the concrete stored-subset scenario below. Inspector users supply their own explicit subset rather than relying on a new selector implementation. |
| Persistence, project isolation, rejected writes, missing/corrupt storage, startup without creation | Retain real-stdio tests in `test_storage_tools.py`, `test_stdio.py`, storage unit tests, and installed-package `catalog_and_storage`. These already cover restart and multiple project identities independently of the host. |
| Atomic replacement, cancellation/concurrency, post-commit errors and uncertain outcomes | Retain `test_storage.py` and `test_storage_tools.py::test_unexpected_post_commit_error_requires_read_before_retry`. Inspector is not a fault-injection substitute. Document read-before-retry; do not claim the client prevents retries. |
| UTF-8 file export, overwrite refusal, terminal parsing, host command recovery, cached-artifact invalidation | Retire with the interface. Keep server serialization and document parsing assertions; do not implement or test equivalent Inspector file-export/cache behavior. Warn users to use the latest successful result for the intended project/document. |
| Real-site field application, paired status/justification behavior, retention/clearing, whitespace and restoration | Preserve all six roles and both delivery paths in `live-browser-qa.md`. Inspector produces the exact artifact; authenticated Chrome demonstrates the site's behavior. No console entry or Save/Submit action. |

Two targeted migrations are sufficient on the audited baseline:

1. Extend the existing direct-MCP document workflow with `prepare_update_url` before any validation call, supplying a long Unicode justification with outer spaces and reserved URL characters and an explicit override. Assert exact decoded text, requested/effective override scope, schema validity, and equivalent structured/text results. This preserves server behavior without recreating file export.
2. Extend the existing direct-MCP storage workflow: read a complete snapshot, construct a selected explicit document retaining relevant identity fields, generate a URL, assert `draft_source.kind == "explicit"` and only selected transferable fields, then verify the full stored draft and file bytes are unchanged. No new client helper or subset abstraction is needed.

## Inspector and live-browser qualification

Keep the existing Inspector 2.14.0 pin for this slice. Its audited source is tag `2.14.0`, commit [`4d3464c`](https://github.com/modelcontextprotocol/inspector/tree/4d3464cb3a6dde609d7b5ac24c440b947eb40f23). The [CLI reference](https://github.com/modelcontextprotocol/inspector/blob/4d3464cb3a6dde609d7b5ac24c440b947eb40f23/clients/cli/README.md) documents discovery, calls and exact JSON arguments; the [configuration reference](https://github.com/modelcontextprotocol/inspector/blob/4d3464cb3a6dde609d7b5ac24c440b947eb40f23/docs/mcp-server-configuration.md) documents `-e` and modern protocol selection. Do not silently upgrade the Inspector while removing the host.

Document the following short maintainer procedure in the contributor/schema/browser-QA guides when implementing removal:

1. Use the exact installed candidate executable, outside the source checkout for package qualification. Record commit, artifact hash/version, interpreter, Inspector 2.14.0, Node version, OS, browser and date. Use the project's documented Node 24.22.3 minimum or a supported newer 24.x. No agent, model key, or BadgeApp credentials belong in Inspector.
2. Start Inspector in modern mode with an explicit disposable absolute `BESTPRACTICES_DATA_DIR`. The web UI is the preferred walkthrough route; the CLI supports repeatable discovery and individual calls. Use the existing Unix and PowerShell commands below as the launch pattern, substituting the actual installed executable and a fresh storage location. Stop it after QA and retain evidence without credentials.
3. Confirm exactly ten tools and inspect schemas/findings. Call `get_criteria` and `build_draft` offline; verify a small Unicode document and readable structured/text results. Exercise a known structured error, such as `read_draft` for a missing draft in the disposable root. Success exit status alone is not a field-value assertion; strict schema warnings also need inspection.
4. Resolve and explicitly select the intended existing project before application work. Exercise `update_draft`/`read_draft` with synthetic data in the disposable root, reconnect to the same root, and confirm the draft persists. Contrast validation with omitted `draft`, explicit `{}`, and a nonempty explicit draft. Use a second resolved project if demonstrating isolation manually; deterministic isolation coverage remains mandatory regardless.
5. For live proposal QA, follow the existing runbook's `build_draft` and `prepare_update_url` calls. Copy the complete returned draft/URL, not truncated visible text or the surrounding JSON envelope. Record A/B results and overrides. Click a link rendering the exact result for one route; paste the exact raw URL into the address bar for the other. If the Inspector UI does not render a link, record the actual rendering route used rather than claiming an Inspector link-click test.
6. Compare each selected control's baseline, both previews and restored state, with screenshots. Explain the intentional `?q=a&x=2#qa` test text beforehand. Check Unicode, punctuation and outer-space trimming separately from exact URL encoding. Discard previews, verify the plain form and perform the supplementary public read. Mark unavailable conditions unexercised, never silently passed.

Unix launch pattern (both paths are placeholders):

```sh
npx -y @modelcontextprotocol/inspector@2.14.0 --protocol-era modern -e BESTPRACTICES_DATA_DIR=/absolute/disposable/qa-drafts /absolute/candidate/bin/bestpractices-mcp
```

Windows PowerShell launch pattern:

```powershell
npx.cmd -y @modelcontextprotocol/inspector@2.14.0 --protocol-era modern -e "BESTPRACTICES_DATA_DIR=C:\mcp-qa\disposable-drafts" "C:\candidate\.venv\Scripts\bestpractices-mcp.exe"
```

For CLI discovery, add `--cli --method tools/list --strict --format json`. For tool calls, use the UI's structured input or the CLI's `--tool-args-json`; do not rely on shell-sensitive coercion for exact Unicode/JSON values. Windows complex-argument examples must be checked on Windows or use the UI rather than assuming Unix quoting works. Inspector is not a new required contributor dependency or default CI gate.

Audit-time feasibility check: on macOS with Node 24.22.3, Inspector 2.14.0 strict discovery against the source checkout returned all ten tools and no schema findings. A `build_draft` call preserved `Inspector audit ✨` in equivalent structured/text results. A `read_draft` call with the documented `-e` storage-root override returned the expected structured `draft_not_found` error and exit code 5 without creating storage. These checks validate the CLI approach only: they are not installed-release qualification, a Windows run, or an Inspector web-UI/live-browser run of the proposed procedure.

## Documentation changes and historical boundaries

Update `CONTRIBUTING.md` (setup, focused tests, stored workflow and Windows paths), `docs/architecture.md` (module and host sections), `docs/testing-policy.md`, `docs/releasing.md` (installed-candidate qualification), `docs/specification.md` (host reference and caller-selection wording), `docs/schema-compatibility.md`, `docs/live-browser-qa.md`, `docs/README.md`, and `docs/roadmap.md`. Keep the generic server storage/recovery and real-client configuration guidance. Inspector usability does not establish an agent's correct selection or interpretation of results.

Preserve the initial implementation plans, milestones, historical coverage numbers, QA records, and ADR 0003. Add a retirement link to the archived planning index and a current note to `docs/coverage-review.md` explaining that subprocess instrumentation still applies. No global replacement of the word “host”: most protocol and caller responsibilities refer to any MCP client and remain valid.

Before declaring removal complete, run the checks in ADR 0004, inspect both built archives, review the CI matrix, and retain exact-candidate Inspector/live-browser evidence with limitations. The two migrated assertions must pass before deleting their host versions. Keep any temporary removal audit out of the permanent test suite. Do not cut or publish a release as part of this work.
