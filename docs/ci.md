# Continuous integration and repository setup

The workflows maintain the bounded ten-tool MCP; they do not add runtime services or automate BadgeApp submission. Development and security tools are not required to run an installed server. Release management and publication are described in [the release procedure](releasing.md).

## Checks and scope

| Workflow | Trigger and coverage | Required setup |
| --- | --- | --- |
| Compatibility and coverage | Pull requests to `main`, pushes to `main`, and manual runs; Python 3.11/3.12 on Ubuntu, macOS and Windows, offline regression/coverage, catalog checks and fresh wheel/sdist installation | GitHub Actions |
| Fuzzing | PRs/pushes to `main` and manual runs; document and proposal harnesses, 30 seconds each on Linux/Python 3.12 | Optional locked Atheris tooling; [run and reproduce fuzzing](fuzzing.md) |
| Semantic PR | PR title metadata for PRs targeting `main`; conventional type/title validation | Squash-only merges and PR-title squash defaults make the validated title the commit on `main` |
| Upstream criteria update | Monday 09:23 UTC and manual runs on `main`; refreshes retained upstream sources, catalog and provenance in one regular PR; deletes the reserved branch after merge | Existing Release App credentials for signed commits/PR events; optional `UPSTREAM_UPDATES_PAUSED=true` pauses updates for manual fixes |
| OSV dependency scan | PRs/pushes to `main`, weekly schedule and manual runs; separate vulnerability and license checks of the Python lock | Public OSV and deps.dev access; no credential is needed for the scans |
| CodeQL | PRs/pushes to `main`, weekly schedule and manual runs; Python and GitHub Actions | Advanced setup in the new repository; public repository or licensed private code scanning |
| Coverage upload | Called after the existing compatibility matrix; uploads its Ubuntu/Python 3.11 report without rerunning tests | Codecov repository connection and `CODECOV_ENABLED=true` |
| Scorecard supply-chain review | Public default-branch pushes, branch-protection changes, weekly schedule and manual runs | Public `reponomics/best-practices-mcp`; results are review guidance, not an arbitrary score threshold |
| Release Please / PyPI | Release PR management, draft/tag preparation, tagged candidate dispatch, release-time scans/SBOMs, approved attestation/PyPI publication, then immutable GitHub asset publication | Release App and PyPI OIDC/environment setup; see [releasing](releasing.md) |
| Verify published release | Successful `Publish to PyPI` workflow completion, or manual tag and expected commit selection on `main`; runs the commands in the [verification guide](verification.md) and retains troubleshooting logs | Read-only token, default-branch workflow, isolated locked `verification-tools`; human report inspection remains manual; no execution of downloaded release code |

The six compatibility jobs retain their own measured coverage and installation evidence. Each job runs `make test-coverage`, which enforces coverage.py's 95% combined statement/branch total through `fail_under = 95` in `[tool.coverage.report]` in `pyproject.toml`, with two decimal places of precision. Separate statement and branch measurements remain in the reports without independent floors. Test failures, report-generation failures and missing coverage data also fail the check. Below-threshold report commands finish writing their output and exit with status 2; the runner generates the remaining reports and preserves the failure for diagnosis. Environment reports also record the invoked GNU Make version (`make`), or `unavailable` if it cannot be determined; this is provenance information, outside the current OSV scan scope. Codecov shows server coverage trends from one representative matrix job; it does not replace the Windows/macOS results or imply combined multi-platform coverage. Its project and patch percentage statuses remain informational because enforcement occurs in the coverage producer.

## Workflow files

No workflow linter is part of the checks, hooks or release procedure. Workflow files are covered by GitHub's own validation when a workflow is loaded, by the CodeQL analysis of GitHub Actions, by Scorecard and by review.

## Dependency inventory

`uv.lock` is the universal development lockfile for runtime dependencies, the installed `dev` group and the non-default `audit-tools`, `fuzz`, `release-tools` and `verification-tools` groups. Local setup, upstream maintenance, compatibility CI and release qualification all use `make setup` to synchronize locked dependencies into `.venv` by default (the compatibility matrix overrides `VENV` as described below). The upstream workflow uses this same development environment, including its locked PyYAML dependency, without a separate setup target or top-level `venv` directory. `.python-version` defaults to Python 3.11; CI overrides `BOOTSTRAP_PYTHON` for its 3.11/3.12 matrix. See [ADR 0002](adr/0002-development-toolchain.md) for the decision and alternatives.

