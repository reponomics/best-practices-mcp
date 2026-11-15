"""Verify public release bytes and evidence without installing or executing the package."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

REPOSITORY = "reponomics/best-practices-mcp"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
WORKFLOW = f"{REPOSITORY}/.github/workflows/release.yml"
ISSUER = "https://token.actions.githubusercontent.com"
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
COMMAND_TIMEOUT = 120
MAX_RUN_ATTEMPTS = 51  # Initial execution plus GitHub's maximum 50 reruns.
SIGNATURES = {
    "provenance.sigstore.json",
    "runtime-wheel.sigstore.json",
    "runtime-sdist.sigstore.json",
}
REPORT_NAMES = {
    "actionlint-go.mod",
    "actionlint-go.sum",
    "actionlint-inventory.json",
    "actionlint-provenance.json",
    "actionlint-stdlib-inventory.json",
    "actionlint-workflow.yml",
    "node-version.txt",
    "osv-licenses.json",
    "osv-scanner.toml",
    "osv-vulnerabilities.sarif",
    "package-lock.json",
    "pip-sdist.json",
    "pip-wheel.json",
    "pre-commit-config.yaml",
    "pyproject.toml",
    "qualification.json",
    "qualification.log",
    "release-workflow.yml",
    "runtime-sdist.cdx.json",
    "runtime-sdist.inventory.json",
    "runtime-wheel.cdx.json",
    "runtime-wheel.inventory.json",
    "tooling.cdx.json",
    "uv.lock",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def normalized_version(tag: str) -> str:
    require(re.fullmatch(r"v\d+\.\d+\.\d+(?:-beta\.\d+)?", tag) is not None, "Invalid release tag")
    return tag[1:].replace("-beta.", "b")


def distribution_names(version: str) -> dict[str, str]:
    return {
        "wheel": f"best_practices_mcp-{version}-py3-none-any.whl",
        "sdist": f"best_practices_mcp-{version}.tar.gz",
    }


def safe_name(name: str) -> str:
    require(
        isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) is not None,
        "Unsafe release asset name",
    )
    return name


def digest(value: str, length: int = 64) -> str:
    require(
        isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None,
        "Invalid cryptographic digest",
    )
    return value


def identity(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), "Expected a regular downloaded file")
    require(path.stat().st_size <= MAX_FILE_BYTES, "Downloaded file exceeds size limit")
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def read_json(path: Path):
    identity(path)
    return json.loads(path.read_text(encoding="utf-8"))


class Evidence:
    """Capture tool output as data and keep a report even when a check fails."""

    def __init__(self, root: Path, tag: str, expected_sha: str | None):
        root.mkdir(parents=True, exist_ok=True)
        require(not (root / "report.json").is_symlink(), "Initial report must not be a symlink")
        require(
            {path.name for path in root.iterdir()} <= {"report.json"},
            "Verification output must be fresh except for its initial report",
        )
        self.root = root
        self.logs = root / "evidence"
        self.logs.mkdir()
        self.assets = root / "github"
        self.assets.mkdir()
        self.report = {
            "schema_version": 1,
            "repository": REPOSITORY,
            "tag": tag,
            "expected_sha": expected_sha,
            "started_at": datetime.now(UTC).isoformat(),
            "status": "running",
            "checks": [],
        }
        self.save()

    def save(self) -> None:
        (self.root / "report.json").write_text(
            json.dumps(self.report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def check(self, name: str, function, *args):
        entry = {"name": name, "status": "running"}
        self.report["checks"].append(entry)
        self.save()
        try:
            result = function(*args)
        except Exception as error:
            entry.update(status="failed", error=f"{type(error).__name__}: {error}")
            self.save()
            raise
        entry["status"] = "passed"
        self.save()
        return result

    def command(self, label: str, args: list[str], *, as_json: bool = False):
        output = self.logs / f"{safe_name(label)}.stdout"
        errors = self.logs / f"{label}.stderr"
        # No raw tool output reaches Actions' workflow-command parser.
        with output.open("wb") as stdout, errors.open("wb") as stderr:
            result = subprocess.run(
                args, stdout=stdout, stderr=stderr, timeout=COMMAND_TIMEOUT, check=False
            )
        if args[0] == "gh":
            time.sleep(0.6)
        require(result.returncode == 0, f"Verification command failed: {label}")
        require(output.stat().st_size <= MAX_FILE_BYTES, "Tool output exceeds size limit")
        text = output.read_text(encoding="utf-8")
        return json.loads(text) if as_json else text

    def api(self, label: str, endpoint: str):
        output = self.command(label, ["gh", "api", "--include", endpoint])
        headers, body = output.replace("\r\n", "\n").split("\n\n", 1)
        rate = dict(line.lower().split(": ", 1) for line in headers.splitlines() if ": " in line)
        if "x-ratelimit-remaining" in rate:
            require(int(rate["x-ratelimit-remaining"]) > 0, "GitHub API rate limit exhausted")
        return json.loads(body)


def fetch_bytes(url: str, limit: int, hosts: set[str]) -> bytes:
    """Retry only transient transport errors; invalid content never gets retried."""
    require(urllib.parse.urlsplit(url).scheme == "https", "Download must use HTTPS")
    require(urllib.parse.urlsplit(url).hostname in hosts, "Unexpected download host")
    for attempt in range(3):
        try:
            return read_response(url, limit, hosts)
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
            delay = max(2**attempt, int(error.headers.get("Retry-After", "0")))
            require(
                delay <= 10, "Server requested a longer retry interval; retry the workflow later"
            )
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            delay = 2**attempt
        time.sleep(delay)
    raise AssertionError("Unreachable retry state")


def read_response(url: str, limit: int, hosts: set[str]) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "best-practices-release-verifier"})
    opener = urllib.request.build_opener(AllowedRedirects(hosts))
    with opener.open(request, timeout=30) as response:
        final = urllib.parse.urlsplit(response.url)
        require(final.scheme == "https" and final.hostname in hosts, "Unexpected redirect host")
        data = response.read(limit + 1)
    require(len(data) <= limit, "Download exceeds size limit")
    return data


class AllowedRedirects(urllib.request.HTTPRedirectHandler):
    """Check each redirect before sending a request to its destination."""

    def __init__(self, hosts: set[str]):
        self.hosts = hosts

    def redirect_request(self, request, response, code, message, headers, new_url):
        parsed = urllib.parse.urlsplit(new_url)
        require(
            parsed.scheme == "https" and parsed.hostname in self.hosts, "Unexpected redirect host"
        )
        return super().redirect_request(request, response, code, message, headers, new_url)


def release_identity(verified: dict, tag: str, expected_sha: str | None) -> tuple[str, dict]:
    statement = verified["verificationResult"]["statement"]
    require(
        statement["predicateType"] == "https://in-toto.io/attestation/release/v0.2",
        "Unexpected release attestation type",
    )
    predicate = statement["predicate"]
    require(
        predicate["repository"] == REPOSITORY and predicate["tag"] == tag,
        "Signed release identity mismatch",
    )
    source = [s for s in statement["subject"] if "uri" in s]
    require(
        len(source) == 1 and source[0]["uri"] == f"pkg:github/{REPOSITORY}@{tag}",
        "Signed source identity mismatch",
    )
    sha = digest(source[0]["digest"]["sha1"], 40)
    require(expected_sha is None or sha == expected_sha, "Signed release commit mismatch")
    files = {}
    for subject in statement["subject"]:
        if "name" not in subject:
            continue
        name = safe_name(subject["name"])
        require(name not in files, "Duplicate signed release asset")
        files[name] = digest(subject["digest"]["sha256"])
    return sha, files


def release_metadata(metadata: dict, tag: str, signed_files: dict, version: str) -> list[dict]:
    require(
        metadata["tag_name"] == tag and metadata["draft"] is False, "Expected the published release"
    )
    require(metadata.get("immutable") is True, "Release is not immutable")
    require(metadata["prerelease"] == ("-beta." in tag), "Release prerelease flag mismatch")
    assets = metadata["assets"]
    names = [safe_name(asset["name"]) for asset in assets]
    expected = REPORT_NAMES | SIGNATURES | {"release.json", "SHA256SUMS"}
    expected |= set(distribution_names(version).values())
    require(
        len(names) == len(set(names)) and set(names) == expected == set(signed_files),
        "Unexpected or missing release assets",
    )
    require(all(0 < asset["size"] <= MAX_FILE_BYTES for asset in assets), "Asset size limit")
    require(sum(asset["size"] for asset in assets) <= MAX_TOTAL_BYTES, "Release size limit")
    return assets


def download_assets(evidence: Evidence, tag: str, assets: list[dict], signed_files: dict) -> None:
    hosts = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
    for asset in assets:
        name = asset["name"]
        url = f"{REPOSITORY_URL}/releases/download/{tag}/{name}"
        require(asset["browser_download_url"] == url, "Unexpected asset URL")
        path = evidence.assets / name
        path.write_bytes(fetch_bytes(url, asset["size"], hosts))
        require(
            identity(path) == {"bytes": asset["size"], "sha256": signed_files[name]},
            "Downloaded GitHub asset differs from signed identity",
        )
        evidence.command(
            f"release-asset-{name}",
            [
                "gh",
                "release",
                "verify-asset",
                tag,
                str(path),
                "--repo",
                REPOSITORY,
            ],
        )


def manifest_inventory(manifest: dict, distributions: dict) -> dict:
    flattened = {}
    for name, value in manifest["artifacts"].items():
        path = PurePosixPath(name)
        require(
            len(path.parts) == 2 and path.parts[0] in {"dist", "reports"},
            "Unexpected manifest path",
        )
        filename = safe_name(path.name)
        require(filename not in flattened, "Duplicate flattened manifest path")
        require(
            (path.parts[0] == "dist") == (filename in distributions.values()),
            "Unexpected manifest artifact role",
        )
        flattened[filename] = value
    require(set(flattened) == REPORT_NAMES | set(distributions.values()), "Incomplete manifest")
    return flattened


def verify_manifest(root: Path, tag: str, sha: str, version: str) -> None:
    manifest = read_json(root / "release.json")
    require(
        manifest["schema_version"] == 1
        and manifest["tag"] == tag
        and manifest["commit"] == sha
        and manifest["version"] == version,
        "Release manifest identity mismatch",
    )
    files = manifest_inventory(manifest, distribution_names(version))
    for name, expected in files.items():
        require(identity(root / name) == expected, "Manifest checksum or size mismatch")
    files["release.json"] = identity(root / "release.json")
    sums = {}
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        checksum, name = line.split("  ", 1)
        require(safe_name(name) not in sums, "Duplicate checksum entry")
        sums[name] = digest(checksum)
    require(
        sums == {name: item["sha256"] for name, item in files.items()},
        "Checksum manifest does not cover exactly the candidate files",
    )


def verify_reports(root: Path, version: str) -> None:
    qualification = read_json(root / "qualification.json")
    require(
        qualification["status"] == "passed" and qualification["installation"]["status"] == "passed",
        "Qualification failed",
    )
    require(qualification["version"] == version, "Qualification version mismatch")
    expected = {name: identity(root / name) for name in distribution_names(version).values()}
    require(qualification["artifacts"] == expected, "Qualification artifact mismatch")
    runs = read_json(root / "osv-vulnerabilities.sarif")["runs"]
    require(bool(runs), "Missing vulnerability scan")
    for run in runs:
        require(
            run["tool"]["driver"]["name"] == "osv-scanner" and not run.get("results"),
            "Vulnerability findings in published report",
        )
        require(
            all(i.get("executionSuccessful") is True for i in run.get("invocations", [])),
            "Vulnerability scanner failed",
        )
    licenses = read_json(root / "osv-licenses.json")
    require(
        bool(licenses["results"])
        and bool(licenses["experimental_config"]["licenses"]["allowlist"]),
        "Missing license scan or policy",
    )
    packages = (package for result in licenses["results"] for package in result["packages"])
    require(
        not any(package.get("license_violations") for package in packages),
        "License violations in published report",
    )


def attestation_args(path: Path, tag: str, sha: str) -> list[str]:
    return [
        "gh",
        "attestation",
        "verify",
        str(path),
        "--repo",
        REPOSITORY,
        "--signer-workflow",
        WORKFLOW,
        "--cert-oidc-issuer",
        ISSUER,
        "--source-ref",
        f"refs/tags/{tag}",
        "--source-digest",
        sha,
        "--deny-self-hosted-runners",
        "--format",
        "json",
    ]


def verified_statement(results: list, tag: str, sha: str, path: Path, predicate: str) -> dict:
    require(len(results) == 1, "Expected one verified attestation")
    verified = results[0]["verificationResult"]
    certificate = verified["signature"]["certificate"]
    expected = {
        "issuer": ISSUER,
        "sourceRepositoryURI": REPOSITORY_URL,
        "sourceRepositoryDigest": sha,
        "sourceRepositoryRef": f"refs/tags/{tag}",
        "buildSignerURI": f"https://github.com/{WORKFLOW}@refs/tags/{tag}",
        "runnerEnvironment": "github-hosted",
    }
    require(
        all(certificate.get(key) == value for key, value in expected.items()),
        "Verified certificate identity mismatch",
    )
    statement = verified["statement"]
    require(statement["predicateType"] == predicate, "Unexpected attestation predicate")
    subject = {"name": path.name, "digest": {"sha256": identity(path)["sha256"]}}
    require(subject in statement["subject"], "Attestation subject mismatch")
    return verified


def verify_distribution(evidence: Evidence, kind: str, name: str, tag: str, sha: str) -> str:
    path = evidence.assets / name
    args = attestation_args(path, tag, sha)
    bundled = evidence.command(
        f"{kind}-bundle-provenance",
        args + ["--bundle", str(evidence.assets / "provenance.sigstore.json")],
        as_json=True,
    )
    verified = verified_statement(bundled, tag, sha, path, "https://slsa.dev/provenance/v1")
    online = evidence.command(f"{kind}-online-provenance", args, as_json=True)
    matches = [
        item for item in online if item["verificationResult"]["statement"] == verified["statement"]
    ]
    require(bool(matches), "Attached provenance is unavailable from GitHub")
    verified_statement(matches[:1], tag, sha, path, "https://slsa.dev/provenance/v1")
    sbom = evidence.command(
        f"{kind}-bundle-sbom",
        args
        + [
            "--bundle",
            str(evidence.assets / f"runtime-{kind}.sigstore.json"),
            "--predicate-type",
            "https://cyclonedx.org/bom",
        ],
        as_json=True,
    )
    statement = verified_statement(sbom, tag, sha, path, "https://cyclonedx.org/bom")["statement"]
    require(
        statement["predicate"] == read_json(evidence.assets / f"runtime-{kind}.cdx.json"),
        "Readable SBOM differs from signed predicate",
    )
    invocation = verified["signature"]["certificate"]["runInvocationURI"]
    require(
        re.fullmatch(re.escape(REPOSITORY_URL) + r"/actions/runs/\d+/attempts/\d+", invocation)
        is not None,
        "Unexpected release workflow invocation",
    )
    return invocation


def verify_release_run(evidence: Evidence, invocation: str, sha: str) -> None:
    run_id = invocation.split("/")[-3]
    attempt = int(invocation.split("/")[-1])
    require(1 <= attempt <= MAX_RUN_ATTEMPTS, "Release attempt exceeds verification limit")
    run = evidence.api("release-run", f"repos/{REPOSITORY}/actions/runs/{run_id}")
    require(
        run["conclusion"] == "success"
        and run["head_sha"] == sha
        and run["path"] == ".github/workflows/release.yml",
        "Release workflow failed or differs",
    )
    jobs = attempt_jobs(evidence, run_id, attempt)
    publications = [
        job for job in jobs if job["name"] == "Attest and publish the approved candidate"
    ]
    require(
        len(publications) == 1 and publications[0]["conclusion"] == "success",
        "Publication job in the signing attempt did not succeed",
    )
    evidence.report["signing_attempt"] = attempt
    build = preceding_build(evidence, run_id, attempt, jobs)
    steps = {step["name"]: step["conclusion"] for step in build["steps"]}
    for name in (
        "Scan candidate and tooling dependencies for vulnerabilities",
        "Check candidate and tooling licenses",
    ):
        require(steps.get(name) == "success", "Release scanner step did not succeed")


def attempt_jobs(evidence: Evidence, run_id: str, attempt: int) -> list[dict]:
    result = evidence.api(
        f"release-jobs-{attempt}",
        f"repos/{REPOSITORY}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100",
    )
    require(result["total_count"] == len(result["jobs"]), "Incomplete release job listing")
    return result["jobs"]


def preceding_build(evidence: Evidence, run_id: str, attempt: int, jobs: list[dict]) -> dict:
    # A publish-only rerun inherits the build's outputs from an earlier attempt.
    # Stop at the newest build job, even if it failed; never cherry-pick an older success.
    while attempt >= 1:
        builds = [job for job in jobs if job["name"] == "Validate and build the release candidate"]
        if builds:
            require(
                len(builds) == 1 and builds[0]["conclusion"] == "success",
                "Most recent build before signing did not succeed",
            )
            evidence.report["build_attempt"] = attempt
            return builds[0]
        attempt -= 1
        if attempt:
            jobs = attempt_jobs(evidence, run_id, attempt)
    raise ValueError("No build evidence at or before the signing attempt")


def pypi_files(metadata: dict, version: str, root: Path) -> list[dict]:
    require(metadata["info"]["version"] == version, "PyPI version mismatch")
    files = metadata["urls"]
    require(
        len(files) == 2
        and {item["filename"] for item in files} == set(distribution_names(version).values()),
        "Unexpected PyPI distribution set",
    )
    for item in files:
        require(item.get("yanked") is False, "PyPI distribution is yanked")
        require(
            item["digests"]["sha256"] == identity(root / item["filename"])["sha256"],
            "PyPI metadata differs from GitHub bytes",
        )
    return files


def verify_pypi(evidence: Evidence, version: str) -> None:
    metadata = fetch_bytes(
        f"https://pypi.org/pypi/best-practices-mcp/{version}/json", MAX_FILE_BYTES, {"pypi.org"}
    )
    (evidence.logs / "pypi-metadata.json").write_bytes(metadata)
    target = evidence.root / "pypi"
    target.mkdir()
    for item in pypi_files(json.loads(metadata), version, evidence.assets):
        verify_pypi_file(evidence, version, item, target)


def verify_pypi_file(evidence: Evidence, version: str, item: dict, target: Path) -> None:
    name = safe_name(item["filename"])
    destination = target / name
    destination.write_bytes(fetch_bytes(item["url"], MAX_FILE_BYTES, {"files.pythonhosted.org"}))
    require(
        identity(destination) == identity(evidence.assets / name), "PyPI downloaded bytes differ"
    )
    url = f"https://pypi.org/integrity/best-practices-mcp/{version}/{name}/provenance"
    provenance = fetch_bytes(url, MAX_FILE_BYTES, {"pypi.org"})
    path = evidence.logs / f"{name}.pypi-provenance.json"
    path.write_bytes(provenance)
    bundles = json.loads(provenance)["attestation_bundles"]
    expected = {
        "kind": "GitHub",
        "repository": REPOSITORY,
        "workflow": "release.yml",
        "environment": "pypi",
    }
    require(
        bool(bundles) and all(bundle["publisher"] == expected for bundle in bundles),
        "Unexpected PyPI publisher identity",
    )
    evidence.command(
        f"{name}-pypi-verify",
        [
            sys.executable,
            "-m",
            "pypi_attestations",
            "verify",
            "pypi",
            "--repository",
            REPOSITORY_URL,
            "--provenance-file",
            str(path),
            str(destination),
        ],
    )


def verify(evidence: Evidence, tag: str, expected_sha: str | None) -> None:
    version = normalized_version(tag)
    if expected_sha is not None:
        digest(expected_sha, 40)
    evidence.report["tools"] = {
        "python": sys.version,
        "pypi-attestations": importlib.metadata.version("pypi-attestations"),
        "gh": evidence.command("gh-version", ["gh", "--version"]).strip(),
    }
    signed = evidence.check(
        "release-attestation",
        evidence.command,
        "release-attestation",
        ["gh", "release", "verify", tag, "--repo", REPOSITORY, "--format", "json"],
    )
    sha, files = release_identity(json.loads(signed), tag, expected_sha)
    evidence.report.update(commit=sha, version=version)
    metadata = evidence.check(
        "release-metadata",
        evidence.api,
        "release-metadata",
        f"repos/{REPOSITORY}/releases/tags/{tag}",
    )
    assets = release_metadata(metadata, tag, files, version)
    evidence.check("github-assets", download_assets, evidence, tag, assets, files)
    evidence.check("manifest", verify_manifest, evidence.assets, tag, sha, version)
    evidence.check("qualification-and-scans", verify_reports, evidence.assets, version)
    invocations = {
        evidence.check(f"{kind}-attestations", verify_distribution, evidence, kind, name, tag, sha)
        for kind, name in distribution_names(version).items()
    }
    require(len(invocations) == 1, "Distributions have different release workflow invocations")
    invocation = invocations.pop()
    evidence.report["release_invocation"] = invocation
    evidence.check("release-run", verify_release_run, evidence, invocation, sha)
    evidence.check("pypi", verify_pypi, evidence, version)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("build/release-verification"))
    parser.add_argument("--expected-sha")
    args = parser.parse_args(argv)
    try:
        evidence = Evidence(args.output_dir.resolve(), args.tag, args.expected_sha)
    except (OSError, ValueError) as error:
        record_initial_failure(args.output_dir, error)
        print("Published release verification could not initialize; use a fresh output directory.")
        return 1
    try:
        verify(evidence, args.tag, args.expected_sha)
    except Exception as error:
        evidence.report.update(status="failed", error=f"{type(error).__name__}: {error}")
    else:
        evidence.report["status"] = "passed"
    evidence.report["finished_at"] = datetime.now(UTC).isoformat()
    evidence.save()
    passed = evidence.report["status"] == "passed"
    print(
        "Published release verification passed."
        if passed
        else "Published release verification failed; inspect the retained report."
    )
    return 0 if passed else 1


def record_initial_failure(root: Path, error: Exception) -> None:
    report = root / "report.json"
    if not root.is_dir() or report.is_symlink():
        return
    try:
        report.write_text(
            json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}) + "\n",
            encoding="utf-8",
        )
    except OSError:
        # A filesystem that cannot store a report must still get a safe, failing CLI result.
        return


if __name__ == "__main__":
    raise SystemExit(main())
