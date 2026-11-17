"""Release publication must preserve candidate identity and privilege boundaries."""

import ast
import hashlib
import json
import re
import sys
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


def test_source_build_is_read_only_and_shared_signers_are_pinned():
    assert WORKFLOW["permissions"] == {"contents": "read"}
    build = JOBS["build"]
    assert "uses" not in build
    assert build["permissions"] == {"contents": "read"}
    assert build["runs-on"] == "ubuntu-24.04"
    checkout = next(item for item in build["steps"] if "actions/checkout@" in item.get("uses", ""))
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["persist-credentials"] is False
    assert any("make validate" in item.get("run", "") for item in build["steps"])
    assert any(
        "make release-build release-qualify RELEASE_SBOM=1" in item.get("run", "")
        for item in build["steps"]
    )
    assert not any("actions/attest@" in item.get("uses", "") for item in build["steps"])
    for item in build["steps"]:
        if "astral-sh/setup-uv@" in item.get("uses", ""):
            assert item["with"]["enable-cache"] is False
        if "actions/setup-go@" in item.get("uses", ""):
            assert item["with"]["cache"] is False

    for job, name, subject, sbom in (
        ("provenance", "provenance", "dist/*", None),
        (
            "wheel-sbom",
            "runtime-wheel",
            "${{ needs.build.outputs.wheel }}",
            "reports/runtime-wheel.cdx.json",
        ),
        (
            "sdist-sbom",
            "runtime-sdist",
            "${{ needs.build.outputs.sdist }}",
            "reports/runtime-sdist.cdx.json",
        ),
    ):
        signer = JOBS[job]
        workflow, commit = signer["uses"].split("@")
        assert workflow == "reponomics/release-infrastructure/.github/workflows/attest.yml"
        assert re.fullmatch(r"[0-9a-f]{40}", commit)
        assert WORKFLOW["env"]["BUILDER_WORKFLOW"] == workflow
        assert WORKFLOW["env"]["BUILDER_COMMIT"] == commit
        assert signer["permissions"] == {
            "contents": "read",
            "id-token": "write",
            "attestations": "write",
        }
        assert signer["with"]["artifact-id"] == "${{ needs.build.outputs.candidate }}"
        assert signer["with"]["attestation-name"] == name
        assert signer["with"]["subject-path"] == subject
        assert signer["with"].get("sbom-path") == sbom
        assert "secrets" not in signer


def test_privileged_publication_jobs_do_not_execute_project_code():
    assert JOBS["publish"]["permissions"] == {"contents": "read", "id-token": "write"}
    for name in ("preflight", "publish", "github-release"):
        assert not any("actions/checkout@" in item.get("uses", "") for item in JOBS[name]["steps"])
        assert not any("make " in item.get("run", "") for item in JOBS[name]["steps"])
        assert not any("actions/attest@" in item.get("uses", "") for item in JOBS[name]["steps"])
    assert JOBS["publish"]["environment"]["name"] == "pypi"
    assert {"preflight", "build", "publish", "provenance", "wheel-sbom", "sdist-sbom"} <= set(
        JOBS["github-release"]["needs"]
    )
    assert {"build", "provenance", "wheel-sbom", "sdist-sbom"} <= set(JOBS["publish"]["needs"])
    assert (
        JOBS["github-release"]["env"]["RELEASE_ID"] == "${{ needs.preflight.outputs.release_id }}"
    )


def test_exact_external_artifacts_verified_before_pypi_upload():
    publish = step("publish", "Publish unchanged distributions with PyPI attestations")
    assert publish["with"]["packages-dir"] == "bundle/dist/"
    assert publish["with"]["attestations"] is True
    assert step("publish", "Download this run's exact candidate")["with"]["artifact-ids"] == (
        "${{ needs.build.outputs.candidate }}"
    )
    for job in ("publish", "github-release"):
        download = step(job, "Download this run's signed bundles")["with"]
        ids = download["artifact-ids"]
        assert set(re.findall(r"needs\.([a-z-]+)\.outputs\.attestations", ids)) == {
            "provenance",
            "wheel-sbom",
            "sdist-sbom",
        }
        assert download["merge-multiple"] is True
    names = [item["name"] for item in JOBS["publish"]["steps"]]
    assert names.index("Verify reviewed builder signatures before publication") < names.index(
        "Publish unchanged distributions with PyPI attestations"
    )
    assert (
        step("publish", "Verify reviewed builder signatures before publication")["run"]
        == (step("github-release", "Verify signatures before release attachment")["run"])
    )


