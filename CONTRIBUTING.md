# Contributing

Thank you for contributing to this project. We strongly encourage contributions, and there are many ways to get involved. If you wish to suggest a feature enhancement, or report any issues with the software or its documentation, visit the [Issues](https://github.com/reponomics/best-practices-mcp/issues) page. Before making any non-trivial code changes, please propose the changes in an issue.

All contributors who interact with this repository must respect the [Code of Conduct](CODE_OF_CONDUCT.md).

This document covers development, local MCP connections, verification and maintainer tooling. For package installation and everyday use, start with the [README](README.md). See the [roadmap](docs/roadmap.md) for planned work and proposals.

## Git Standards

### Commit Messages

Please use [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/) when committing code for this repo. Include a brief statement of the changes in the imperative mood, and an optional body, usually not more than a paragraph. Coding agents should avoid long, discursive commentary in the commit body.

### Commit Signing

Please ensure that your commits are signed and appear as "Verified" on GitHub. See GitHub [docs](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification) for guidance. This is required and enforced on Pull Requests.

### Commit Signoff - DCO

By contributing code to this project, you must agree to the [Developer Certificate of Origin (DCO) version 1.1](./docs/DCO.txt). This is a confirmation that you have the right to submit the code changes that you propose. To make this explicit, please include a `Signed-off-by: NAME <EMAIL ADDRESS>` trailer in your commits, which you can do simply by adding the `--signoff` flag (or `-s`) when running `git commit`, i.e., `git commit --signoff`. This is not a strict requirement for every commit, and coding agents should not be instructed to include a signoff on your behalf for changes that you have not reviewed or approved.

## Local Development

Local development defaults to Python **3.11**, the lowest supported minor version, as recorded in [`.python-version`](.python-version). [`pyproject.toml`](pyproject.toml) retains `requires-python = ">=3.11"` for package compatibility and Ruff's `py311` target. The local interpreter preference does not restrict users to Python 3.11.

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) independently of the project environment, using the exact version in `[tool.uv].required-version` in [`pyproject.toml`](pyproject.toml), currently **0.13.8**. uv is required for contributor setup and lock maintenance; it is not required to run the installed server. `uv --version` checks the executable on your `PATH`; `UV=/path/to/uv` overrides it for Make.

Install GNU Make. On macOS, Make is available with the command-line developer tools; on Linux, use the distribution's package manager. On Windows, one supported route is `choco install make --version=4.4.1 --yes` from an elevated PowerShell with [Chocolatey](https://community.chocolatey.org/packages/make/4.4.1) already installed. Reopen the terminal if needed to refresh `PATH`. Use native Windows Python/uv with native Make; Git Bash and WSL are not prerequisites.

The repository's [`.gitattributes`](.gitattributes) keeps text files at LF line endings on every platform, including Windows with `core.autocrlf=true`. Vendored upstream files and the copied upstream license are exempt from conversion because their exact bytes are checked. Save source files with LF endings in your editor; no global Git setting change is required. For an older Windows checkout already containing CRLF files, commit or stash your work and use a fresh clone to apply the policy without overwriting local edits.

The same commands work from a Unix shell or Windows PowerShell:

```sh
make help
make setup
make check
make build
```

`make help` reads the Makefile's annotated targets through a small Python helper and works before project setup. uv can supply Python if necessary. `make setup` uses `uv sync --locked --group dev --no-group audit-tools` to create or synchronize `.venv`, installing this package in editable mode and the development dependencies from [`uv.lock`](uv.lock). `.python-version` supplies the interpreter preference; `--locked` fails if metadata and the lock disagree. Synchronization removes unselected packages, so keep unrelated tools in separate environments. pip is an explicit development dependency for offline package installation checks.

The default environment is `.venv`, matching uv’s project default. Make selects `.venv/bin/python` or `.venv/Scripts/python.exe`; activation is unnecessary. Direct `uv sync` and `uv run` use the same environment without an extra environment variable. Prefer the Make targets for repeated operations. Make exports `UV_PROJECT_ENVIRONMENT` from `VENV`, so custom environments remain supported: pass the same `VENV` override to each Make command, and set `UV_PROJECT_ENVIRONMENT` to that path when using uv directly.

