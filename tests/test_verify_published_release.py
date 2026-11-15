"""Consumer verification must fail closed without executing downloaded project code."""

import hashlib
import importlib.util
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_published_release.py"
SPEC = importlib.util.spec_from_file_location("verify_published_release", SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)
TAG = "v0.2.0-beta.3"
VERSION = "0.2.0b3"
SHA = "a" * 40
INVOCATION = f"{verifier.REPOSITORY_URL}/actions/runs/123/attempts/1"


def encoded(value):
    return json.dumps(value).encode()


def file_identity(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def signed_statement(path, predicate, value=None):
    certificate = {
        "issuer": verifier.ISSUER,
        "sourceRepositoryURI": verifier.REPOSITORY_URL,
        "sourceRepositoryDigest": SHA,
        "sourceRepositoryRef": f"refs/tags/{TAG}",
        "buildSignerURI": f"https://github.com/{verifier.WORKFLOW}@refs/tags/{TAG}",
        "runnerEnvironment": "github-hosted",
        "runInvocationURI": INVOCATION,
    }
    return [
        {
            "verificationResult": {
                "signature": {"certificate": certificate},
                "statement": {
                    "predicateType": predicate,
                    "subject": [
                        {"name": path.name, "digest": {"sha256": verifier.identity(path)["sha256"]}}
                    ],
                    "predicate": value,
                },
            }
        }
    ]


@pytest.fixture
def publication(tmp_path, monkeypatch):
    names = verifier.distribution_names(VERSION)
    files = {name: b"{}" for name in verifier.REPORT_NAMES | verifier.SIGNATURES}
    files.update({name: kind.encode() for kind, name in names.items()})
    files["qualification.json"] = encoded(
        {
            "status": "passed",
            "version": VERSION,
            "installation": {"status": "passed"},
            "artifacts": {name: file_identity(files[name]) for name in names.values()},
        }
    )
    files["osv-vulnerabilities.sarif"] = encoded(
        {
            "runs": [
                {
                    "tool": {"driver": {"name": "osv-scanner"}},
                    "results": [],
                }
            ]
        }
    )
    files["osv-licenses.json"] = encoded(
        {
            "results": [{"packages": []}],
            "experimental_config": {"licenses": {"allowlist": ["MIT"]}},
        }
    )
    manifest = {
        "schema_version": 1,
        "tag": TAG,
        "version": VERSION,
        "commit": SHA,
        "artifacts": {
            f"{'dist' if name in names.values() else 'reports'}/{name}": file_identity(content)
            for name, content in files.items()
            if name not in verifier.SIGNATURES
        },
    }
    files["release.json"] = encoded(manifest)
    files["SHA256SUMS"] = "".join(
        f"{file_identity(data)['sha256']}  {name}\n"
        for name, data in sorted(files.items())
        if name not in verifier.SIGNATURES
    ).encode()
    signed = {
        "verificationResult": {
            "statement": {
                "predicateType": "https://in-toto.io/attestation/release/v0.2",
                "predicate": {"repository": verifier.REPOSITORY, "tag": TAG},
                "subject": [
                    {"uri": f"pkg:github/{verifier.REPOSITORY}@{TAG}", "digest": {"sha1": SHA}}
                ]
                + [
                    {"name": name, "digest": {"sha256": file_identity(data)["sha256"]}}
                    for name, data in files.items()
                ],
            }
        }
    }
    metadata = {
        "tag_name": TAG,
        "draft": False,
        "immutable": True,
        "prerelease": True,
        "assets": [
            {
                "name": name,
                "size": len(data),
                "browser_download_url": f"{verifier.REPOSITORY_URL}/releases/download/{TAG}/{name}",
            }
            for name, data in files.items()
        ],
    }
    pypi = {
        "info": {"version": VERSION},
        "urls": [
            {
                "filename": name,
                "url": f"https://files.pythonhosted.org/{name}",
                "yanked": False,
                "digests": {"sha256": file_identity(files[name])["sha256"]},
            }
            for name in names.values()
        ],
    }
    publisher = {
        "kind": "GitHub",
        "repository": verifier.REPOSITORY,
        "workflow": "release.yml",
        "environment": "pypi",
    }
    provenance = {"attestation_bundles": [{"publisher": publisher}]}
    urls = {asset["browser_download_url"]: files[asset["name"]] for asset in metadata["assets"]}
    urls[f"https://pypi.org/pypi/best-practices-mcp/{VERSION}/json"] = encoded(pypi)
    for item in pypi["urls"]:
        urls[item["url"]] = files[item["filename"]]
        urls[
            f"https://pypi.org/integrity/best-practices-mcp/{VERSION}/{item['filename']}/provenance"
        ] = encoded(provenance)
    jobs = {
        "total_count": 2,
        "jobs": [
            {
                "name": "Validate and build the release candidate",
                "conclusion": "success",
                "steps": [
                    {"name": name, "conclusion": "success"}
                    for name in [
                        "Scan candidate and tooling dependencies for vulnerabilities",
                        "Check candidate and tooling licenses",
                    ]
                ],
            },
            {
                "name": "Attest and publish the approved candidate",
                "conclusion": "success",
                "steps": [],
            },
        ],
    }
    commands = []

    def command(self, label, args, *, as_json=False):
        commands.append((label, args))
        if label == "gh-version":
            return "gh fixture"
        if label == "release-attestation":
            return json.dumps(signed)
        if label.endswith("-bundle-sbom"):
            return signed_statement(Path(args[3]), "https://cyclonedx.org/bom", {})
        if label.endswith("-provenance"):
            return signed_statement(Path(args[3]), "https://slsa.dev/provenance/v1")
        return "OK"

    def api(self, label, endpoint):
        if label == "release-metadata":
            return metadata
        if label == "release-run":
            return {
                "conclusion": "success",
                "head_sha": SHA,
                "path": ".github/workflows/release.yml",
            }
        assert label.startswith("release-jobs-")
        return jobs

    monkeypatch.setattr(verifier.Evidence, "command", command)
    monkeypatch.setattr(verifier.Evidence, "api", api)
    monkeypatch.setattr(verifier, "fetch_bytes", lambda url, limit, hosts: urls[url])
    monkeypatch.setattr(verifier.importlib.metadata, "version", lambda name: "0.0.31")
    return {
        "output": tmp_path / "verification",
        "files": files,
        "metadata": metadata,
        "urls": urls,
        "jobs": jobs,
        "signed": signed,
        "commands": commands,
    }


def execute(publication, *extra):
    result = verifier.main(["--tag", TAG, "--output-dir", str(publication["output"]), *extra])
    report = json.loads((publication["output"] / "report.json").read_text())
    return result, report


def test_public_bytes_and_every_asset_are_verified(publication):
    result, report = execute(publication, "--expected-sha", SHA)
    assert result == 0 and report["status"] == "passed"
    assert all(check["status"] == "passed" for check in report["checks"])
    assert report["commit"] == SHA and report["release_invocation"] == INVOCATION
    labels = [label for label, _ in publication["commands"]]
    assert len([name for name in labels if name.startswith("release-asset-")]) == 31
    for label, args in publication["commands"]:
        if args[:3] == ["gh", "attestation", "verify"]:
            assert args[args.index("--source-digest") + 1] == SHA
            assert args[args.index("--cert-oidc-issuer") + 1] == verifier.ISSUER
            assert "--deny-self-hosted-runners" in args
        if label.endswith("-pypi-verify"):
            assert "--provenance-file" in args
            assert Path(args[-1]).parent.name == "pypi"
            assert Path(args[-1]).read_bytes() == publication["files"][Path(args[-1]).name]
        assert "pip" not in args and "install" not in args


def test_initial_report_is_replaced(publication):
    publication["output"].mkdir()
    (publication["output"] / "report.json").write_text('{"status":"not_started"}')
    assert execute(publication)[0] == 0


def test_old_downloads_cannot_be_reused(publication):
    publication["output"].mkdir()
    (publication["output"] / "old.whl").write_bytes(b"stale")
    result, report = execute(publication)
    assert result == 1 and "fresh" in report["error"]


def test_expected_commit_mismatch_fails_before_download(publication):
    result, report = execute(publication, "--expected-sha", "b" * 40)
    assert result == 1 and "commit mismatch" in report["error"]
    assert not list((publication["output"] / "github").iterdir())


@pytest.mark.parametrize("field,value", [("immutable", False), ("draft", True)])
def test_unpublished_or_mutable_release_fails(publication, field, value):
    publication["metadata"][field] = value
    assert execute(publication)[0] == 1


def test_missing_asset_fails(publication):
    publication["metadata"]["assets"].pop()
    result, report = execute(publication)
    assert result == 1 and "missing release assets" in report["error"]


def test_tampered_github_asset_fails(publication):
    url = publication["metadata"]["assets"][0]["browser_download_url"]
    publication["urls"][url] = b"tampered"
    result, report = execute(publication)
    assert result == 1 and report["checks"][-1]["name"] == "github-assets"


def test_actual_pypi_bytes_are_compared(publication):
    name = verifier.distribution_names(VERSION)["wheel"]
    publication["urls"][f"https://files.pythonhosted.org/{name}"] = b"different public bytes"
    result, report = execute(publication)
    assert result == 1 and "PyPI downloaded bytes differ" in report["error"]


def test_wrong_pypi_publisher_fails(publication):
    name = verifier.distribution_names(VERSION)["wheel"]
    url = f"https://pypi.org/integrity/best-practices-mcp/{VERSION}/{name}/provenance"
    provenance = json.loads(publication["urls"][url])
    provenance["attestation_bundles"][0]["publisher"]["environment"] = "unapproved"
    publication["urls"][url] = encoded(provenance)
    result, report = execute(publication)
    assert result == 1 and "publisher identity" in report["error"]


def test_failed_release_scan_is_not_mistaken_for_empty_success(publication):
    publication["jobs"]["jobs"][0]["steps"][0]["conclusion"] = "failure"
    result, report = execute(publication)
    assert result == 1 and "scanner step" in report["error"]


def test_successful_finalization_rerun_preserves_original_build_evidence(publication, monkeypatch):
    # The signature still refers to attempt 1, whose finalization failed. The current
    # run is successful after retrying finalization, with the original candidate intact.
    publication["jobs"]["jobs"].append(
        {
            "name": "Attach evidence and publish the immutable GitHub release",
            "conclusion": "failure",
            "steps": [],
        }
    )
    publication["jobs"]["total_count"] = 3
    original = verifier.Evidence.api
    endpoints = []

    def api(self, label, endpoint):
        endpoints.append(endpoint)
        return original(self, label, endpoint)

    monkeypatch.setattr(verifier.Evidence, "api", api)
    assert execute(publication)[0] == 0
    assert f"repos/{verifier.REPOSITORY}/actions/runs/123" in endpoints
    assert f"repos/{verifier.REPOSITORY}/actions/runs/123/attempts/1/jobs?per_page=100" in endpoints


def test_publish_only_retry_uses_preceding_build_and_scan_evidence(publication, monkeypatch):
    original = verifier.Evidence.api
    queries = []

    def api(self, label, endpoint):
        queries.append(endpoint)
        if label == "release-jobs-2":
            return {"total_count": 1, "jobs": [publication["jobs"]["jobs"][1]]}
        return original(self, label, endpoint)

    monkeypatch.setattr(verifier.Evidence, "api", api)
    evidence = verifier.Evidence(publication["output"], TAG, SHA)
    verifier.verify_release_run(evidence, INVOCATION.replace("attempts/1", "attempts/2"), SHA)
    assert evidence.report["signing_attempt"] == 2
    assert evidence.report["build_attempt"] == 1
    assert len(queries) == 3


def test_retry_does_not_skip_a_failed_newer_build(publication, monkeypatch):
    original = verifier.Evidence.api
    queries = []
    publication["jobs"]["jobs"][0]["conclusion"] = "failure"

    def api(self, label, endpoint):
        queries.append(endpoint)
        if label == "release-jobs-3":
            return {"total_count": 1, "jobs": [publication["jobs"]["jobs"][1]]}
        return original(self, label, endpoint)

    monkeypatch.setattr(verifier.Evidence, "api", api)
    evidence = verifier.Evidence(publication["output"], TAG, SHA)
    with pytest.raises(ValueError, match="Most recent build"):
        verifier.verify_release_run(evidence, INVOCATION.replace("attempts/1", "attempts/3"), SHA)
    assert not any("/attempts/1/" in query for query in queries)


def test_failed_publish_at_signature_attempt_is_not_accepted(publication):
    publication["jobs"]["jobs"][1]["conclusion"] = "failure"
    evidence = verifier.Evidence(publication["output"], TAG, SHA)
    with pytest.raises(ValueError, match="Publication job in the signing attempt"):
        verifier.verify_release_run(evidence, INVOCATION, SHA)


def test_unbounded_attempt_history_is_rejected(publication):
    evidence = verifier.Evidence(publication["output"], TAG, SHA)
    with pytest.raises(ValueError, match="verification limit"):
        verifier.verify_release_run(evidence, INVOCATION.replace("attempts/1", "attempts/999"), SHA)


def test_multiple_online_attestations_are_allowed_when_bundle_is_available(
    publication, monkeypatch
):
    original = verifier.Evidence.command

    def command(self, label, args, *, as_json=False):
        result = original(self, label, args, as_json=as_json)
        if label.endswith("-online-provenance"):
            extra = json.loads(json.dumps(result[0]))
            extra["verificationResult"]["statement"]["predicate"] = {"other-attempt": True}
            return [extra, *result]
        return result

    monkeypatch.setattr(verifier.Evidence, "command", command)
    assert execute(publication)[0] == 0


def test_attached_provenance_must_be_publicly_available(publication, monkeypatch):
    original = verifier.Evidence.command

    def command(self, label, args, *, as_json=False):
        result = original(self, label, args, as_json=as_json)
        if label.endswith("-online-provenance"):
            result[0]["verificationResult"]["statement"]["predicate"] = {"different": True}
        return result

    monkeypatch.setattr(verifier.Evidence, "command", command)
    result, report = execute(publication)
    assert result == 1 and "provenance is unavailable" in report["error"]


def test_license_violations_in_retained_report_are_rejected(publication):
    assert execute(publication)[0] == 0
    root = publication["output"] / "github"
    path = root / "osv-licenses.json"
    report = json.loads(path.read_text())
    report["results"][0]["packages"] = [{"license_violations": ["unapproved"]}]
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="License violations"):
        verifier.verify_reports(root, VERSION)