@pytest.mark.skipif(sys.platform == "win32", reason="Release verification runs in bash on Linux")
@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "workflow",
        "repository",
        "ref",
        "parameters",
        "provenance_certificate_workflow",
        "provenance_certificate_digest",
        "sbom_certificate_workflow",
        "sbom_certificate_digest",
    ],
)
def test_signature_verification_binds_builder_and_source(
    candidate, monkeypatch, tmp_path, mutation
):
    import subprocess

    gh = tmp_path / "gh"
    gh.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" >> "$GH_CALLS"\n'
        'case " $* " in\n'
        '  *" --predicate-type https://cyclonedx.org/bom "*) cat "$GH_SBOM_RESULT" ;;\n'
        '  *) cat "$GH_RESULT" ;;\n'
        "esac\n"
    )
    gh.chmod(0o755)
    import os

    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("GH_CALLS", str(tmp_path / "calls"))
    monkeypatch.setenv("GITHUB_REPOSITORY", "reponomics/best-practices-mcp")
    monkeypatch.setenv("BUILDER_WORKFLOW", WORKFLOW["env"]["BUILDER_WORKFLOW"])
    monkeypatch.setenv("BUILDER_COMMIT", WORKFLOW["env"]["BUILDER_COMMIT"])
    parameters = {
        "workflow": {
            "repository": "https://github.com/reponomics/best-practices-mcp",
            "ref": "refs/tags/v0.2.0-beta.1",
            "path": ".github/workflows/release.yml",
        }
    }
    mutations = {
        "workflow": {"path": ".github/workflows/unexpected.yml"},
        "repository": {"repository": "https://github.com/another/project"},
        "ref": {"ref": "refs/heads/main"},
    }
    parameters["workflow"].update(mutations.get(mutation, {}))
    if mutation == "parameters":
        parameters["inputs"] = {"compiler-flags": "unrecorded-build-control"}
    certificate = {
        "buildConfigURI": "https://github.com/reponomics/best-practices-mcp/.github/workflows/release.yml@refs/tags/v0.2.0-beta.1",
        "buildConfigDigest": "a" * 40,
    }
    certificate_mutations = {
        "provenance_certificate_workflow": {
            "buildConfigURI": "https://github.com/reponomics/best-practices-mcp/.github/workflows/unexpected.yml@refs/tags/v0.2.0-beta.1"
        },
        "provenance_certificate_digest": {"buildConfigDigest": "b" * 40},
    }
    provenance_certificate = {**certificate, **certificate_mutations.get(mutation, {})}
    sbom_mutations = {
        "sbom_certificate_workflow": {
            "buildConfigURI": "https://github.com/reponomics/best-practices-mcp/.github/workflows/unexpected.yml@refs/tags/v0.2.0-beta.1"
        },
        "sbom_certificate_digest": {"buildConfigDigest": "b" * 40},
    }
    sbom_certificate = {**certificate, **sbom_mutations.get(mutation, {})}
    sbom_result = tmp_path / "gh-sbom-result.json"
    sbom_result.write_text(
        json.dumps(
            [
                {
                    "verificationResult": {"signature": {"certificate": sbom_certificate}},
                }
            ]
        )
    )
    monkeypatch.setenv("GH_SBOM_RESULT", str(sbom_result))
    result = tmp_path / "gh-result.json"
    result.write_text(
        json.dumps(
            [
                {
                    "verificationResult": {
                        "signature": {"certificate": provenance_certificate},
                        "statement": {
                            "predicate": {"buildDefinition": {"externalParameters": parameters}}
                        },
                    }
                }
            ]
        )
    )
    monkeypatch.setenv("GH_RESULT", str(result))
    source = step("publish", "Verify reviewed builder signatures before publication")["run"]
    if mutation:
        failed = subprocess.run(["bash", "-eo", "pipefail", "-c", source], cwd=candidate.parent)
        assert failed.returncode != 0
        return
    subprocess.run(["bash", "-eo", "pipefail", "-c", source], cwd=candidate.parent, check=True)
    args = (tmp_path / "calls").read_text().splitlines()
    assert args.count("verify") == 4
    for flag, value in {
        "--signer-workflow": WORKFLOW["env"]["BUILDER_WORKFLOW"],
        "--signer-digest": WORKFLOW["env"]["BUILDER_COMMIT"],
        "--repo": "reponomics/best-practices-mcp",
        "--source-ref": "refs/tags/v0.2.0-beta.1",
        "--source-digest": "a" * 40,
        "--cert-oidc-issuer": "https://token.actions.githubusercontent.com",
    }.items():
        assert args.count(flag) == 4
        assert all(args[i + 1] == value for i, arg in enumerate(args) if arg == flag)
    assert args.count("--deny-self-hosted-runners") == 4
    gh.write_text("#!/bin/sh\nexit 1\n")
    failed = subprocess.run(["bash", "-eo", "pipefail", "-c", source], cwd=candidate.parent)
    assert failed.returncode == 1


def test_draft_dispatch_runs_at_tag_and_does_not_publish_from_main():
    config = json.loads((ROOT / ".github/release-please-config.json").read_text())
    assert config["packages"]["."]["draft"] is True
    assert config["packages"]["."]["force-tag-creation"] is True
    release_please = yaml.safe_load((ROOT / ".github/workflows/release-please.yml").read_text())
    dispatch = release_please["jobs"]["dispatch"]
    assert dispatch["permissions"] == {"contents": "read", "actions": "write"}
    assert "'--ref', tag" in dispatch["steps"][0]["run"]
    assert "startsWith(github.ref, 'refs/tags/')" in JOBS["preflight"]["if"]
    triggers = WORKFLOW.get("on", WORKFLOW.get(True))
    assert not (triggers["workflow_dispatch"] or {}).get("inputs")
    assert WORKFLOW["env"]["RELEASE_TAG"] == "${{ github.ref_name }}"
    assert "tag=" not in dispatch["steps"][0]["run"]


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
