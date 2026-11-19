"""Release publication must preserve candidate identity and privilege boundaries."""

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
JOBS = WORKFLOW["jobs"]


def step(job, name):
    return next(item for item in JOBS[job]["steps"] if item["name"] == name)


def python_source(block):
    return block.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]


VERIFY = python_source(step("publish", "Verify candidate identities and checksums")["run"])


def verification_namespace():
    module = ast.parse(VERIFY)
    module.body = [
        item
        for item in module.body
        if isinstance(item, ast.Import | ast.ImportFrom | ast.FunctionDef)
    ]
    namespace: dict[str, Any] = {}
    exec(compile(module, "release-candidate-verifier", "exec"), namespace)
    return namespace


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    root = tmp_path / "bundle"
    (root / "dist").mkdir(parents=True)
    (root / "reports").mkdir()
    files = {
        "dist/best_practices_mcp-0.2.0b1-py3-none-any.whl": b"wheel",
        "dist/best_practices_mcp-0.2.0b1.tar.gz": b"source",
        "reports/runtime-wheel.cdx.json": b"{}",
    }
    for name, content in files.items():
        (root / name).write_bytes(content)
    manifest = {
        "schema_version": 1,
        "tag": "v0.2.0-beta.1",
        "commit": "a" * 40,
        "version": "0.2.0b1",
        "artifacts": {
            name: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
            for name, content in files.items()
        },
    }
    (root / "release.json").write_text(json.dumps(manifest))
    sums = "".join(
        hashlib.sha256((root / name).read_bytes()).hexdigest() + "  " + Path(name).name + "\n"
        for name in sorted([*files, "release.json"], key=lambda name: Path(name).name)
    )
    (root / "SHA256SUMS").write_text(sums)
    monkeypatch.setenv("RELEASE_TAG", manifest["tag"])
    monkeypatch.setenv("GITHUB_SHA", manifest["commit"])
    return root


def test_exact_candidate_verifies(candidate):
    wheel, sdist = verification_namespace()["verify"](candidate)
    assert wheel.read_bytes() == b"wheel"
    assert sdist.read_bytes() == b"source"


def test_candidate_mutation_is_rejected(candidate):
    next((candidate / "dist").glob("*.whl")).write_bytes(b"replaced")
    with pytest.raises(ValueError, match="checksum or size"):
        verification_namespace()["verify"](candidate)


@pytest.mark.parametrize("name", ["dist/unexpected.whl", "reports/unexpected.txt"])
def test_extra_files_are_rejected(candidate, name):
    (candidate / name).write_bytes(b"extra")
    with pytest.raises(ValueError, match="Unexpected, missing"):
        verification_namespace()["verify"](candidate)


def test_missing_files_are_rejected(candidate):
    (candidate / "reports/runtime-wheel.cdx.json").unlink()
    with pytest.raises(ValueError, match="regular files"):
        verification_namespace()["verify"](candidate)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "reports/a\n::error::x"])
def test_manifest_paths_are_rejected(candidate, name):
    manifest = json.loads((candidate / "release.json").read_text())
    manifest["artifacts"] = {name: {"sha256": "0" * 64, "bytes": 0}}
    (candidate / "release.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unsafe candidate path"):
        verification_namespace()["verify"](candidate)


def test_candidate_symlink_is_rejected(candidate):
    path = candidate / "reports/runtime-wheel.cdx.json"
    path.unlink()
    try:
        path.symlink_to("../release.json")
    except OSError:
        pytest.skip("Symlink creation is unavailable")
    with pytest.raises(ValueError, match="regular files"):
        verification_namespace()["verify"](candidate)


@pytest.mark.parametrize("variable", ["RELEASE_TAG", "GITHUB_SHA"])
def test_candidate_for_another_release_is_rejected(candidate, monkeypatch, variable):
    monkeypatch.setenv(variable, "wrong")
    with pytest.raises(ValueError, match="identity|another commit"):
        verification_namespace()["verify"](candidate)


def test_checksum_manifest_is_checked(candidate):
    (candidate / "SHA256SUMS").write_text("incorrect\n")
    with pytest.raises(ValueError, match="Checksum manifest"):
        verification_namespace()["verify"](candidate)


