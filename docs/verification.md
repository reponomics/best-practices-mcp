# Verify a release

This guide explains how to verify the integrity and authenticity of Best Practices MCP release assets before installing or relying on them. It covers the evidence published starting with **0.2.0-beta.3**; do not assume earlier releases have the same evidence. Maintainer operations belong in the [release procedure](releasing.md).

## Claims and evidence

| Claim | Evidence and verification | Limit |
| --- | --- | --- |
| A downloaded file belongs to the project's published GitHub release. | GitHub's signed release attestation; `gh release verify-asset` checks the local file against it. | This authenticates release membership, not software safety. |
| Published release assets and their associated tag are immutable. | The release page's **Immutable** label and `gh release verify`; GitHub locks the assets and tag on publication. | Release notes and titles remain editable. Immutability is not a guarantee of permanent availability. |
| The distributions were attested by the expected release workflow at the expected source revision. | SLSA v1 provenance, verified with repository, workflow, tag and commit constraints. | Provenance identifies the attesting workflow; it does not prove reproducible builds or independently audit the build. |
| PyPI accepted the files from the configured GitHub publisher. | PyPI publish attestations identify `reponomics/best-practices-mcp`, `release.yml` and environment `pypi`. | Trusted Publishing uses short-lived OIDC credentials; it does not certify code quality or eliminate compromised-workflow risk. |
| Runtime reference installations have signed dependency inventories. | CycloneDX SBOM attestations bind each reference SBOM to its distribution digest. | These are platform- and time-specific reference installations, not bundled or universally fixed dependency sets. |
| Release dependency scans and package qualification passed. | Retained OSV vulnerability SARIF, separate license JSON, policy inputs and qualification evidence. | These are dated results within the documented scan scope and license policy, not a claim of no vulnerabilities or unrestricted licensing. |

