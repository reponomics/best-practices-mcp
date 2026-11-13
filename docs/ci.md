# Continuous integration and repository setup

The workflows maintain the bounded nine-tool MCP; they do not add runtime services or automate BadgeApp submission. Development and security tools are not required to run an installed server. Release management and publication are described in [the release procedure](releasing.md).

## Checks and scope

| Workflow | Trigger and coverage | Required setup |
| --- | --- | --- |
| Compatibility and coverage | Pull requests to `main`, pushes to `main`, and manual runs; Python 3.11/3.12 on Ubuntu, macOS and Windows, offline regression/coverage, catalog checks and fresh wheel/sdist installation | GitHub Actions; Node 24 is development-only |
| Semantic PR | PR title metadata for PRs targeting `main`; conventional type/title validation | Squash-only merges and PR-title squash defaults make the validated title the commit on `main` |
| Upstream criteria check | Monday 09:23 UTC and manual runs on `main`; compares the two criteria YAML files and full English locale with upstream `production`, maintaining one tracking issue | Public upstream reads and job-scoped `issues: write` using `GITHUB_TOKEN`; no additional secret |
| OSV dependency scan | PRs/pushes to `main`, weekly schedule and manual runs; committed universal Python lock plus npm lock | Public OSV service access; no credential is needed for the scan |
| CodeQL | PRs/pushes to `main`, weekly schedule and manual runs; Python, JavaScript/TypeScript development code and GitHub Actions | Advanced setup in the new repository; public repository or licensed private code scanning |
| Coverage upload | Called after the existing compatibility matrix; uploads its Ubuntu/Python 3.11 report without rerunning tests | Codecov repository connection and `CODECOV_ENABLED=true` |
| Scorecard supply-chain review | Public default-branch pushes, branch-protection changes, weekly schedule and manual runs | Public `reponomics/best-practices-mcp`; results are review guidance, not an arbitrary score threshold |
| Release Please / PyPI | Release PR management and approved tagged publication | Release App and PyPI OIDC/environment setup; see [releasing](releasing.md) |

The six compatibility jobs retain their own measured coverage and installation evidence. Codecov shows server coverage trends from one representative matrix job; it does not replace the Windows/macOS results or imply combined multi-platform coverage. Its project and patch percentage statuses are informational. Tests and report-generation failures remain failures; no percentage threshold is substituted for the behavioral contract.

## Dependency inventory

`uv.lock` is the resolved cross-platform Python inventory for the package and all development extras, including build/release tools. `package-lock.json` covers the development-only DOM tooling. OSV receives these lockfiles explicitly with implicit resolution disabled. A failed scanner process is not converted into a clean scan. Reports are retained even when findings fail the check, where a report was produced.

The uv version is recorded in `.tool-versions` and pinned in the Python development extra. Keep these together when updating the tool. The normal project interface remains `venv` plus Make/pip; this lock does not silently migrate server installation to uv. The compatibility and fresh-consumer package checks resolve the declared dependencies through pip, so the committed OSV inventory is not a claim that every consumer resolver result is identical to that lock. A new compatible transitive version can be selected by pip; lock refresh and scheduled scans provide a reviewed inventory, while fresh-install tests separately check consumer compatibility.

Use the maintained Make targets for dependency checks and lock updates. Their underlying commands are:

```sh
venv/bin/uv lock --check
venv/bin/uv lock
```

Review the lock diff and rerun the required checks when accepting dependency updates. Dependabot proposes weekly grouped Python/uv, npm and GitHub Actions updates, with conventional PR-title prefixes. Major Python/npm updates remain separate for deliberate compatibility review; grouped security updates remain reviewable and do not auto-merge. Dependabot configuration does not itself enable repository vulnerability alerts or security-update settings; enable those in the new repository.

## Code scanning

This repository contains an explicit advanced CodeQL workflow. Do not enable GitHub's default CodeQL setup alongside it. The workflow scans interpreted source without installing or executing the project. Code scanning activates automatically when the target repository is public. While private, set `PRIVATE_CODE_SCANNING_ENABLED=true` only after enabling the necessary GitHub Code Security entitlement. Before that, the CodeQL job is visibly skipped, not qualified as a successful analysis.