@pytest.fixture
def signed_manifests(candidate, monkeypatch):
    if os.name == "nt":
        pytest.skip("These release workflow shell steps run on Ubuntu, not Windows")
    if not shutil.which("bash") or not shutil.which("sha256sum"):
        pytest.skip("Release verification runs on Ubuntu and requires bash and sha256sum")
    root = candidate.parent
    assets = root / "release-verification/assets"
    assets.mkdir(parents=True)
    for path in candidate.rglob("*"):
        if path.is_file():
            shutil.copyfile(path, assets / path.name)
    commands = root / "commands.jsonl"
    executable = root / "bin/gh"
    executable.parent.mkdir()
    executable.write_text('#!/bin/sh\nexec "$GH_TEST_PYTHON" "$GH_TEST_SCRIPT" "$@"\n')
    script = executable.with_suffix(".py")
    script.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['GH_TEST_LOG'], 'a') as output:\n"
        "    output.write(json.dumps(args) + '\\n')\n"
        "if Path(args[2]).name == os.environ.get('GH_TEST_REJECT'):\n"
        "    sys.exit(23)\n"
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(executable.parent) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("GH_TEST_PYTHON", sys.executable)
    monkeypatch.setenv("GH_TEST_SCRIPT", str(script))
    monkeypatch.setenv("GH_TEST_LOG", str(commands))
    monkeypatch.delenv("GH_TEST_REJECT", raising=False)
    monkeypatch.setenv("RUNNER_TEMP", str(root))
    monkeypatch.setenv("GITHUB_REPOSITORY", "reponomics/best-practices-mcp")
    monkeypatch.setenv("REPOSITORY", "reponomics/best-practices-mcp")
    monkeypatch.setenv("EXPECTED_SHA", "a" * 40)
    return root, assets, commands


def manifest_verification_source(stage):
    if stage == "before-publication":
        return step("github-release", "Verify signatures before release attachment")["run"]
    workflow = yaml.safe_load((ROOT / ".github/workflows/verify-release.yml").read_text())
    return next(
        item["run"]
        for item in workflow["jobs"]["verify"]["steps"]
        if item["name"] == "1b. Verify the signed release manifests"
    )


def run_manifest_verification(stage, root):
    return subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-e",
            "-o",
            "pipefail",
            "-c",
            manifest_verification_source(stage),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize("stage", ["before-publication", "after-publication"])
def test_manifest_signatures_require_expected_release_identity(signed_manifests, stage):
    root, _, commands = signed_manifests
    result = run_manifest_verification(stage, root)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in commands.read_text().splitlines()]
    manifests = [call for call in calls if Path(call[2]).name in {"release.json", "SHA256SUMS"}]
    assert {Path(call[2]).name for call in manifests} == {"release.json", "SHA256SUMS"}
    expected = {
        "--repo": "reponomics/best-practices-mcp",
        "--signer-workflow": "reponomics/best-practices-mcp/.github/workflows/release.yml",
        "--cert-oidc-issuer": "https://token.actions.githubusercontent.com",
        "--source-ref": "refs/tags/v0.2.0-beta.1",
        "--source-digest": "a" * 40,
    }
    for call in manifests:
        assert call[:2] == ["attestation", "verify"]
        assert "--deny-self-hosted-runners" in call
        assert Path(call[call.index("--bundle") + 1]).name == "provenance.sigstore.json"
        for flag, value in expected.items():
            assert call[call.index(flag) + 1] == value


@pytest.mark.parametrize("stage", ["before-publication", "after-publication"])
def test_manifest_verification_supports_python_path_with_spaces(
    signed_manifests, monkeypatch, stage
):
    root, _, _ = signed_manifests
    interpreter = root / "python tools/python"
    interpreter.parent.mkdir()
    interpreter.symlink_to(sys.executable)
    monkeypatch.setenv("GH_TEST_PYTHON", str(interpreter))
    result = run_manifest_verification(stage, root)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("stage", ["before-publication", "after-publication"])
@pytest.mark.parametrize("manifest", ["release.json", "SHA256SUMS"])
def test_manifest_signature_failure_stops_verification(
    signed_manifests, monkeypatch, stage, manifest
):
    root, _, commands = signed_manifests
    monkeypatch.setenv("GH_TEST_REJECT", manifest)
    result = run_manifest_verification(stage, root)
    assert result.returncode == 23
    calls = [json.loads(line) for line in commands.read_text().splitlines()]
    assert Path(calls[-1][2]).name == manifest