Override `BOOTSTRAP_PYTHON` to test another interpreter, preferably in a separate environment: `make setup VENV=venv-3.12 BOOTSTRAP_PYTHON=3.12`, followed by `make check VENV=venv-3.12 BOOTSTRAP_PYTHON=3.12`. Add custom environment directories to your local Git excludes. Paths containing spaces can be passed as one quoted argument, for example `make setup "VENV=build/dev venv"`. Overrides do not edit `.python-version` or narrow the universal lock.

For an existing checkout, stop processes using the development environment and deactivate it before migration. `make setup` synchronizes the selected environment and may replace it when the requested interpreter differs; it does not preserve manually installed packages. To recreate it explicitly, remove only the selected disposable environment directory and run `make setup` again. Do not edit `pyvenv.cfg` to switch interpreters.

If migrating from the previous `venv` default, recreate the environment with `make setup` instead of renaming it. Clear any old `VENV` or `UV_PROJECT_ENVIRONMENT` shell overrides first (`unset VENV UV_PROJECT_ENVIRONMENT` on Unix; `Remove-Item Env:VENV, Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue` in PowerShell). Update editor interpreter selections, MCP host paths and any installed Git hooks (`make setup-hooks`) to use `.venv`. Remove the old `venv` only after its users have switched; Make does not remove it automatically.

`pyproject.toml` declares runtime dependencies and the installed `dev` dependency group. The non-default `audit-tools` group records uv for OSV scanning without installing uv inside its own managed environment. A separate non-default `inventory-tools` group supplies CI’s YAML parser for actionlint inventory generation. The non-default `release-tools` group pins CycloneDX Python for release-reference SBOMs in its own environment. The non-default `verification-tools` group pins PyPI attestation verification tooling for the read-only post-release check. Normal setup does not install these groups; their dependencies remain in the lockfile scanned by OSV. `make tooling-check` rejects drift between the uv inventory, the lock and uv's required version. There is no `.tool-versions` or asdf prerequisite. See [ADR 0002](docs/adr/0002-development-toolchain.md) for the decision and alternatives.

After changing dependencies, run `make lock`, review the diff, then run `make setup` and the validation commands below. To update uv, change both its exact `required-version` and its `audit-tools` requirement, install that external uv version, then regenerate the lock. `make lock-check` verifies consistency without changing the lock. Fresh-consumer checks still install through pip without the development lock to exercise ordinary package installation.

