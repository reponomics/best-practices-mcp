# Release procedure

This is an independent Reponomics project. It is not affiliated with, sponsored by, endorsed by, or an official project of OpenSSF, the Linux Foundation, or the OpenSSF Best Practices Badge (BadgeApp) project or its contributors. Upstream references and notices describe compatibility and provenance.

Release automation targets `reponomics/best-practices-mcp`. Prepare the repository privately and make it public immediately before the first release. Configure and verify GitHub CI, release approvals and PyPI Trusted Publishing before enabling publication.

This document is the maintainer runbook. Consumers should follow [Release verification](verification.md) for integrity and authenticity checks, expected identities, evidence scope and limitations.

## Repository setup

Use `main` as the default branch. Require pull requests, passing required checks and signed commits. Enable squash merging only, with the PR title as the default squash commit message. The `Semantic PR / Validate PR title` check validates Conventional Commit titles on PRs targeting `main`; it does not validate every intermediate branch commit. Squash-only merging and the PR-title default make the resulting main-branch history conventional. The deliberate empty `Initial commit` is the bootstrap exception.

Release Please creates the GitHub version tag and a draft release after its release PR is merged. A separate dispatch starts `release.yml` at that tag; successful qualification, approved PyPI publication and evidence attachment precede GitHub publication. Those tags are lightweight references to the signed release commit, not separately signed annotated tag objects. Enable GitHub immutable releases before the first release. This protects each published release’s tag and attached assets; it does not turn a lightweight tag into a signed annotated tag. No signing key or manual signing/tagging operation is added to the workflow. Require signed main-branch commits through repository rules and inspect the release commit's GitHub verification before approving publication.

Create or reuse a GitHub App installed only on the repositories it should release. For this repository grant repository Contents, Issues and Pull requests read/write permissions. Store its client ID as repository variable `RELEASE_APP_CLIENT_ID` and its private key as repository secret `RELEASE_APP_PRIVATE_KEY`. The workflow requests only those permissions and a repository-scoped short-lived token. Do not use a PAT. The App token lets Release Please's PRs run ordinary CI. A separate metadata-only dispatch job receives `actions: write` and starts `release.yml` at the candidate tag using `GITHUB_TOKEN`; explicit `workflow_dispatch` is an exception to ordinary token event suppression. The App needs no additional Actions permission. Draft release events do not trigger the candidate workflow automatically.

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

## Prepare and publish a candidate

Review the Release Please PR and all required checks before merging. The committed manifest records the last managed version; do not reset it or assume it is empty when preparing a subsequent beta. Release Please updates `pyproject.toml`, the local package version in `uv.lock`, the marked README installation-version block, `CHANGELOG.md` and the release manifest. Python metadata normalizes a version such as `0.2.0-beta.1` to `0.2.0b1`; the validator compares normalized versions while requiring the planned `vX.Y.Z` or `vX.Y.Z-beta.N` tag form.

The release configuration uses `draft: true` and `force-tag-creation: true`. After merging the release PR, Release Please creates the draft and its lightweight tag, then the dispatch job starts `release.yml` with both the workflow ref and its `tag` input set to that tag. The workflow refuses a mismatched ref, a missing/non-draft release, an unexpected prerelease flag or a moved tag. The existing PyPI registration remains `release.yml` with environment `pypi`; the environment's `v*` tag restriction remains applicable.

The release workflow has four jobs with separate permissions:

1. **Preflight:** a metadata-only job finds the exact tag in the paginated releases list and retrieves the draft by numeric release ID. GitHub’s release-by-tag endpoint returns published releases only. The job verifies the draft and Git tag separately, and carries the release ID through finalization so a replacement draft is rejected. GitHub draft visibility requires push access, so this job has `contents: write` but does not check out or execute project code.
2. **Build and evidence:** a read-only job validates tag/version/manifest/main ancestry, runs contributor checks, builds one wheel and one source archive, and qualifies those exact archives in fresh environments. It generates runtime-reference SBOMs, scans both the actual installation dependencies and the development/tooling inventories, and assembles a checksummed candidate bundle. Findings and scanner failures block publication; failed evidence is retained for investigation.
3. **Approved publication:** the `pypi` environment requires approval. This job downloads the candidate by its exact artifact ID, verifies its commit/tag, complete file set, sizes and hashes, generates signed build provenance and reference-SBOM attestations, then publishes the unchanged distributions to PyPI with Trusted Publishing and PyPI publish attestations. It has `contents: read`, `id-token: write` and `attestations: write`, and never checks out or executes project build code.
4. **GitHub finalization:** a separate `contents: write` job rechecks the draft/tag, verifies the same candidate and signatures, attaches the files, and publishes the draft. Matching previously uploaded assets can be retained on retry; conflicting assets fail rather than being overwritten. GitHub immutability protects the tag and assets after publication.

