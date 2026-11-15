# ADR 0002: One Make interface and a locked uv development environment

Status: Accepted. Date: 2026-11-14.

## Context

Contributors need a straightforward workflow on Linux, macOS and native Windows, with reproducible dependencies and an auditable inventory. Previously, Make and Windows instructions duplicated commands, CI installed dependencies separately through pip, and `.tool-versions` recorded a uv pin without an asdf integration. These paths could drift.

## Decision

Keep GNU Make as the canonical task interface. Most recipes already invoke Python; centralize platform-specific executable paths and environment exports, quote paths, and move the small shell-dependent help, executable-resolution and distribution-globbing operations into a standard-library Python helper. Help continues to come from Makefile annotations. Windows uses native GNU Make with `cmd.exe` recipes, launched from PowerShell; it does not require Git Bash or WSL. CI exercises the same Make targets on all three operating systems, with environment paths containing spaces.

Use `.venv` by default so Make and direct uv project commands share an environment without contributor-specific configuration. Retain the `VENV` override for CI and custom environments. Use an independently installed, exactly pinned uv to create and synchronize the standard `.venv` directory from `uv.lock`. `.python-version` selects Python 3.11, the minimum supported minor version; CI also tests 3.12. The package's Python compatibility declaration remains separate from this development preference. Install development tools from a `dev` dependency group rather than publishing them as a package extra. Node 24.22.3 or newer within 24.x and `package-lock.json` remain limited to DOM development tests. `.nvmrc` selects the exact Node version for local setup and CI.

Declare uv's executable requirement in `[tool.uv].required-version`, which uv enforces and `setup-uv` reads in CI. Remove `.tool-versions`; no asdf integration is needed. Include the matching uv distribution in a non-default `audit-tools` dependency group so OSV sees its version in `uv.lock` without installing a second uv into the environment. A consistency check rejects disagreement between the executable requirement, audit group and lock. Updating uv requires updating both declarations, regenerating the lock, and updating the external executable.

OSV scans the committed Python and npm locks without implicit resolution. This covers the recorded package versions, including uv; it does not attest to every locally installed executable or inventory the whole operating-system toolchain. Fresh wheel/sdist checks continue using pip in clean environments, exercising consumer installation independently of the development lock. Server users need neither Make nor uv.

Make is part of the release toolchain: it orchestrates builds through Python's `build` frontend and the setuptools backend, but consumers do not need Make to build or install the package. CI environment evidence and release candidate evidence record the invoked GNU Make version, including when a custom executable is used. Windows installation remains pinned to 4.4.1; Linux and macOS use their platform-provided Make. GNU Make is outside the current OSV scan scope. Version recording provides traceability, not vulnerability coverage; adding that coverage would require a suitable system-package or toolchain inventory rather than a Python dependency entry.

## Alternatives considered

- Keep pip/venv for development and uv only for scanning: leaves separate resolution paths and an unnecessary contributor distinction between setup and lock maintenance.
- Replace uv with compiled requirements files: viable, but adds lock-generation conventions and platform/interpreter handling without simplifying this existing universal lock.
- Maintain Make plus separate Windows commands: duplicates task definitions and invites drift.
- Adopt just, Task or Poe: viable task runners, but migration adds another tool or dependency without much benefit for these mostly Python recipes. Just also requires deliberate shell configuration on Windows. Reconsider if Make's platform branches grow substantially.
- Require a Unix compatibility environment on Windows: avoids some recipe changes but adds a larger prerequisite than native Make.

## Consequences and verification

Contributors install uv and GNU Make separately; Python can be supplied by uv. They use the same documented Make commands on each platform. The tradeoff is a small platform branch and a Python helper, maintained through focused tests and the six-job OS/Python CI matrix. Local checks alone cannot establish Windows support. Release builds share the locked setup and Make qualification targets; publication permissions and approval gates remain separate.

References: [uv dependency groups](https://docs.astral.sh/uv/concepts/dependencies/#dependency-groups), [uv required version](https://docs.astral.sh/uv/reference/settings/#required-version), [GNU Make shell selection](https://www.gnu.org/software/make/manual/html_node/Choosing-the-Shell.html), [OSV supported lockfiles](https://google.github.io/osv-scanner/supported-languages-and-lockfiles/).