def test_signed_manifest_verification_rejects_changed_release_file(signed_manifests):
    root, assets, _ = signed_manifests
    (assets / "runtime-wheel.cdx.json").write_bytes(b"changed report")
    result = run_manifest_verification("after-publication", root)
    assert result.returncode != 0
    assert "runtime-wheel.cdx.json: FAILED" in result.stdout


def test_provenance_covers_distributions_and_both_manifests(candidate):
    subjects = next(item for item in JOBS["publish"]["steps"] if item.get("id") == "provenance")
    selected = {
        path.relative_to(candidate).as_posix()
        for pattern in subjects["with"]["subject-path"].splitlines()
        for path in candidate.parent.glob(pattern)
    }
    assert selected == {
        *[path.relative_to(candidate).as_posix() for path in (candidate / "dist").iterdir()],
        "release.json",
        "SHA256SUMS",
    }


def run_draft_preflight(monkeypatch, tmp_path, *, listed=None, expected_id=None, **changes):
    import subprocess

    release = {
        "id": 123,
        "tag_name": "v0.2.0-beta.1",
        "draft": True,
        "immutable": False,
        "prerelease": True,
        **changes,
    }
    monkeypatch.setenv("RELEASE_TAG", "v0.2.0-beta.1")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_REPOSITORY", "reponomics/best-practices-mcp")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    monkeypatch.delenv("RELEASE_ID", raising=False)
    if expected_id is not None:
        monkeypatch.setenv("RELEASE_ID", expected_id)

    def query(command, **kwargs):
        endpoint = command[-1]
        base = "repos/reponomics/best-practices-mcp/"
        if endpoint == base + "releases?per_page=100":
            assert command[2:4] == ["--paginate", "--slurp"]
            pages = [
                [{"id": 99, "tag_name": "v0.2.0-beta.10", "draft": False}],
                [{"id": 123, "tag_name": "v0.2.0-beta.1", "draft": True}],
            ]
            return json.dumps(pages if listed is None else listed)
        if endpoint == base + "git/ref/tags/v0.2.0-beta.1":
            return json.dumps({"object": {"type": "commit", "sha": "a" * 40}})
        assert endpoint == base + "releases/123", f"Unexpected API endpoint: {endpoint}"
        return json.dumps(release)

    monkeypatch.setattr(subprocess, "check_output", query)
    source = python_source(step("preflight", "Verify draft and tag")["run"])
    exec(compile(source, "release-draft-preflight", "exec"), {})


def test_draft_preflight_preserves_prerelease_flag(monkeypatch, tmp_path):
    run_draft_preflight(monkeypatch, tmp_path)
    assert (tmp_path / "output").read_text() == "prerelease=true\nrelease_id=123\n"


@pytest.mark.parametrize("count", [0, 2])
def test_draft_lookup_rejects_missing_or_ambiguous_tag(monkeypatch, tmp_path, count):
    listed = [[{"id": 123, "tag_name": "v0.2.0-beta.1"}] for _ in range(count)]
    with pytest.raises(SystemExit, match="exactly one"):
        run_draft_preflight(monkeypatch, tmp_path, listed=listed)


def test_finalization_rejects_replacement_draft(monkeypatch, tmp_path):
    with pytest.raises(SystemExit, match="identity changed"):
        run_draft_preflight(monkeypatch, tmp_path, expected_id="456")


def test_finalization_accepts_original_draft(monkeypatch, tmp_path):
    run_draft_preflight(monkeypatch, tmp_path, expected_id="123")


@pytest.mark.parametrize("changes", [{"draft": False}, {"immutable": True}, {"prerelease": False}])
def test_draft_preflight_rejects_published_or_mismatched_release(monkeypatch, tmp_path, changes):
    with pytest.raises(SystemExit):
        run_draft_preflight(monkeypatch, tmp_path, **changes)