def test_signed_manifest_does_not_excuse_changed_local_bytes(publication):
    assert execute(publication)[0] == 0
    root = publication["output"] / "github"
    (root / "qualification.log").write_bytes(b"replaced")
    with pytest.raises(ValueError, match="checksum or size"):
        verifier.verify_manifest(root, TAG, SHA, VERSION)


@pytest.mark.parametrize(
    "field,value",
    [
        ("issuer", "https://attacker.example"),
        ("sourceRepositoryDigest", "b" * 40),
        ("sourceRepositoryRef", "refs/heads/main"),
        ("runnerEnvironment", "self-hosted"),
    ],
)
def test_verified_certificate_must_match_policy(tmp_path, field, value):
    path = tmp_path / "artifact.whl"
    path.write_bytes(b"artifact")
    result = signed_statement(path, "https://slsa.dev/provenance/v1")
    result[0]["verificationResult"]["signature"]["certificate"][field] = value
    with pytest.raises(ValueError, match="certificate identity"):
        verifier.verified_statement(result, TAG, SHA, path, "https://slsa.dev/provenance/v1")


def test_readable_sbom_must_equal_signed_predicate(publication, monkeypatch):
    original = verifier.Evidence.command

    def command(self, label, args, *, as_json=False):
        result = original(self, label, args, as_json=as_json)
        if label.endswith("-bundle-sbom"):
            result[0]["verificationResult"]["statement"]["predicate"] = {"changed": True}
        return result

    monkeypatch.setattr(verifier.Evidence, "command", command)
    result, report = execute(publication)
    assert result == 1 and "Readable SBOM differs" in report["error"]