The candidate and signed bundles are retained as workflow artifacts for 30 days. GitHub release assets contain the wheel, source archive, `SHA256SUMS`, `release.json`, qualification evidence, vulnerability SARIF, separate license JSON, runtime-reference SBOMs and installation inventories, tooling SBOM, scan policy/lock inputs, and signed attestation bundles. `release.json` records the source commit, creation time, scanner version and file identities. Its paths describe the candidate bundle; published assets use unique flat filenames, and `SHA256SUMS` uses those downloadable filenames. Signatures are created afterward and are independently verified rather than included in that earlier checksum manifest. Release reports are dated assessments; scheduled OSV checks continue to detect later advisories.

Publishing to PyPI and GitHub is not atomic. PyPI publication precedes GitHub finalization so a failed package upload leaves a draft rather than a finalized GitHub release claiming successful publication. If PyPI succeeds and finalization fails, rerun only the failed GitHub job in the same workflow run while its artifacts are retained. Never rebuild and substitute different bytes for an already published version. If the tagged workflow itself needs a fix, merge the correction and prepare a new candidate version. Rerunning or redispatching the old tag still executes its old workflow; leave that failed candidate unpublished rather than moving its tag. If a PyPI upload partially succeeds, inspect the existing files and hashes before recovery; the workflow deliberately does not blanket-enable `skip-existing`.

For a draft whose dispatch failed before publication, a maintainer can explicitly start the candidate workflow at its tag:

```sh
gh workflow run release.yml --repo reponomics/best-practices-mcp --ref vX.Y.Z -f tag=vX.Y.Z
```

Replace both tag values with the same actual candidate tag. A dispatch on `main` with a tag supplied only as an input will not publish. Keep `PYPI_PUBLISH_ENABLED` disabled until the public repository, draft/tag process, required checks, environment approval and PyPI registration are ready. Do not create a published GitHub release manually to trigger this workflow.

## SBOM scope and verification

The non-default `release-tools` group pins CycloneDX Python in an isolated tool environment. It inspects each freshly installed wheel/source-archive environment without installing the SBOM generator there. Runtime SBOMs are validated CycloneDX JSON 1.6 and identify the candidate digest, source commit, platform, Python version and creation time. They describe reference installations, including explicitly identified environment bootstrap tooling; they are not claims that all dependencies are bundled in the archives or identical on every platform and future installation date.

Runtime OSV inventories come from pip's actual installation report, excluding the unpublished project root and avoiding unrelated bootstrap tooling. Public pip reports retain selected package identities and download hashes with local paths, credentials and URL queries removed. The separate tooling SBOM exports the uv/npm/actionlint inventory; Node and workflow tooling are not represented as MCP runtime dependencies. The Go standard-library version is checked separately for vulnerabilities. The release uses the same reviewed license policy as PR CI, including exact-version metadata corrections, the Docutils exception, and the permissive 0BSD allowlist entry used by release tooling.

Use the [consumer verification instructions](verification.md) after publication. Verify GitHub's immutable-release attestation and the local assets, the distributions' workflow provenance and SBOM attestations, and PyPI's publish attestations. Retain the release/run identity and verification results when recording release QA. Checksums alone are not authentication.

These controls support the project's OpenSSF Best Practices and OSPS Baseline evaluation goal. They do not establish a complete assessment or a SLSA Build Level 3 claim. Stronger reusable-builder isolation and contributor/reviewer governance remain separate workstreams.

### First verified publication