def test_read_only_build_and_project_free_privileged_jobs():
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert "permissions" not in JOBS["build"]
    assert JOBS["publish"]["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }
    for name in ("preflight", "publish", "github-release"):
        assert not any("actions/checkout@" in item.get("uses", "") for item in JOBS[name]["steps"])
        assert not any("make " in item.get("run", "") for item in JOBS[name]["steps"])
    assert JOBS["publish"]["environment"]["name"] == "pypi"
    assert JOBS["github-release"]["needs"] == ["build", "publish"]
    assert JOBS["build"]["outputs"]["release_id"] == "${{ needs.preflight.outputs.release_id }}"
    assert JOBS["github-release"]["env"]["RELEASE_ID"] == "${{ needs.build.outputs.release_id }}"


def test_scan_failure_blocks_bundle_and_pypi_gets_only_archives():
    bundle = step("build", "Assemble the successful release bundle")
    assert "if" not in bundle
    publish = step("publish", "Publish unchanged distributions with PyPI attestations")
    assert publish["with"]["packages-dir"] == "bundle/dist/"
    assert publish["with"]["attestations"] is True
    vulnerability = step("build", "Scan candidate and tooling dependencies for vulnerabilities")
    licenses = step("build", "Check candidate and tooling licenses")
    for kind in ("wheel", "sdist"):
        assert f"runtime-{kind}.inventory.json" in vulnerability["with"]["scan-args"]
        assert f"runtime-{kind}.inventory.json" in licenses["with"]["scan-args"]


def test_draft_dispatch_runs_at_tag_and_does_not_publish_from_main():
    config = json.loads((ROOT / ".github/release-please-config.json").read_text())
    assert config["packages"]["."]["draft"] is True
    assert config["packages"]["."]["force-tag-creation"] is True
    release_please = yaml.safe_load((ROOT / ".github/workflows/release-please.yml").read_text())
    dispatch = release_please["jobs"]["dispatch"]
    assert dispatch["permissions"] == {"contents": "read", "actions": "write"}
    assert "'--ref', tag" in dispatch["steps"][0]["run"]
    assert "github.ref == format('refs/tags/{0}', inputs.tag)" in JOBS["preflight"]["if"]


@pytest.mark.parametrize("mutation", [None, "extra_asset", "changed_digest", "moved_tag"])
def test_final_publisher_checks_uploaded_assets_before_sealing(candidate, monkeypatch, mutation):
    import subprocess

    monkeypatch.chdir(candidate.parent)
    monkeypatch.setenv("RELEASE_ID", "123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "reponomics/best-practices-mcp")
    signatures = candidate.parent / "attestations"
    signatures.mkdir()
    for name in ("provenance", "runtime-wheel", "runtime-sdist"):
        (signatures / f"{name}.sigstore.json").write_text("signature")
    state: dict[str, Any] = {"assets": [], "uploaded": False, "published": False}

    def query(command, **kwargs):
        if command[1:3] == ["release", "upload"]:
            state["uploaded"] = True
            state["assets"] = [
                {
                    "name": Path(name).name,
                    "digest": "sha256:" + hashlib.sha256(Path(name).read_bytes()).hexdigest(),
                }
                for name in command[6:]
            ]
            if mutation == "extra_asset":
                state["assets"].append({"name": "unexpected", "digest": "sha256:bad"})
            if mutation == "changed_digest":
                state["assets"][0]["digest"] = "sha256:bad"
            return ""
        if command[1:3] == ["release", "edit"]:
            state["published"] = True
            return ""
        if "/git/ref/" in command[-1]:
            sha = "b" * 40 if state["uploaded"] and mutation == "moved_tag" else "a" * 40
            return json.dumps({"object": {"type": "commit", "sha": sha}})
        assert command[-1] == "repos/reponomics/best-practices-mcp/releases/123"
        return json.dumps(
            {
                "id": 123,
                "tag_name": "v0.2.0-beta.1",
                "draft": True,
                "immutable": False,
                "prerelease": True,
                "assets": state["assets"],
            }
        )

    monkeypatch.setattr(subprocess, "check_output", query)
    source = python_source(
        step("github-release", "Attach matching assets and publish the draft")["run"]
    )
    if mutation:
        with pytest.raises(SystemExit):
            exec(compile(source, "release-asset-publisher", "exec"), {})
    else:
        exec(compile(source, "release-asset-publisher", "exec"), {})
    assert state["uploaded"]
    assert state["published"] is (mutation is None)