def test_manifest_path_cannot_escape_asset_directory():
    with pytest.raises(ValueError, match="manifest path"):
        verifier.manifest_inventory({"artifacts": {"reports/../secret": {}}}, {})


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a\n::error::x", "a\\b", "--option"])
def test_unsafe_asset_names_are_rejected(name):
    with pytest.raises(ValueError, match="Unsafe"):
        verifier.safe_name(name)


def test_transport_retries_are_bounded(monkeypatch):
    calls = []
    monkeypatch.setattr(verifier.time, "sleep", lambda seconds: None)

    def fail(*args):
        calls.append(args)
        raise urllib.error.HTTPError(args[0], 503, "unavailable", {}, None)

    monkeypatch.setattr(verifier, "read_response", fail)
    with pytest.raises(urllib.error.HTTPError):
        verifier.fetch_bytes("https://pypi.org/test", 10, {"pypi.org"})
    assert len(calls) == 3


def test_bad_content_is_never_retried(monkeypatch):
    calls = []

    def fail(*args):
        calls.append(args)
        raise ValueError("Downloaded content exceeds limit")

    monkeypatch.setattr(verifier, "read_response", fail)
    with pytest.raises(ValueError):
        verifier.fetch_bytes("https://pypi.org/test", 10, {"pypi.org"})
    assert len(calls) == 1


@pytest.mark.parametrize("destination", ["https://attacker.example/file", "http://pypi.org/file"])
def test_redirects_are_checked_before_following_them(destination):
    request = urllib.request.Request("https://pypi.org/file")
    with pytest.raises(ValueError, match="redirect host"):
        verifier.AllowedRedirects({"pypi.org"}).redirect_request(
            request, None, 302, "redirect", {}, destination
        )


def test_timeout_retains_failed_report_and_partial_output(tmp_path, monkeypatch, capsys):
    def run(args, *, stdout, stderr, **kwargs):
        stdout.write(b"::error::untrusted-output")
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(verifier.subprocess, "run", run)
    monkeypatch.setattr(verifier.importlib.metadata, "version", lambda name: "0.0.31")
    output = tmp_path / "timeout"
    assert verifier.main(["--tag", TAG, "--output-dir", str(output)]) == 1
    assert "::error::" not in capsys.readouterr().out
    assert json.loads((output / "report.json").read_text())["status"] == "failed"
    assert (output / "evidence/gh-version.stdout").read_bytes() == b"::error::untrusted-output"
