"""Release publication must preserve candidate identity and privilege boundaries."""

import ast
import hashlib
import json
from pathlib import Path

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
    namespace = {}
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
    state = {"assets": [], "uploaded": False, "published": False}

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