[GitHub immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases), [artifact verification](https://cli.github.com/manual/gh_attestation_verify), and [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) describe the underlying trust mechanisms.

## 1. Download and authenticate release assets

Install a current [GitHub CLI](https://cli.github.com/) with `gh release verify`, `gh release verify-asset` and `gh attestation verify` available. Authenticate with `gh auth login` if needed; verification needs read access, not repository write permission. The commands below work in POSIX shells and Windows PowerShell as single lines. No repository checkout, project virtual environment or installation of this package is required.

The worked example uses the published [beta.3 release](https://github.com/reponomics/best-practices-mcp/releases/tag/v0.2.0-beta.3), whose source commit is [`b222cabb63cbd5d44475b965e44ee349eee161ef`](https://github.com/reponomics/best-practices-mcp/commit/b222cabb63cbd5d44475b965e44ee349eee161ef). For another release, replace the tag, filenames, directory and full commit SHA throughout. Python filenames normalize `0.2.0-beta.3` to `0.2.0b3`.

```sh
gh release verify v0.2.0-beta.3 --repo reponomics/best-practices-mcp
gh release download v0.2.0-beta.3 --repo reponomics/best-practices-mcp --dir verify-beta3
cd verify-beta3
gh release verify-asset v0.2.0-beta.3 best_practices_mcp-0.2.0b3-py3-none-any.whl --repo reponomics/best-practices-mcp
gh release verify-asset v0.2.0-beta.3 best_practices_mcp-0.2.0b3.tar.gz --repo reponomics/best-practices-mcp
gh release verify-asset v0.2.0-beta.3 SHA256SUMS --repo reponomics/best-practices-mcp
```

Use a new download directory. Each verification must report success and exit with status zero. Check that the verified release tag and commit match the release you intended to obtain. For a new version, obtain the expected commit from the project's release/tag history and compare it with the signed release record; do not take an arbitrary downloaded manifest as the sole source of expected identity.

Repeat `gh release verify-asset` with the filename of any report, SBOM or signature bundle you intend to use. This checks the actual local bytes against GitHub's signed release record. `gh release verify` alone checks the release record, not your downloaded files. GitHub's automatically generated **Source code (zip/tar.gz)** downloads are not the packaged source distribution; use the explicitly attached `best_practices_mcp-*.tar.gz` file. See the [release asset verifier](https://cli.github.com/manual/gh_release_verify-asset).

After authenticating `SHA256SUMS`, you can check all its entries on Linux with `sha256sum -c SHA256SUMS` or on macOS with `shasum -a 256 -c SHA256SUMS`. On Windows, use `Get-FileHash -Algorithm SHA256 ./best_practices_mcp-0.2.0b3-py3-none-any.whl` and compare its hash to the matching manifest entry, or use `gh release verify-asset` directly for each file. A checksum without an authenticated expected value establishes consistency, not publisher identity. The three workflow signature bundles are created after the checksum manifest and are verified separately.

## 2. Verify the distribution's workflow provenance

Run this against the downloaded wheel, then repeat it with the source archive filename:

```sh
gh attestation verify best_practices_mcp-0.2.0b3-py3-none-any.whl --repo reponomics/best-practices-mcp --signer-workflow reponomics/best-practices-mcp/.github/workflows/release.yml --cert-oidc-issuer https://token.actions.githubusercontent.com --source-ref refs/tags/v0.2.0-beta.3 --source-digest b222cabb63cbd5d44475b965e44ee349eee161ef --deny-self-hosted-runners
```

The default predicate is `https://slsa.dev/provenance/v1`. Success verifies the artifact digest, signature and expected workflow/source identity. Inspect the reported workflow invocation and its successful build, publication and finalization jobs. For beta.3 this is [run 43759677395, attempt 1](https://github.com/reponomics/best-practices-mcp/actions/runs/43759677395). Add `--format json` to retain the verified statement and certificate details.

To use the attached provenance bundle, append `--bundle provenance.sigstore.json` to the same command, retaining all identity constraints. Bundle verification may still need trust-root network access; fully offline verification requires the preparation described in [GitHub's offline instructions](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/verify-attestations-offline). Online lookup also checks association with the repository currently using that name; a saved bundle records identity at signing time.

### Signing keys and trust roots

Our workflow and PyPI attestations use Sigstore keyless signing. Each signing operation creates an ephemeral keypair: the private key signs the statement containing the artifact digest, and a short-lived X.509 certificate binds the public key to the workflow's OIDC identity. These release-signing private keys exist in the signing process, are discarded afterward, and are not uploaded to GitHub Releases or PyPI. There is no persistent project release-signing key for users to import. This separates transient signing from public artifact serving; it does not make the signing workflow independent of GitHub. See [Sigstore's key lifecycle](https://docs.sigstore.dev/about/overview/#how-sigstore-works).

Users obtain the public signing certificate and signature in the downloaded `provenance.sigstore.json` and `runtime-*.sigstore.json` bundles, or through PyPI's provenance retrieved by its verifier. The certificate's public key verifies the signature; its identity and trust chain must also be checked. Accepting an arbitrary certificate shipped beside a file is insufficient.

| Expected identity | Required value |
| --- | --- |
| OIDC issuer | `https://token.actions.githubusercontent.com` |
| Source repository | `https://github.com/reponomics/best-practices-mcp` |
| Signing workflow | `reponomics/best-practices-mcp/.github/workflows/release.yml` |
| Source ref and digest | The selected `refs/tags/...` release tag and its full commit SHA |
| PyPI publisher environment | `pypi` |

The workflow verifier commands enforce the issuer, repository, workflow, tag and commit. The PyPI verifier below enforces the expected repository; also inspect its publisher metadata for the workflow and environment. The signer is the release process, not a claim that a particular human authored or reviewed every source change. GitHub's immutable-release attestation has a separate GitHub service identity and is checked by `gh release verify`, not by applying these workflow identity constraints to it.

Verification tools authenticate the certificate-authority and transparency-log trust material using their trusted configuration, including Sigstore's TUF distribution. Online `gh attestation verify` obtains this material automatically. To obtain the public trust material explicitly, use:

```sh
gh attestation trusted-root
```

This prints trusted-root JSON for the supported Sigstore instances; it is not a project private key or a substitute for checking the expected signer. Follow the [CLI reference](https://cli.github.com/manual/gh_attestation_trusted-root) and the offline guide linked above to save and use it. Do not replace trust roots with an unauthenticated file from the release. Verifiers check that signing occurred during the certificate's validity using authenticated timestamp/transparency evidence, so expiry of a short-lived certificate does not by itself invalidate an old release signature.

## 3. Verify PyPI's publisher attestation

PyPI exposes provenance in the release's file details. Expect the GitHub publisher `reponomics/best-practices-mcp`, workflow `release.yml`, environment `pypi`, and the same source commit, tag and workflow invocation as above. Trusted Publishing authenticates the upload; the publish attestation binds that identity to the distribution's digest.

With [uv](https://docs.astral.sh/uv/getting-started/installation/) installed, run the official verifier against the local files you already downloaded:

```sh
uvx --from pypi-attestations pypi-attestations verify pypi --repository https://github.com/reponomics/best-practices-mcp best_practices_mcp-0.2.0b3-py3-none-any.whl
uvx --from pypi-attestations pypi-attestations verify pypi --repository https://github.com/reponomics/best-practices-mcp best_practices_mcp-0.2.0b3.tar.gz
```

Expect `OK` for each file. This verifies the local distribution against PyPI's provenance and expected repository, rather than checking only an unrelated copy. To fetch and verify a PyPI file directly, replace the local filename with `pypi:` followed by that filename. The verifier is a separate tool; it does not require installing Best Practices MCP. See [PyPI's verification instructions](https://docs.pypi.org/attestations/consuming-attestations/).

Verification applies to the bytes checked. A later unpinned `uvx` or `pip` installation can select a different release or dependency set; these commands do not automatically enforce verification in your installer.

## 4. Inspect SBOMs and scan evidence

For the wheel's signed runtime SBOM, verify the **wheel** as the subject, using the CycloneDX predicate and attached bundle:

```sh
gh attestation verify best_practices_mcp-0.2.0b3-py3-none-any.whl --repo reponomics/best-practices-mcp --signer-workflow reponomics/best-practices-mcp/.github/workflows/release.yml --cert-oidc-issuer https://token.actions.githubusercontent.com --source-ref refs/tags/v0.2.0-beta.3 --source-digest b222cabb63cbd5d44475b965e44ee349eee161ef --deny-self-hosted-runners --predicate-type https://cyclonedx.org/bom --bundle runtime-wheel.sigstore.json
```

For the source archive, substitute its filename and `runtime-sdist.sigstore.json`. Add `--format json` to inspect the verified statement's `predicate`, which contains the SBOM. The readable copies are `runtime-wheel.cdx.json` and `runtime-sdist.cdx.json`; authenticate those files with `gh release verify-asset` before using them. Their metadata records the distribution digest, source commit, Python version, platform and generation time, including environment bootstrap tools in their stated scope.

| Asset | What to inspect |
| --- | --- |
| `release.json` | Tag, source commit, normalized version, scanner version, artifact sizes and SHA-256 digests. Paths refer to the original bundle; download filenames are flattened. |
| `qualification.json`, `qualification.log` | Successful fresh wheel/source installation, dependency consistency, entry-point checks and MCP probes; check the artifact hashes. |
| `osv-vulnerabilities.sarif` | Vulnerability results for the scanned inventories; check the release run's scan step succeeded, not just whether the report has zero results. |
| `osv-licenses.json`, `osv-scanner.toml` | Separate license results, allowlist, metadata corrections and documented exceptions, including Docutils. |
| `runtime-*.inventory.json`, `pip-*.json` | Actual reference-installation dependencies supplied to the scanner and sanitized installation records. |
| `tooling.cdx.json`, lockfiles and `actionlint-*` inputs | Separate development/tooling inventory, including the pinned actionlint fork and its Go toolchain. |

Release vulnerability and license findings, and scanner failures, block publication. The scan covers reference runtime dependencies and the Python/npm/actionlint inventories; the Go standard library is checked separately for vulnerabilities. The unpublished project root is excluded from the runtime dependency inventory. This is dependency scanning, not a source-code audit, full operating-system scan or legal opinion. The retained policy is part of the interpretation of a passing result. Scheduled scans can find advisories disclosed after publication; release reports remain snapshots. See [CI scope](ci.md) and the [toolchain inventory boundaries](adr/0002-development-toolchain.md).

## Limits and failed verification

These checks rely on GitHub, PyPI, the relevant signing infrastructure and your verification tools. A valid signature proves an authenticated claim about particular bytes; it does not establish that the software is benign, that every dependency is safe, or that the workflow could not have been compromised. The project publishes SLSA-format provenance but does **not** claim SLSA Build Level 3, reproducible builds, or complete OpenSSF/OSPS certification. Lightweight release tags point to signed commits; they are not separately signed annotated tags.

GitHub's release attestation covers attached reports, while the workflow's build/SBOM attestations have the distributions as subjects. Runtime SBOMs describe reference installations; dependency resolution can differ by platform and installation date. The tooling SBOM is separate from the MCP runtime. Workflow artifacts expire after 30 days; release assets provide the retained public evidence, subject to hosting availability.

If a required verification fails, stop before installing or relying on the asset. Confirm the repository, tag, filename and tool version, then report an unexplained mismatch through the project's [security reporting instructions](../SECURITY.md). Do not bypass a failed check by removing identity constraints. Absence of evidence for an older release is not a successful verification under this guide.

These instructions address release integrity/authenticity verification under [OSPS_DO_03_01](https://www.bestpractices.dev/en/criteria#baseline-3.osps_do_03_01) and expected release-author identity under [OSPS_DO_03_02](https://www.bestpractices.dev/en/criteria#baseline-3.osps_do_03_02). The signed distribution attestations and GitHub release record provide evidence for [OSPS-BR-06.01](https://baseline.openssf.org/versions/2026-08-28#osps-br-0601), which explicitly allows attestations; `SHA256SUMS` alone is not a signature. These controls do not require a signed Git tag, and broader baseline assessment is separate.
