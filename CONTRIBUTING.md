# Contributing

Report bugs and propose improvements through [GitHub Issues](https://github.com/reponomics/best-practices-mcp/issues). Discuss non-trivial changes in an issue before implementing them, and follow the [Code of Conduct](CODE_OF_CONDUCT.md). For installation and everyday use, see the [README](README.md).

## Local development

Install GNU Make. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) at the version specified by `[tool.uv].required-version` in [pyproject.toml](pyproject.toml). Python defaults to the version in [.python-version](.python-version), currently 3.11; uv can install it if needed. On Windows, use native Make and uv from PowerShell; CI installs Make with `choco install make --version=4.4.1 --yes`.

From the repository root:

```sh
make setup
make help
```

`make setup` installs the editable project and locked development dependencies into `.venv`. Activation is unnecessary. Prefer Make targets for repeated operations; `make help` lists the available commands. Synchronization removes unselected packages, so keep unrelated tools outside this environment. Node is needed only for the optional Inspector workflow.

To test another Python version without changing the main environment:

```sh
make setup VENV=build/python-3.12 BOOTSTRAP_PYTHON=3.12
make check VENV=build/python-3.12 BOOTSTRAP_PYTHON=3.12
```

Pass the same overrides to subsequent Make commands. If using uv directly with a custom environment, set `UV_PROJECT_ENVIRONMENT` to that path. Save source files with LF endings; [.gitattributes](.gitattributes) defines the repository's line-ending rules.

## Validate the implementation

Run this before submitting a PR:

```sh
make validate
```

This checks the lockfile, formatting and lint, types, offline tests and catalog reproduction. It returns a failing status if any check fails.

Use focused checks while developing and additional package checks when relevant:

| Command | Purpose |
| --- | --- |
| `make test` | Offline unit and MCP integration tests |
| `make typecheck` | mypy in strict mode over the server package and scripts, with a relaxed profile for tests |
| `make test-coverage` | Server coverage, including MCP subprocesses; reports in `build/coverage/` |
| `make test-package` | Build and inspect distributions and test an isolated installed wheel with existing dependencies |
| `make check-fresh-package` | Install wheel and sdist in fresh environments; permits dependency downloads and writes results to `build/verification/` |

Add or update tests for changed behavior. The [testing policy](docs/testing-policy.md) defines contract and compatibility expectations. CI runs the Python 3.11/3.12 matrix on Linux, macOS and Windows, plus dependency and security checks; see [CI documentation](docs/ci.md).

For optional commit-time checks, run `make setup-hooks` once per clone. Hooks use the development environment; rerun `make setup` after dependency changes. The offline suite runs on every commit, including documentation changes. `make pre-commit-check` runs all hooks against tracked files.

Inspector and live-browser checks are **not required for ordinary contributions**. Maintainers use the [Inspector guide](docs/inspector-qa.md) and [browser runbook](docs/live-browser-qa.md) for release qualification as described in the [release procedure](docs/releasing.md).

For optional Linux fuzzing of document parsing and proposal URLs, see the [fuzzing guide](docs/fuzzing.md).

## Dependencies

Dependency changes must use licenses compatible with the project's MIT distribution and intended use, and pass CI's OSV vulnerability and license checks. Include the dependency's purpose and license evidence in the PR. Changes to license exceptions require review.

After editing the dependency declarations:

```sh
make lock
make setup
make validate
```

Review and commit both the manifest and lockfile changes. The [dependency inventory](docs/ci.md#dependency-inventory) explains the scanned groups, policy, and tooling pins. OSV runs in CI; installing it locally is optional. See [local dependency scans](docs/ci.md#optional-local-dependency-scans) if you want to run it before pushing.

## Connect a host to a development checkout

After `make setup`, configure your MCP host to launch the checkout's absolute executable path:

```json
{
  "mcpServers": {
    "bestpractices": {
      "command": "/absolute/path/to/best-practices-mcp/.venv/bin/bestpractices-mcp"
    }
  }
}
```

On Windows, use `.venv\Scripts\bestpractices-mcp.exe` and escape backslashes in JSON. Starting the executable without arguments waits for MCP messages; `--help` and `--version` provide CLI information. Keep stdout reserved for protocol traffic and send diagnostics to stderr.

Use a disposable absolute `BESTPRACTICES_DATA_DIR` for manual storage tests. The [README](README.md#optional-draft-storage) describes storage configuration. For interactive debugging without an assistant, follow the optional [Inspector setup](docs/inspector-qa.md#launch-inspector).

## Submit a pull request

Keep changes focused, describe their effect, and report the validation performed and any checks left unrun. Include relevant tests and documentation.

Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) for commit messages and the PR title. Sign commits so GitHub can mark them **Verified**; see [GitHub's signing guide](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification).

Contributions must comply with the [Developer Certificate of Origin](docs/DCO.txt). Use `git commit --signoff` to record your certification with a `Signed-off-by` trailer. A trailer is not mandatory on every commit; do not ask an agent to certify changes on your behalf before you have reviewed or approved them. DCO signoff and cryptographic commit signing are separate.

## Specialized work

- [Upstream maintenance](docs/upstream-compatibility.md#checking-for-upstream-changes): compare and refresh the bundled BadgeApp sources.
- [CI and dependency tooling](docs/ci.md): workflow behavior, scanner policy and toolchain updates.
- [Release procedure](docs/releasing.md): package qualification and publication.
- [Documentation index](docs/README.md): architecture, contracts and other reference material.
