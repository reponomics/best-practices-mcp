# Release procedure

This is an independent Reponomics project. It is not affiliated with, sponsored by, endorsed by, or an official project of OpenSSF, the Linux Foundation, or the OpenSSF Best Practices Badge (BadgeApp) project or its contributors. Upstream references and notices describe compatibility and provenance.

Release automation targets `reponomics/best-practices-mcp`. Prepare the repository privately and make it public immediately before the first release. Configure and verify GitHub CI, release approvals and PyPI Trusted Publishing before enabling publication.

## Repository setup

Use `main` as the default branch. Require pull requests, passing required checks and signed commits. Enable squash merging only, with the PR title as the default squash commit message. The `Semantic PR / Validate PR title` check validates Conventional Commit titles on PRs targeting `main`; it does not validate every intermediate branch commit. Squash-only merging and the PR-title default make the resulting main-branch history conventional. The deliberate empty `Initial commit` is the bootstrap exception.

Release Please creates the GitHub version tag and release automatically after its release PR is merged. Those tags are lightweight references to the signed release commit, not separately signed annotated tag objects. Enable GitHub immutable releases before the first release. This protects each published release’s tag and attached assets; it does not turn a lightweight tag into a signed annotated tag. No signing key or manual signing/tagging operation is added to the workflow. Require signed main-branch commits through repository rules and inspect the release commit's GitHub verification before approving publication.

Create or reuse a GitHub App installed only on the repositories it should release. For this repository grant repository Contents, Issues and Pull requests read/write permissions. Store its client ID as repository variable `RELEASE_APP_CLIENT_ID` and its private key as repository secret `RELEASE_APP_PRIVATE_KEY`. The workflow requests only those permissions and a repository-scoped short-lived token. Do not use a PAT. The App token lets Release Please's PRs run ordinary CI and its published release event trigger the publishing workflow; events created with `GITHUB_TOKEN` generally do not trigger those workflows.

Configure the `pypi` environment with the designated privileged reviewer. Self-approval is permitted; leave “Prevent self-review” disabled. Required environment reviewers for this plan become available when the repository is public; verify the actual rules before the first release. Restrict the environment to release tags and retain its approval gate for beta and stable uploads.

| Setting | Location | Meaning |
| --- | --- | --- |
| `RELEASE_APP_CLIENT_ID` | Repository variable | Release Please GitHub App client ID |
| `RELEASE_APP_PRIVATE_KEY` | Repository secret | That App's private key |
| `PYPI_PUBLISH_ENABLED=true` | Repository variable | Explicit readiness switch for publication; leave unset until release preparation is approved |
| `pypi` | GitHub environment | Required publication approval and Trusted Publisher environment identity |

Enable the status checks documented in [CI and maintenance](ci.md). Release Please and publication jobs are release operations, not required PR checks. Do not enable a second CodeQL default setup alongside the checked-in advanced workflow. Codecov uses its GitHub integration and OIDC; it is unrelated to the release App and requires no PyPI credential.

## PyPI Trusted Publisher

Configure the pending publisher through the authenticated PyPI UI, with `hesreallyhim` as the expected owning account. Enter these exact GitHub identity fields:

| Field | Value |
| --- | --- |
| PyPI project | `best-practices-mcp` |
| GitHub repository owner | `reponomics` |
| Repository name | `best-practices-mcp` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