Use your MCP client or the optional [Inspector workflow](#inspect-the-implemented-tools) to exercise the server interactively. The reference terminal host was removed under [ADR 0004](docs/adr/0004-remove-reference-host.md).

Required tests follow documented upstream procedures, criteria YAML and agreed MCP compatibility rules. A locally supervised live browser check tests actual proposal-URL compatibility. See the [testing policy](docs/testing-policy.md) for authority and traceability.

The installed CLI supports these commands on macOS/Linux:

```sh
.venv/bin/bestpractices-mcp --help
.venv/bin/bestpractices-mcp --version
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\bestpractices-mcp.exe --help
.\.venv\Scripts\bestpractices-mcp.exe --version
```

Running it without arguments starts the stdio server and waits for an MCP host. Protocol traffic uses stdout; diagnostics must use stderr.

## Validate the implementation

From the repository root after `make setup`:

```sh
make validate
make test-package
make check-fresh-package
```

`make validate` checks lock consistency, runs quality checks and the offline test suite with coverage enforcement, verifies the catalog, and lints workflows. It continues with independent checks after a failure and exits nonzero if any check fails. It does not run OSV or require OSV-Scanner to be installed; dependency scans run in CI. Individual targets remain available for focused work, including `make check` for quality checks and tests. Coverage reports are written under `build/coverage/`; fresh-package results and sanitized logs are written under `build/verification/`. The [release procedure](docs/releasing.md) covers exact candidate qualification, publication controls and published-package QA.

Workflow lint tentatively uses the [kjanat/actionlint fork](https://github.com/kjanat/actionlint), pinned to v1.17.1 by full commit SHA in `.pre-commit-config.yaml`, built with Go 1.27.4. The separate [Actionlint workflow](.github/workflows/actionlint.yml) uses the same source and toolchain pins. `make setup` installs pre-commit in `.venv`; `make workflow-check` (also included in `make validate`) checks all tracked workflows without a separate actionlint installation. Stage new workflow files with `git add` before checking them. The first run needs network access to download the pinned Go toolchain and build and cache actionlint; contributors do not need to install Go separately, including on Windows. Later runs reuse the cached environment.

To optionally run checks automatically when committing, run `make setup-hooks` once per clone after `make setup`. Hooks use the existing locked environment and Make targets; run setup again after dependency changes. The offline test suite runs on every commit, including documentation-only changes, because tests may assert documentation content. Other hooks select relevant staged filenames:

| Hook | When it runs |
| --- | --- |
| Python quality | Python source, tests, scripts, or Python/tooling configuration changes |
| Lock consistency | Python manifest, lockfile, bootstrap configuration, or tooling helper changes |
| Catalog reproduction | Vendored inputs, packaged catalog, generator, or relevant tooling configuration changes |
| Offline tests | Every commit, including documentation-only changes |
| Actionlint | YAML files under `.github/workflows/` change |

The offline suite takes roughly a minute and includes MCP subprocess tests; it never runs the live BadgeApp browser test or live smoke checks. OSV scans and fresh-package downloads are not commit hooks. `make pre-commit-check` runs all configured hooks against tracked files; `make workflow-check` explicitly checks all tracked workflows. Git hook installation remains optional and is not required for `make validate`.

Dependabot checks the actionlint hook revision weekly and proposes updates to its SHA and version comment together. When accepting an update, also update the source SHA and release version in `.github/workflows/actionlint.yml`; keep the hook’s `language_version`, that workflow’s `GO_VERSION`, and the OSV workflow’s Go version in agreement. CI rejects mismatched pins. Keep the `# frozen: v1.17.1`-style comment so hook updates follow release tags. CI generates and retains the executable module inventory for both OSV scans, and a separate Go standard-library inventory for vulnerability scanning. Contributors do not generate these inventories or maintain Go dependency files. This fork selection is tentative; review its maintenance and compatibility before changing releases, especially when moving to v2.

`make test-storage`, `make test-documents`, and `make test-upstream` select focused storage, document and transfer tests from the ordinary offline suite. `make smoke-live PROJECT_ID=1` separately checks public GET compatibility; it never saves anything or establishes the deployed upstream revision.

For live-form QA, follow the brief [PolicyChecks browser runbook](docs/live-browser-qa.md): resolve the intended project and level, authenticate in the browser, inspect the actual form baseline, then review the generated proposal URLs in the form without saving. Its first execution follows beta publication and gates stable promotion; repeat it for subsequent release candidates. Compare retention, overrides, paired fields and exact text before discarding the previews. The [recorded Chrome cases](docs/live-qa/2026-11-09/README.md) provide examples. Artifact reports identify included and excluded fields; they do not predict the form's effects or saved values. Eligible supplied fields are always included, even when equal to the public record. A user may delegate browser actions to a host agent; the MCP itself never saves. A later `get_project_progress` call reports saved observations separately. The URL interface follows upstream recommendations.

`make catalog-check` verifies byte-for-byte regeneration from vendored inputs. `make test-package` checks the distribution contents and an isolated installed wheel using the current environment's dependencies. Fresh-install qualification separately installs wheel and sdist into new environments.

`make upstream-check` compares all retained BadgeApp sources against `production` using public network reads, without editing files or GitHub. `make upstream-prepare` prepares source, catalog and documentation-reference changes locally. The weekly/manual workflow maintains one regular update PR; labels are advisory and every update requires review and passing CI. Follow the [upstream update procedure](docs/upstream-compatibility.md#checking-for-upstream-changes), including pausing automation before making manual fixes on its reserved branch.

## Dependencies

Any proposed change that introduces or updates a direct or transitive dependency must use a license compatible with this project's MIT-licensed distribution and intended use, and must pass the OSV vulnerability and license checks in CI. This applies to runtime, development, build and audit dependencies in `uv.lock`, plus actionlint and the modules imported by its executable, derived from the pinned hook revision in CI. Include the dependency's purpose and available license evidence in the pull request. Contributors may use their preferred tools to assess a dependency or wait for the PR workflow results; installing or running OSV-Scanner locally is not required. Routine contributor validation does not recheck dependency licenses.

Update the Python manifest and lockfile with `make lock`, synchronize the development environment, and run `make validate`. The [OSV workflow](.github/workflows/osv-scanner.yml) enforces the license allowlist; [`osv-scanner.toml`](osv-scanner.toml) records version-specific third-party metadata corrections and the approved Docutils development-tool exception. Its first-party MIT override has no version restriction because unpublished release candidates have no registry license metadata; `make tooling-check` verifies it against this checkout’s project metadata and local lock entry. These license entries do not suppress vulnerability checks. There is no actionlint vulnerability exception: the fork updates the affected Windows dependency, and building from source with Go 1.27.4 avoids the older toolchain in its published v1.17.1 binaries. Release-time scans additionally check the actual dependencies resolved for the qualified wheel and source archive. The allowlist includes 0BSD for release tooling; Arrow and Defusedxml have exact-version corrections verified against their published licenses. New licenses or changes to exceptions require review, and an OSI-approved license is not automatically on the allowlist. See [CI documentation](docs/ci.md#dependency-inventory) for scan scope and retained reports.

### Optional local dependency scans

Maintainers and contributors who want proactive checks can install [OSV-Scanner](https://google.github.io/osv-scanner/installation/) using the version pinned in the workflow. Put it on `PATH`, or pass `OSV_SCANNER=/path/to/osv-scanner` to Make, then run from the repository root:

```sh
make -k scan-vulnerabilities scan-licenses
```

These optional local checks contact OSV and deps.dev and use the committed Python lockfile and repository policy. They do not generate or scan the CI-only actionlint inventory; inspect the PR workflow reports for that coverage. Both scans are attempted even if one fails, and any failure produces a nonzero exit status. Results are written to the ignored files `osv-scanner.sarif` and `osv-licenses.json`; inspect `license_violations` in the JSON for license-policy findings. Investigate unknown metadata against the dependency's license files and document any justified policy correction or exception.

## Source installation and native Windows commands

Python 3.11 is the supported minimum targeted by the compatibility matrix. Use an isolated environment; the assessed project does not need to use Python. From this checkout, a runtime-only installation on macOS/Linux is:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m best_practices_mcp --version
```

The native PowerShell equivalents for a runtime-only installation are:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m best_practices_mcp --version
```

For development and QA on Windows, use the same Make targets documented above from PowerShell. CI exercises native Make with `cmd.exe` recipes, including an environment path containing spaces.

Coverage measures server-package statements and branches, including Python MCP subprocesses. `make test-coverage` and `make validate` require at least 95% statement coverage and 95% branch coverage independently, using unrounded counts. The Make variable `COVERAGE_MINIMUM` sets this shared floor. A temporary hook in the development venv forwards only Coverage.py's process configuration through the SDK's filtered environment; it is removed after collection and does not modify production code. `make test-coverage` writes `build/coverage/html/index.html`, XML/JSON reports and a summary with commit/environment details and gate results, retaining reports when coverage falls below the floor. For focused diagnostic measurements without the full-suite floor, invoke `.venv/bin/python scripts/check_coverage.py tests/test_read_tools.py` directly (on Windows, use `.venv\Scripts\python.exe`). Coverage percentages complement behavioral assertions; they do not establish that uncovered paths are safe. CI retains the reports for each matrix combination.

`make check-fresh-package` explicitly permits dependency downloads and creates fresh temporary environments for wheel and sdist installation outside the checkout. It does not reuse the development environment's dependencies. Use `make test-package` for the offline package check. Dependency installation requires network access unless the required packages are cached; runtime fixture checks are offline.

## Connect a host to a development checkout

After `make setup`, use the absolute executable path in the host's MCP configuration:

```json
{
  "mcpServers": {
    "bestpractices": {
      "command": "/absolute/path/to/best-practices-mcp/.venv/bin/bestpractices-mcp"
    }
  }
}
```

On Windows, use an absolute `.venv\Scripts\bestpractices-mcp.exe` path (escape backslashes in JSON), or configure `.venv\Scripts\python.exe` with arguments `["-m", "best_practices_mcp"]`.

The baseline is MCP `2026-07-28` with official Python SDK `2.3.0`. `BESTPRACTICES_DATA_DIR` optionally supplies an absolute server-local data root. Unset selects `~/Library/Application Support/bestpractices-mcp` on macOS, `$XDG_DATA_HOME/bestpractices-mcp` (absolute XDG only) or `~/.local/share/bestpractices-mcp` on Linux, and `%LOCALAPPDATA%/bestpractices-mcp` on Windows. Empty/relative overrides and existing nondirectory roots fail at startup; `~` is not expanded in overrides. Startup and read-only/document-only workflows create no storage.

Only `update_draft` writes `<root>/projects/<project_id>/.bestpractices.json`. Each project has one multi-level draft. An explicit document, including `{}`, bypasses stored files; an omitted document reads the selected project at call time. Complete reads retain unfamiliar JSON and report structural diagnostics. Updates validate source identity before patching and check full read/update result budgets before atomic replacement. New drafts use owner-only permissions where supported; existing permissions are preserved.

Updates within one server process use per-project guards. Separate servers and external editors are not coordinated: avoid simultaneous writers to the same project/root. Atomic replacement prevents partial files, not lost updates between independent writers or sudden-power-loss guarantees. Cancellation or a lost response can leave an uncertain outcome; use `read_draft` to inspect before deciding on another patch. The server never retries the mutation automatically.

Automated tests and package probes use temporary storage, never the normal draft directory. Inspector checks should likewise use a disposable root as shown below.

## Inspect the implemented tools

MCP Inspector 2.14.0 provides an independent client for this stdio server. After setup, launch its web UI with a disposable absolute storage root. No model, agent, or BadgeApp credentials are needed by Inspector.

On macOS/Linux:

```sh
QA_ROOT="$(mktemp -d)"
npx -y @modelcontextprotocol/inspector@2.14.0 --protocol-era modern -e "BESTPRACTICES_DATA_DIR=$QA_ROOT" ./.venv/bin/bestpractices-mcp
```

On Windows PowerShell, use `npx.cmd` and the Windows server executable:

```powershell
$qaRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("bestpractices-qa-" + [guid]::NewGuid())
npx.cmd -y @modelcontextprotocol/inspector@2.14.0 --protocol-era modern -e "BESTPRACTICES_DATA_DIR=$qaRoot" .\.venv\Scripts\bestpractices-mcp.exe
```

Keep the same disposable root when testing a reconnect. Stop the server before removing that QA directory. For a custom environment, substitute its executable; for release qualification, use the absolute executable of the exact installed candidate outside the source checkout.

Only this optional Inspector workflow requires Node/npm. Install Node 24.22.3 or a newer supported 24.x version; on Unix with nvm, use `nvm install 24` and `nvm use 24`, or install Node directly on Windows. Node is not required for project setup, automated tests, pre-commit, or default CI. Inspector is external to this project's dependency inventory and OSV scans.

Discovery, `get_criteria`, `build_draft`, `read_draft`, `update_draft`, and `validate_draft` are offline; only `update_draft` writes local drafts. Public project/badge reads and `prepare_update_url` contact BadgeApp. No tool authenticates or submits changes. Resolve and explicitly select the intended project before application work. Inspector may retain old results: use the latest successful result for that project and draft, and read the draft before deciding whether to retry an uncertain write.

Follow [Inspector qualification](docs/inspector-qa.md) for the short tool-call walkthrough, exact result handling, and CLI smoke checks. It is a maintainer qualification step for relevant release candidates and stable promotion; ordinary contributors need only the automated validation above. The [schema guide](docs/schema-compatibility.md) explains portability findings, and [live browser QA](docs/live-browser-qa.md) checks actual proposal application without saving.
