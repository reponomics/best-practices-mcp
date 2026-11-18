# Verify a release

This guide shows how to check that the files of a release are the ones that the project published, and that the release workflow built them from the tagged commit. You need the [GitHub CLI](https://cli.github.com/), signed in with `gh auth login`, and [uv](https://docs.astral.sh/uv/getting-started/installation/) for step 3. You do not need a checkout of the repository, and you do not install the package.

Releases before 0.2.0-beta.3 do not have this evidence.

## What you rely on

No single party vouches for a release. The steps below check three parties against one another.

| Party | What it provides |
| --- | --- |
| GitHub | Hosts the release and records which files belong to it. It also issues the OIDC token that states which workflow, tag and commit a release job ran for. |
| Sigstore | Puts the claims of that token into a short-lived signing certificate and records every signature in a public log |
| PyPI | Hosts the package and records which publisher uploaded each file |

Step 1 relies on GitHub. Steps 2 and 4 check a Sigstore signature and the identity in its certificate. Step 3 checks the file that you downloaded from GitHub against PyPI's own record, with a tool that GitHub does not publish.

## Set the values for the release

Choose a release on the [releases page](https://github.com/reponomics/best-practices-mcp/releases) and set five variables. The example uses version 1.2.3.

```sh
REPO=reponomics/best-practices-mcp
TAG=v1.2.3
WHEEL=best_practices_mcp-1.2.3-py3-none-any.whl
SDIST=best_practices_mcp-1.2.3.tar.gz
COMMIT=$(gh api "repos/$REPO/git/ref/tags/$TAG" --jq .object.sha)
```

`COMMIT` is the full SHA of the commit that the tag points to. You can also read it from the release page, from your own clone, or with `git ls-remote "https://github.com/$REPO" "refs/tags/$TAG"`. Steps 2 and 4 fail if the signing certificate names a different commit.

For a beta such as `v1.2.3-beta.1`, the file names use `1.2.3b1`.

In PowerShell, write each assignment as `$REPO = "reponomics/best-practices-mcp"`. The commands below are the same in both shells.

## 1. Download and authenticate the files

```sh
gh release verify "$TAG" --repo "$REPO"
gh release download "$TAG" --repo "$REPO" --dir verify
cd verify
gh release verify-asset "$TAG" "$WHEEL" --repo "$REPO"
gh release verify-asset "$TAG" "$SDIST" --repo "$REPO"
gh release verify-asset "$TAG" SHA256SUMS --repo "$REPO"
```

Each command must report success. `gh release verify` checks GitHub's signed record of the release. The release is immutable: after publication, GitHub does not allow its tag or its files to change, and the release page shows an **Immutable** label. `gh release verify-asset` checks one downloaded file against that record. Run it for any other file that you intend to use.

Then check every file against the checksum list. Use `sha256sum -c SHA256SUMS` on Linux and `shasum -a 256 -c SHA256SUMS` on macOS. On Windows, compare the output of `Get-FileHash` with the entry in the list.

The "Source code" archives that GitHub generates are not the source distribution. Use the attached `.tar.gz` file.

## 2. Verify the build provenance

Run this for the wheel, then again with `"$SDIST"`:

```sh
gh attestation verify "$WHEEL" --repo "$REPO" --signer-workflow "$REPO/.github/workflows/release.yml" --cert-oidc-issuer https://token.actions.githubusercontent.com --source-ref "refs/tags/$TAG" --source-digest "$COMMIT" --deny-self-hosted-runners
```

Success means that the release workflow of this repository attested this exact file, at this tag and commit. To use the bundle that is attached to the release, add `--bundle provenance.sigstore.json`.

You can make the same check with the Sigstore client, which does not come from GitHub:

```sh
uvx sigstore verify github --bundle provenance.sigstore.json --cert-identity "https://github.com/$REPO/.github/workflows/release.yml@refs/tags/$TAG" --repository "$REPO" --ref "refs/tags/$TAG" --sha "$COMMIT" "$WHEEL"
```

It prints `OK` and the signed statement. It fails if the file, the repository, the tag or the commit differs.

## 3. Verify the PyPI attestation

```sh
uvx --from pypi-attestations pypi-attestations verify pypi --repository "https://github.com/$REPO" "$WHEEL"
uvx --from pypi-attestations pypi-attestations verify pypi --repository "https://github.com/$REPO" "$SDIST"
```

Each command prints `OK`. It confirms that PyPI received this exact file from the project's publisher. The file came from GitHub in step 1, so this step also shows that GitHub and PyPI hold the same file. The file page on PyPI shows the publisher: this repository, the workflow `release.yml` and the environment `pypi`.

## 4. Verify the SBOM signatures

```sh
gh attestation verify "$WHEEL" --repo "$REPO" --signer-workflow "$REPO/.github/workflows/release.yml" --cert-oidc-issuer https://token.actions.githubusercontent.com --source-ref "refs/tags/$TAG" --source-digest "$COMMIT" --deny-self-hosted-runners --predicate-type https://cyclonedx.org/bom --bundle runtime-wheel.sigstore.json
```

For the source distribution, use `"$SDIST"` and `runtime-sdist.sigstore.json`. Success means that the SBOM in the bundle belongs to that file. The readable copies are `runtime-wheel.cdx.json` and `runtime-sdist.cdx.json`. The Sigstore client command of step 2 also works here, with the SBOM bundle in place of the provenance bundle.

## Signing keys and identity

The project has no long-lived signing key, and there is no public key to import. The release workflow uses Sigstore keyless signing. For each signature it creates a key pair and presents its GitHub OIDC token to Sigstore. Sigstore issues a short-lived certificate that binds the public key to the claims of that token. The workflow signs and discards the private key. The certificate and the signature are in the attestation bundle.

The commands above check the signature and also the identity in the certificate. A valid signature from another identity is not acceptable. The expected identity is:

| Field | Value |
| --- | --- |
| OIDC issuer | `https://token.actions.githubusercontent.com` |
| Repository | `reponomics/best-practices-mcp` |
| Workflow | `.github/workflows/release.yml` |
| Source | The release tag and its commit |
| PyPI environment | `pypi` |

The verification tools obtain Sigstore's trust root themselves. `gh attestation trusted-root` prints it. Do not replace it with a file from the release.

The signer is the release process. A signature does not say that a particular person wrote or reviewed the code.

The release commit has a verified signature, and the repository accepts only signed commits on `main`. GitHub shows the signature on the commit page. The release tag is a lightweight tag and has no signature of its own. The immutable release protects the tag instead.

## What the release files hold

| File | Content |
| --- | --- |
| `release.json` | The tag, the commit, the version and the size and hash of each file |
| `qualification.json`, `qualification.log` | The result of installing and starting both distributions in fresh environments |
| `osv-vulnerabilities.sarif`, `osv-licenses.json` | The vulnerability scan and the license check for the release |
| `osv-scanner.toml` | The scan policy that applied |
| `runtime-*.cdx.json`, `runtime-*.inventory.json`, `pip-*.json` | The SBOM, the dependency list and the installation record of each reference installation |
| `tooling.cdx.json`, `uv.lock`, `pyproject.toml` | The inventory of the development tools and the files that define it |
| `*.sigstore.json` | The attestation bundles |

An SBOM describes one reference installation on one platform at the time of the release. Your installation can resolve different dependency versions.

## Limits

- These checks rely on GitHub, PyPI, Sigstore and your own tools.
- A valid signature shows who produced a file. It does not show that the software is free of defects.
- The project does not claim SLSA Build Level 3 or reproducible builds.
- The scan reports show the state on the day of the release.
- Verifying a file does not constrain what an installer downloads later. Install the exact version that you verified.

## If a check fails

Stop, and do not install the file. Check the tag, the file name and the version of your tools. Do not remove an identity option to make a command pass. Report a mismatch that you cannot explain through [SECURITY.md](../../SECURITY.md).

The project's Verify published release workflow runs the commands of steps 1 to 4 after each publication. It rehearses this guide. It is not an independent verification and does not replace checking your own download.
