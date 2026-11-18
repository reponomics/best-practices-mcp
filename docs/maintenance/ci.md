# Continuous integration

This document lists the GitHub Actions workflows, says which of them a pull request must pass, and describes how the workflows are secured and maintained. It also describes the checks that a contributor runs locally.

## Workflows

The workflow files are in `.github/workflows/`. Each file is the source of truth for its triggers, runner images and tool versions.

| Workflow | Runs on | Purpose |
| --- | --- | --- |
| Compatibility and coverage | Pull requests, pushes to `main` | Runs formatting, lint, type checks, the test suite with coverage, and package installation checks. It runs on Linux, macOS and Windows with the Python versions in the workflow's matrix, which start at the oldest supported version. See [testing](../testing/testing.md). |
| Coverage upload | When the workflow above calls it | Sends one coverage report to Codecov. |
| Fuzzing | Pull requests, pushes to `main` | Runs the [fuzz targets](../testing/fuzzing.md) for a fixed time. |
| PR Requirements | Pull request events | Checks that the title follows Conventional Commits and that the contributor checklist is complete. The title becomes the commit message on `main`, and the release tooling reads it. |
| OSV dependency scan | Pull requests, pushes to `main`, weekly | Scans the locked dependencies for known vulnerabilities and checks their licenses. See [dependencies](dependencies.md#scanning). |
| CodeQL | Pull requests, pushes to `main`, weekly | Analyzes the Python code and the workflow files for security weaknesses. |
| Scorecard supply-chain review | Pushes to `main`, weekly, and when a branch rule changes | Publishes OpenSSF Scorecard results for the repository. |
| Upstream criteria update | Weekly, and when its pull request closes | Opens a pull request when the BadgeApp sources change, and deletes the branch after a merge. See [upstream updates](upstream-updates.md). |
| Release Please | Pushes to `main` | Maintains the release pull request and starts the publication of a release. See [releasing](../release/releasing.md). |
| Publish to PyPI | When Release Please starts it | Builds, checks and scans a release candidate, then publishes it after a maintainer approves. |
| Verify published release | After a publication | Runs the commands in the [verification guide](../release/verification.md) against the published release. |

Every workflow except Coverage upload and PR Requirements can also be started manually.

## Required checks

The repository ruleset `protect-main` is the source of truth for the rules on `main`. It requires these checks to pass before a pull request can merge:

- every job of Compatibility and coverage
- the coverage upload and the Codecov patch status
- Fuzzing
- both PR Requirements jobs
- the OSV dependency scan
- both CodeQL analyses

The ruleset also sets these rules:

- Changes reach `main` only through a pull request, and the pull request must be up to date with `main`.
- Pull requests are merged by squash. The history of `main` is linear.
- Commits on `main` must have a verified signature.
- Code scanning blocks a merge when CodeQL or OSV-Scanner reports a security alert of high severity or above.
- Coverage of the server package must not fall below the floor in [testing](../testing/testing.md#coverage).
- Open secret scanning alerts block a merge.

Scorecard, the upstream update and the three release workflows run no check on a pull request. They are not required checks.

The ruleset does not require an approving review. Other members of the organization usually review a pull request before it merges.

## Security practices

- Each workflow sets read-only permissions at the top level. A job that needs more declares only the permissions that it needs.
- Every action is pinned to a full commit SHA. A comment beside the SHA gives the release tag.
- The workflows that run on pull request code have no access to secrets. PR Requirements reads the pull request metadata and does not check out code.
- The jobs that publish a release do not check out or run project code. They receive the release candidate as an artifact from an earlier job.
- Publication to PyPI uses trusted publishing through OIDC. The repository stores no PyPI token. The `pypi` environment requires approval from a maintainer.
- The release and upstream update workflows use a short-lived token from a GitHub App. The App signs the commits that these workflows create.
- CodeQL analyzes the workflow files, and Scorecard reviews token permissions and action pinning.
- Secret scanning and push protection are enabled for the repository.
- The repository stores one secret: the private key of the release App. Only the administrator can change it. The key is replaced when the organization or its governance changes, and when a compromise is possible.

The project does not run a separate workflow linter. GitHub validates a workflow file when it loads the file.

## Maintaining the workflows

Dependabot opens a pull request when an action has an update, and it changes the SHA and the tag comment together. [Dependencies](dependencies.md#updates) describes the Dependabot configuration.

A change to a workflow goes through a pull request like any other change. The release workflows, the upstream update and the release verification do not run on a pull request, so no check exercises a change to them before it merges. Review these changes line by line.

Two repository variables enable optional services. `CODECOV_ENABLED` enables the coverage upload, which authenticates through OIDC and uses no stored token. `PYPI_PUBLISH_ENABLED` enables publication.

## Local checks

`make validate` runs most of the checks that the Compatibility and coverage workflow runs: the lockfile check, formatting and lint, type checks, the tests with the coverage floor, and the catalog check. It does not run the package checks. It continues after a failure and returns a failing status if any check failed. `make check` is a faster subset: formatting and lint, type checks, and the tests without coverage.

`make setup-hooks` installs optional pre-commit hooks. The hooks run the same Make targets when a commit touches the relevant files, and they run the test suite on every commit.

The dependency scans, CodeQL, Scorecard and fuzzing run in CI. [Dependencies](dependencies.md#scanning) and [fuzzing](../testing/fuzzing.md) describe how to run the first and the last locally.