`release-please.yml` is the release manager, but **`release.yml` is the PyPI uploader**. Do not register the former as the Trusted Publisher. No PyPI API token is stored. A pending publisher does not reserve the package name. See [PyPI's pending-publisher setup](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) and [OIDC publication guidance](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## First beta

The checked-in empty Release Please manifest `{}` means no release has been recorded. The bootstrap configuration explicitly requests `0.1.0-beta.1` and marks its GitHub release as a prerelease. The clean project snapshot should use a release-worthy conventional commit such as `feat: bootstrap BadgeApp MCP server`, so the initial release PR has meaningful changes to collect.

Release Please updates `pyproject.toml`, the local package version in `uv.lock`, the marked installation-version block in README, `CHANGELOG.md` and the release manifest. The Python metadata normalizes `0.1.0-beta.1` to `0.1.0b1`; both spellings identify the same version. Keep the managed README pins in SemVer spelling so the generic updater replaces the complete beta suffix. The validation script compares normalized Python versions while requiring the planned tag form `v0.1.0-beta.1`.

Review the release PR and its required CI before merging. Check version alignment, notices, release notes and the selected source/documentation tree. Change repository visibility to public, verify the environment reviewer, register the pending publisher, and enable `PYPI_PUBLISH_ENABLED` before merging the release PR that should publish. Do not merge the release PR first and assume changing the readiness variable later will replay its event.

On merge, Release Please records the released version in the manifest and creates the version tag and GitHub prerelease. The `release.published` event triggers `release.yml` for both prereleases and stable releases. The workflow verifies the release flag, package version, manifest, checked-out SHA and tag ancestry on `main`; runs required tests and catalog/lock checks; builds one wheel and one source distribution; checks metadata/README rendering and exact notices; and installs those exact archives into fresh environments for CLI, eleven-tool MCP and reference-host probes.

The distribution artifact is uploaded only after those checks pass. A separate job waits for `pypi` approval, downloads that same workflow run's immutable artifact, and publishes using OIDC with attestations. The PyPI archives are built after the GitHub release event and are not attached to that immutable GitHub release; PyPI publishing attestations provide their separate provenance. Do not append assets to an already immutable GitHub release. Exact candidate hashes establish which bytes were qualified and uploaded, not bit-for-bit reproducibility across independent builds. The publishing job does not check out or execute project build code. Workflow permissions are read-only by default; only that upload job receives `id-token: write`.

## Local candidate checks

Use the project venv and the locked Node development tooling. The commands below prepare and qualify files; none publishes anything:

```sh
make check catalog-check lock-check workflow-check
make release-build
make release-artifacts
make release-qualify
```

`release-build` requires a clean candidate distribution directory to avoid mixing old and new releases. `release-artifacts` checks metadata and records SHA-256 hashes. `release-qualify` explicitly permits dependency downloads and tests the existing candidate archives without rebuilding them. Reports and sanitized logs stay under ignored `build/release/`.

For a tagged release checkout with the Release Please manifest already updated, source validation can be reproduced with:

```sh
make release-check RELEASE_ARGS='--tag v0.1.0-beta.1 --prerelease true --sha FULL_RELEASE_COMMIT_SHA'
```

The initial empty manifest intentionally fails this publication-identity check until Release Please has prepared the release. A successful local build does not establish PyPI availability or the configured GitHub approval controls.

## Verify the published beta and advance to stable

Immediately after publication, verify fresh installation from production PyPI using the README's exact `uvx` and `pipx` commands. Check the normalized version, installed executable and actual MCP discovery/calls with a disposable data root; do not substitute a source-checkout or cached development install. Verify the reference-host instructions and retain the installed wheel/source archive identity in the release QA record. Then exercise the [local live browser runbook](live-browser-qa.md) against PolicyChecks silver using that published server. The first live browser check is deliberately deferred until after beta publication; record it as pending before then, not as passed or waived. It checks populated edit forms without saving the application.

Stable publication is conditional on published-package and live browser QA passing. Repeat the live browser check for subsequent release candidates, recording the exact candidate exercised. If a candidate changes after a successful check, assess the change and rerun affected cases before release. For the stable release PR, change the package configuration's `release-as` to `0.1.0`, set `prerelease` to `false`, and remove any prerelease versioning strategy if one was subsequently added. Use a release-worthy commit or the documented `Release-As: 0.1.0` commit footer if needed to produce the PR. Review the beta-to-stable diff and run the same gates. Release Please then creates a new `v0.1.0` release; its wheel and sdist are rebuilt, qualified and approved separately. Beta artifacts are not renamed in place.

After stable release, remove the one-time `release-as` override so later Conventional Commits determine versions normally. Keep `prerelease: false` for ordinary releases. Verify unpinned stable installation as well as exact-version installation. If beta verification fails, hold stable publication, fix and retest; correct or withdraw misleading installation guidance promptly. No automatic deletion, yanking or overwriting of an existing PyPI release is performed.

[Release Please's manifest configuration](https://github.com/googleapis/release-please/blob/main/docs/manifest-releaser.md) documents empty bootstrap manifests, explicit release versions and removing `release-as` after use.
