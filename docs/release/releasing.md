# Releasing

This document is the maintainer procedure for publishing a release. [Versioning](versioning.md) says how the version number is chosen. [Verify a release](verification.md) tells a user how to check a published release. [CI](../maintenance/ci.md#security-practices) describes how the workflows are secured.

## The sequence

1. Release Please keeps a release pull request open on `main`. The pull request holds the version change and the release notes for the changes since the last release.
2. A maintainer reviews and merges the release pull request.
3. Release Please creates a draft GitHub release and the tag `vX.Y.Z` on the merge commit. It then starts the Publish to PyPI workflow at that tag.
4. The workflow builds, checks and scans a release candidate. It then waits for approval in the `pypi` environment.
5. A maintainer approves.
6. The workflow publishes the distributions to PyPI, attaches the release files to the GitHub release, and publishes the release.
7. The Verify published release workflow runs the commands of the verification guide against the published release.

## What the maintainer checks

Before merging the release pull request:

- The required checks pass.
- The version and the release notes match the changes.

Before approving the publication:

- The release commit shows as verified on GitHub.
- The build job passed, including both dependency scans.

After the publication:

- The Verify published release workflow passed.
- The package installs from PyPI with the commands in the [README](../../README.md), and the server starts.
- The manual checks pass. They are [Inspector qualification](../testing/inspector-qa.md) and the [live browser runbook](../testing/live-browser-qa.md). If one fails, fix the problem and publish a new version.

The live browser runbook is also run before a major change to the tools or to proposal URLs is released.

## The publication workflow

The workflow has four jobs. Each job has only the permissions that it needs.

| Job | What it does |
| --- | --- |
| Preflight | Finds the draft release for the tag and confirms that the draft, the tag and the prerelease flag agree. It does not check out code. |
| Build | Confirms that the tag, the version and the manifest agree and that the commit is on `main`. It runs the contributor checks, builds one wheel and one source distribution, and installs both in fresh environments. It produces SBOMs, runs the [dependency scans](../maintenance/dependencies.md#scanning) and assembles the candidate with checksums. |
| Publish | Waits for approval. It downloads the candidate, confirms its commit, tag, files and hashes, and creates signed provenance and SBOM attestations. It publishes the unchanged distributions to PyPI through trusted publishing. It does not check out or run project code. |
| GitHub release | Confirms the draft and the candidate again, attaches the files and publishes the release. |

The workflow stops if the tag has moved, if the release is missing or is not a draft, or if a scan reports a finding.

## What is published

PyPI receives the wheel and the source distribution with their attestations. The GitHub release receives the same two files, a checksum file, the release manifest, the qualification evidence, the scan reports, the SBOMs and the signed attestation bundles. [Verify a release](verification.md) describes each file and how to check it.

The scan reports show the state on the day of the release. The weekly scan continues to check the dependencies after that.

## Configuration

| Setting | Where | Purpose |
| --- | --- | --- |
| `RELEASE_APP_CLIENT_ID` | Repository variable | Identifies the GitHub App that Release Please uses |
| `RELEASE_APP_PRIVATE_KEY` | Repository secret | The private key of that App |
| `PYPI_PUBLISH_ENABLED` | Repository variable | Publication runs only when the value is `true` |
| `pypi` | GitHub environment | Requires approval from a maintainer and accepts only release tags |
| Trusted publisher | PyPI project settings | Names this repository, the workflow file `release.yml` and the environment `pypi` |
| Immutable releases | Repository settings | Protects the tag and the files of a published release |

The App has read and write access to the contents, issues and pull requests of this repository. The workflows use no PyPI token and no personal access token.

## When something fails

Publication to PyPI and publication on GitHub are separate steps. PyPI comes first, so a failed upload leaves a draft release.

- **PyPI succeeded and the GitHub release job failed.** Rerun only the failed job in the same workflow run. The run keeps its artifacts for 30 days.
- **The workflow at the tag needs a fix.** Merge the fix and publish a new version. Leave the failed candidate unpublished. Do not move its tag.
- **The workflow did not start after the release pull request merged.** Start it at the tag: `gh workflow run release.yml --ref vX.Y.Z -f tag=vX.Y.Z`.
- **A PyPI upload stopped partway.** Compare the files and hashes on PyPI with the candidate before you do anything else.

Never rebuild a version that is already published, and never replace its files. The project does not delete or yank a release automatically.

## Local candidate checks

These commands build and check a candidate locally. They publish nothing.

```sh
make check catalog-check lock-check
make release-build
make release-artifacts
make release-qualify
```

`make release-qualify` downloads dependencies. `make release-qualify RELEASE_SBOM=1` also produces the SBOMs, after `make release-evidence-setup`. The reports are written to `build/release/`, which Git ignores.