uv is an external bootstrap tool. Its exact requirement lives in `[tool.uv].required-version`; `setup-uv` reads this from `pyproject.toml`. The matching distribution is locked in `audit-tools` solely for inventory and is excluded from normal setup. `make tooling-check` checks agreement between these declarations and `uv.lock`; `.tool-versions` and asdf are not used. pip remains a locked development dependency for offline package checks. Release evidence uses a separate `release-tools` environment for pinned CycloneDX Python; the generator inspects fresh runtime environments without being installed in them.

OSV scans the committed Python lockfile explicitly with implicit resolution disabled, including the uv audit entry. This inventories declared package versions rather than attesting to installed bootstrap binaries or every OS tool. Scanner failures remain failures, and reports are retained when produced. Fresh-consumer checks install wheels and sdists through pip in clean environments without the development lock, so their transitive versions can differ from the scanned inventory.

The OSV job also enforces the dependency license allowlist, including 0BSD and Unlicense, using version-specific third-party metadata corrections and the documented Docutils development-tool exception in `osv-scanner.toml`. The local first-party package has a version-independent MIT override sourced from `LICENSE` and `pyproject.toml`, so an unpublished candidate does not fail on missing registry metadata. `make tooling-check` requires the override to match the project identity/license and the editable root in `uv.lock`, and rejects suppression flags or narrowing selectors. The optional PyPI verifier adds email-validator under the [OSI-approved Unlicense](https://opensource.org/license/unlicense); its other metadata corrections are scoped to the exact published versions. These entries do not suppress vulnerabilities. Both scans explicitly load that root policy. Newly exposed findings require investigation, not automatic exclusions.

Reassess license corrections and exceptions when a package's version or use changes, and keep the workflow's allowlist and the Makefile's `OSV_LICENSES` value together when changing policy. Both scan steps fail on findings or scanner errors, and the license step runs even after an earlier failure. Vulnerability SARIF stays in `osv-dependency-report`; license results, policy and lockfiles are retained separately in `osv-license-report` for 14 days. OSV 2.7.1 omits license findings from SARIF, so inspect the license JSON artifact for those findings. Contributors may rely on the PR workflow rather than installing the scanner locally; see the [dependency policy](../CONTRIBUTING.md#dependencies).

All six compatibility jobs invoke the canonical Make targets for setup, quality, lock/catalog checks, coverage, offline wheel checks and fresh-consumer installation. Windows invokes native GNU Make 4.4.1 from PowerShell; the Makefile selects `cmd.exe` recipes. Every matrix job uses `build/dev venv` to exercise paths containing spaces. Help is tested before environment creation. Release qualification also uses Make, while its publishing job retains its separate trust boundary. Release scans additionally cover the actual dependency resolution in each qualified installation, and publication requires those scans to pass. Runtime-reference SBOMs, tooling inventory, SARIF, license JSON, hashes and signed provenance become immutable release assets; see the [release procedure](releasing.md).

Use `make lock` to regenerate the lock and `make lock-check` to verify it. For a uv update, change both the executable requirement and the audit-group pin, install the new external version, regenerate the lock, and rerun setup and checks.

Review the lock diff and rerun the required checks when accepting dependency updates. Dependabot proposes weekly grouped Python/uv and GitHub Actions updates with conventional PR-title prefixes. Major Python updates remain separate for deliberate compatibility review; grouped security updates remain reviewable and do not auto-merge. Dependabot configuration does not itself enable repository vulnerability alerts or security-update settings; enable those in the new repository.

## Optional local dependency scans

Install [OSV-Scanner](https://google.github.io/osv-scanner/installation/) at the version pinned in the OSV workflow. Put it on `PATH`, or pass `OSV_SCANNER=/path/to/osv-scanner` to Make:

```sh
make -k scan-vulnerabilities scan-licenses
```

These commands query OSV and deps.dev using the committed Python lockfile and repository policy. Both scans are attempted, and any failure produces a nonzero exit status. Results are written to ignored `osv-scanner.sarif` and `osv-licenses.json`; inspect `license_violations` for license-policy findings. Investigate unknown metadata against the dependency's license files before proposing a policy correction or exception.

## Code scanning

This repository contains an explicit advanced CodeQL workflow. Do not enable GitHub's default CodeQL setup alongside it. The workflow scans interpreted source without installing or executing the project. Code scanning activates automatically when the target repository is public. While private, set `PRIVATE_CODE_SCANNING_ENABLED=true` only after enabling the necessary GitHub Code Security entitlement. Before that, the CodeQL job is visibly skipped, not qualified as a successful analysis.

OSV vulnerability scanning runs independently of code-scanning availability. Its SARIF upload requires the target repository to be public or explicitly enabled for private code scanning, and is omitted for fork PRs whose tokens cannot upload it. The downloadable report and scan exit status remain available. Do not waive vulnerabilities merely to make publication green; investigate and record any narrowly justified exception explicitly rather than copying another project's overrides.

## Codecov setup and privilege boundary

Install or authorize the Codecov GitHub App for `reponomics/best-practices-mcp`, connect the repository, then set repository variable `CODECOV_ENABLED=true`. This is a service integration, not a PyPI publishing credential. No stored Codecov token is configured. The upload job uses GitHub OIDC for same-repository events. Public fork PRs use Codecov's tokenless fork path and receive no OIDC token; private fork uploads are skipped.

Coverage measurement runs in the ordinary read-only compatibility jobs. A separate upload job downloads the current run's named coverage artifact and reads checked-out paths solely for mapping; it does not install or execute project code. It has only the additional `id-token: write` permission needed by Codecov. An enabled upload that fails fails its job, while its coverage percentage statuses remain informational. Verify the first actual upload and commit/path mapping before relying on the dashboard.

## Repository controls and activation

Keep workflow-level permissions read-only. Additional token permissions are declared only on the jobs that need them. Actions are pinned to reviewed full commit SHAs; Dependabot maintains those references. The semantic-title workflow reads PR metadata without checking out PR code. Upstream patch preparation runs trusted code from `main` with read-only permissions; a short-lived App token then publishes only the allowlisted source/catalog/documentation files. Its single concurrency group serializes updates and branch cleanup. The merge cleanup job has `contents: write` solely to remove the reserved branch when its head still matches the merged PR. See the [upstream update procedure](upstream-compatibility.md#checking-for-upstream-changes) for branch ownership and pausing updates. Release App secrets and publication OIDC are never available to ordinary test jobs. The release dispatcher has only the extra Actions permission needed to start the tagged workflow. Metadata-only draft preflight and final GitHub asset publication have Contents write permission; the approved PyPI job has OIDC and Attestations write permission. None of those privileged jobs checks out or executes project build code.

Before public release, configure the `main` ruleset to require the six compatibility jobs, semantic PR title check and OSV scan. After the first successful CodeQL run, add its three analysis checks where supported. Require PRs, verified signed commits on main and squash-only merges, with the PR title used as the squash commit title. Enable immutable GitHub releases before the first release; Release Please uses lightweight tags pointing to the signed release commits, not separately signed annotated tags. Do not require release/publication jobs or scheduled Scorecard analysis on ordinary PRs. Codecov percentage statuses remain informational. The exact check names should be selected from successful runs in the new repository rather than guessed from an old repository's check inventory.

The pre-release repository starts private and becomes public immediately before the first release. At that checkpoint, verify the environment approval gate, activate applicable code scanning, run the required checks in the new repository, and inspect any pending/skipped integrations honestly. A workflow file or a skipped job does not establish that CodeQL, Codecov, OSV or publication has succeeded. Public-service activation and the first real results are distinct from local configuration validation.

## First push to exercise CI

Create the private `reponomics/best-practices-mcp` repository without a generated README or license, connect its remote, and push the reviewed `main` history. Use conventional-title pull requests for subsequent changes and inspect checks against the exact commits being reviewed.

Keep `PYPI_PUBLISH_ENABLED` unset and leave the release App variable unset while bringing up ordinary CI. The compatibility matrix and OSV scan can run before publication setup. A private-repository CodeQL skip is expected until the required entitlement or public visibility is in place; Codecov remains skipped until explicitly connected. Review actual run results before selecting required checks, then use the signed squash path for approved pull requests. Configure release services separately using the release procedure. No live browser session is needed for this first push; the first published beta must pass the browser runbook before stable promotion.

## Local validation

`make validate` runs lock consistency, quality checks, offline tests and catalog reproduction in one command. It continues with independent checks after failures and returns a failing status if any check fails. See [contributor prerequisites](../CONTRIBUTING.md#validate-the-implementation). OSV runs in CI and is not part of standard contributor validation. For proactive dependency checks, see [optional local scans](#optional-local-dependency-scans). `make check` remains the offline regression/lint interface, and `make test-coverage` measures server coverage locally. CodeQL/Codecov/Scorecard are qualified through their configured GitHub jobs; local configuration checks do not substitute for those executions.

References: [CodeQL advanced workflow configuration](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options), [Codecov action and OIDC](https://github.com/codecov/codecov-action), [OSV-Scanner](https://google.github.io/osv-scanner/), [Dependabot configuration](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference).