On 2026-11-15, [0.2.0-beta.3](https://github.com/reponomics/best-practices-mcp/releases/tag/v0.2.0-beta.3) completed [release run 43759677395, attempt 1](https://github.com/reponomics/best-practices-mcp/actions/runs/43759677395) at commit `b222cabb63cbd5d44475b965e44ee349eee161ef`. The maintainer approved the `pypi` deployment. All four release jobs succeeded, including qualification, vulnerability and license scans, attestation generation, PyPI publication and immutable GitHub finalization.

Post-publication checks verified all 31 downloaded asset digests, all 27 checksum-manifest entries, the GitHub release attestation, both distributions' workflow provenance, both signed runtime SBOMs and both PyPI publish attestations. The PyPI wheel and source archive matched the GitHub distribution hashes. This is a record for that release, not a substitute for verifying later releases or evidence that live browser QA has passed.

## Local candidate checks

Use the project venv and the locked Node development tooling. The commands below prepare and qualify files; none publishes anything:

```sh
make check catalog-check lock-check workflow-check
make release-build
make release-artifacts
make release-qualify
```

For release-reference SBOMs, additionally run `make release-evidence-setup` and `make release-qualify RELEASE_SBOM=1`. This uses the non-default tool environment and requires network access; it is not part of normal contributor validation. Release bundle assembly additionally requires successful scan reports and an actual candidate tag matching the checkout.

`release-build` requires a clean candidate distribution directory to avoid mixing old and new releases. `release-artifacts` checks metadata and records SHA-256 hashes. Its evidence also records the invoked GNU Make version under `toolchain.make`, or `unavailable` if detection fails, including in reports of failed candidate validation. Make orchestrates release assembly but is outside the current OSV dependency scan scope; see [ADR 0002](adr/0002-development-toolchain.md). `release-qualify` explicitly permits dependency downloads and tests the existing candidate archives without rebuilding them. Reports and sanitized logs stay under ignored `build/release/`.

For a tagged release checkout with the Release Please manifest already updated, source validation can be reproduced with:

```sh
make release-check RELEASE_ARGS='--tag v0.2.0-beta.1 --prerelease true --sha FULL_RELEASE_COMMIT_SHA'
```

The manifest must agree with the candidate tag and package version. A successful local build does not establish PyPI availability or the configured GitHub approval controls.

## Verify the published beta and advance to stable

Immediately after publication, verify fresh installation from production PyPI using the README's exact `uvx` and `pipx` commands. Check the normalized version, installed executable and actual MCP discovery/calls with a disposable data root; do not substitute a source-checkout or cached development install. Verify the reference-host instructions and retain the installed wheel/source archive identity in the release QA record. Then exercise the [local live browser runbook](live-browser-qa.md) against PolicyChecks silver using that published server. The first live browser check is deliberately deferred until after beta publication; record it as pending before then, not as passed or waived. It checks populated edit forms without saving the application.

Stable publication is conditional on published-package and live browser QA passing. Repeat the live browser check for subsequent release candidates, recording the exact candidate exercised. If a candidate changes after a successful check, assess the change and rerun affected cases before release. For the stable release PR, change the package configuration's `release-as` to the intended stable version (for example, `0.2.0` after the `0.2.0` beta series), set `prerelease` to `false`, and remove any prerelease versioning strategy if one was subsequently added. Use a release-worthy commit or the documented `Release-As: 0.2.0` commit footer if needed to produce the PR. Review the beta-to-stable diff and run the same gates. Release Please then creates a corresponding stable release (for example, `v0.2.0`); its wheel and sdist are rebuilt, qualified and approved separately. Beta artifacts are not renamed in place.

After stable release, remove the one-time `release-as` override so later Conventional Commits determine versions normally. Keep `prerelease: false` for ordinary releases. Verify unpinned stable installation as well as exact-version installation. If beta verification fails, hold stable publication, fix and retest; correct or withdraw misleading installation guidance promptly. No automatic deletion, yanking or overwriting of an existing PyPI release is performed.

[Release Please's manifest configuration](https://github.com/googleapis/release-please/blob/main/docs/manifest-releaser.md) documents empty bootstrap manifests, explicit release versions and removing `release-as` after use.