OSV vulnerability scanning runs independently of code-scanning availability. Its SARIF upload requires the target repository to be public or explicitly enabled for private code scanning, and is omitted for fork PRs whose tokens cannot upload it. The downloadable report and scan exit status remain available. Do not waive vulnerabilities merely to make publication green; investigate and record any narrowly justified exception explicitly rather than copying another project's overrides.

## Codecov setup and privilege boundary

Install or authorize the Codecov GitHub App for `reponomics/best-practices-mcp`, connect the repository, then set repository variable `CODECOV_ENABLED=true`. This is a service integration, not a PyPI publishing credential. No stored Codecov token is configured. The upload job uses GitHub OIDC for same-repository events. Public fork PRs use Codecov's tokenless fork path and receive no OIDC token; private fork uploads are skipped.

Coverage measurement runs in the ordinary read-only compatibility jobs. A separate upload job downloads the current run's named coverage artifact and reads checked-out paths solely for mapping; it does not install or execute project code. It has only the additional `id-token: write` permission needed by Codecov. An enabled upload that fails fails its job, while its coverage percentage statuses remain informational. Verify the first actual upload and commit/path mapping before relying on the dashboard.

## Repository controls and activation

Keep workflow-level permissions read-only. Additional `security-events: write`, `id-token: write` and `issues: write` permissions are declared only on the jobs that need them. Actions are pinned to reviewed full commit SHAs; Dependabot maintains those references. The semantic-title workflow reads PR metadata without checking out PR code. The upstream criteria workflow runs only on the maintained repository's `main` branch; its single concurrency group serializes issue updates. Release App secrets and publication OIDC are never available to ordinary test jobs.

Before public release, configure the `main` ruleset to require the six compatibility jobs, semantic PR title check and OSV scan. After the first successful CodeQL run, add its three analysis checks where supported. Require PRs, verified signed commits on main and squash-only merges, with the PR title used as the squash commit title. Enable immutable GitHub releases before the first release; Release Please uses lightweight tags pointing to the signed release commits, not separately signed annotated tags. Do not require release/publication jobs or scheduled Scorecard analysis on ordinary PRs. Codecov percentage statuses remain informational. The exact check names should be selected from successful runs in the new repository rather than guessed from an old repository's check inventory.

The pre-release repository starts private and becomes public immediately before the first release. At that checkpoint, verify the environment approval gate, activate applicable code scanning, run the required checks in the new repository, and inspect any pending/skipped integrations honestly. A workflow file or a skipped job does not establish that CodeQL, Codecov, OSV or publication has succeeded. Public-service activation and the first real results are distinct from local YAML/actionlint and configuration validation.

## First push to exercise CI

Create the private `reponomics/best-practices-mcp` repository without a generated README or license, connect its remote, and push the reviewed `main` history. Use conventional-title pull requests for subsequent changes and inspect checks against the exact commits being reviewed.

Keep `PYPI_PUBLISH_ENABLED` unset and leave the release App variable unset while bringing up ordinary CI. The compatibility matrix and OSV scan can run before publication setup. A private-repository CodeQL skip is expected until the required entitlement or public visibility is in place; Codecov remains skipped until explicitly connected. Review actual run results before selecting required checks, then use the signed squash path for approved pull requests. Configure release services separately using the release procedure. No live browser session is needed for this first push; the first published beta must pass the browser runbook before stable promotion.

## Local validation

`make check` remains the required offline regression/lint interface. `make test-coverage` measures server coverage locally. Run `actionlint` over `.github/workflows/*.yml` when changing workflows. The OSV scan contacts the advisory service and CodeQL/Codecov/Scorecard are qualified through their configured GitHub jobs; local configuration checks do not substitute for those executions.

References: [CodeQL advanced workflow configuration](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options), [Codecov action and OIDC](https://github.com/codecov/codecov-action), [OSV-Scanner](https://google.github.io/osv-scanner/), [Dependabot configuration](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference).
