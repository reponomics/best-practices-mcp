# Dependencies

This document states the policy for third-party packages and describes how the project adds, updates and scans them. GitHub Actions are covered in [CI](ci.md). The BadgeApp material that the repository vendors is covered in [upstream updates](upstream-updates.md).

## Policy

- The server keeps its runtime dependencies few. A new runtime dependency needs a purpose that the standard library and the existing dependencies do not meet.
- A dependency must have an upstream project that publishes releases and fixes security problems.
- The license of a dependency must be on the project's license allowlist. The allowlist holds licenses that are compatible with distributing this project under MIT.
- A dependency must have no known vulnerability when it is added. The scan in CI enforces this.
- Every runtime and development dependency is pinned to an exact version in `pyproject.toml`. `uv.lock` records every package that the pins resolve to, with hashes. The build backend is declared as a minimum version, and a release is built with the pinned version of the `dev` group.

## Groups

`pyproject.toml` is the source of truth for names and versions.

| Group | Purpose |
| --- | --- |
| `[project].dependencies` | The packages that a user installs with the server |
| `dev` | Tests, lint, type checks, build and packaging checks |
| `fuzz` | Atheris, for the [fuzz targets](../testing/fuzzing.md). It installs only on Linux. |
| `audit-tools` | The uv version that the project requires. The group exists so that the scans cover uv. |
| `release-tools` | The tool that produces the release SBOMs |
| `verification-tools` | The tool that verifies PyPI attestations |

`make setup` installs the runtime dependencies and the `dev` group into `.venv`. The other groups are installed only by the commands and workflows that need them.

## Adding or changing a dependency

1. Check the package against the policy above. Read its license file if the registry metadata is missing or unclear.
2. Edit `pyproject.toml` with an exact version.
3. Run `make lock`, then `make setup`, then `make validate`.
4. Commit `pyproject.toml` and `uv.lock` together. State the purpose of the dependency and its license in the pull request.

The reviewer reads the lockfile diff. A change can add packages that the pull request does not name.

## Upgrading uv

Use this checklist while the workflows contain explicit uv archive checksums. The examples use `0.13.10`; replace it with the version you are adopting.

1. Install that uv version locally and confirm it with `uv --version`. For a standalone installation, use `uv self update 0.13.10`; otherwise use the package manager that installed uv.
2. Update both `[tool.uv].required-version` and `audit-tools` in `pyproject.toml` to the same exact version. `make tooling-check` checks their agreement with the lockfile.
3. Open the three checksum URLs below, replacing `0.13.10` in each URL. Each response contains a 64-character SHA-256 digest followed by a filename. Copy only the digest, and cross-check it against the corresponding archive's digest on the [GitHub release](https://github.com/astral-sh/uv/releases/tag/0.13.10), also replacing the version in that URL.
4. Paste the three digests into the matching `uv-checksum` entries in [ci.yml](../../.github/workflows/ci.yml). Paste the Linux digest into `checksum` in [fuzz.yml](../../.github/workflows/fuzz.yml), [osv-scanner.yml](../../.github/workflows/osv-scanner.yml), [release.yml](../../.github/workflows/release.yml), [upstream-criteria.yml](../../.github/workflows/upstream-criteria.yml), and [verify-release.yml](../../.github/workflows/verify-release.yml). Update the nearby version comments. Keep `require-checksums: true`.
5. Run `make lock`, `make setup`, and `make validate`, in that order. Review the lockfile for unrelated upgrades, commit the pins, lockfile, and workflow changes together, and require the platform matrix and dependency scans to pass before merging.

The checksum URL follows this pattern:

```text
https://releases.astral.sh/github/uv/releases/download/<version>/<archive>.sha256
```

| CI platform | Checksum URL for uv 0.13.10 |
| --- | --- |
| Linux x64 | [uv-x86_64-unknown-linux-gnu.tar.gz.sha256](https://releases.astral.sh/github/uv/releases/download/0.13.10/uv-x86_64-unknown-linux-gnu.tar.gz.sha256) |
| macOS ARM64 | [uv-aarch64-apple-darwin.tar.gz.sha256](https://releases.astral.sh/github/uv/releases/download/0.13.10/uv-aarch64-apple-darwin.tar.gz.sha256) |
| Windows x64 | [uv-x86_64-pc-windows-msvc.zip.sha256](https://releases.astral.sh/github/uv/releases/download/0.13.10/uv-x86_64-pc-windows-msvc.zip.sha256) |

These hashes verify the executable archives downloaded by `setup-uv`; they are different from the PyPI distribution hashes in `uv.lock`.

### When to retire the manual checksums

The explicit hashes bridge a release-timing gap: `setup-uv` v10.4.0 does not bundle checksums for uv 0.13.10. Retire steps 3–4 once a released `setup-uv` version includes checksums for the chosen uv version on all three CI platforms. Confirm the entries in that action release's [`src/download/checksum/known-checksums.json`](https://github.com/astral-sh/setup-uv/blob/v10.4.0/src/download/checksum/known-checksums.json), replacing `v10.4.0` in the link with the candidate action release.

In one PR, pin that action release by its full commit SHA in all six workflows, remove their explicit `checksum` inputs and the checksum-only `matrix.include` entries in `ci.yml`, and retain `version-file: pyproject.toml` and `require-checksums: true`. Require the platform matrix to pass before merging. Then simplify this checklist to updating the uv pins, regenerating the lockfile, and validating; the action maintains the checksum table. Future uv upgrades must still use an action release that knows the chosen version's checksums. If it has not caught up, wait or temporarily restore explicit hashes. Updating the action alone does not change the uv version.

## Updates

Dependabot opens pull requests for new versions each week, for the Python packages and for the GitHub Actions. `.github/dependabot.yml` holds the configuration. It groups minor and patch updates of Python packages into one pull request and opens a separate pull request for each major update. It groups the updates of actions into one pull request. It also opens a pull request when a security advisory affects a dependency.

Each update goes through the same checks as any other change.

## Scanning

The OSV dependency scan workflow runs on every pull request, on every push to `main`, and once a week. It runs two scans against `uv.lock`:

- A vulnerability scan against the OSV database.
- A license check against the allowlist.

The scans read the exact versions in the lockfile and resolve nothing else. A finding or a scanner error fails the job, and a pull request cannot merge while the job fails.

The release workflow repeats both scans. It also scans the packages that a fresh installation of the wheel and of the source distribution resolves. A finding or a scanner error stops the publication.

The weekly run can report a vulnerability in a dependency that the project already uses. [SECURITY.md](../../SECURITY.md#dependency-and-code-scanning-findings) states how quickly the project fixes a finding of each severity and how a finding may be suppressed.

To run the scans locally, install OSV-Scanner at the version that the workflow uses and run `make -k scan-vulnerabilities scan-licenses`.

## License allowlist

The allowlist is the `OSV_LICENSES` value in the `Makefile`. The OSV workflow and the release workflow each carry a copy of the same list. Change all three together.

Registry metadata is sometimes missing or does not use a standard license identifier. `osv-scanner.toml` holds a correction for each such package. A correction applies to one exact version and records the evidence for the license. When Dependabot updates the package, the correction no longer applies and the license must be checked again.

`osv-scanner.toml` also holds one exception, for Docutils. It is a development-only dependency of Twine and is not distributed with the server.

Corrections and exceptions affect only the license check. They never hide a vulnerability finding.

The maintainers reassess the allowlist and the corrections from time to time, and when the set of dependencies changes substantially. A license can stay on the allowlist while no current package uses it.
