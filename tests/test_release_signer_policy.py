"""Post-publication verification must select only reviewed signer identities."""

import ast
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
VERIFY = yaml.safe_load((ROOT / ".github/workflows/verify-release.yml").read_text())
RELEASE = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
JOB = VERIFY["jobs"]["verify"]


def selector():
    step = next(
        item
        for item in JOB["steps"]
        if item["name"] == "Select the reviewed signer policy for this release"
    )
    source = step["run"].split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    module = ast.parse(source)
    module.body = [
        item
        for item in module.body
        if isinstance(item, ast.Import | ast.ImportFrom | ast.FunctionDef)
    ]
    namespace = {}
    exec(compile(module, "reviewed-release-signer", "exec"), namespace)
    return namespace["select_signer"]


@pytest.mark.parametrize("tag", ["v0.2.0-beta.3", "v0.3.0-beta.1", "v0.5.0"])
def test_legacy_releases_keep_source_signer(tag):
    assert selector()(tag, "a" * 40) == (
        "reponomics/best-practices-mcp/.github/workflows/release.yml",
        "a" * 40,
    )


@pytest.mark.parametrize("tag", ["v0.5.1", "v0.6.0-beta.1", "v1.0.0"])
def test_later_releases_require_reviewed_external_signer(tag, monkeypatch):
    for name in ("BUILDER_WORKFLOW", "BUILDER_COMMIT"):
        monkeypatch.setenv(name, JOB["env"][name])
        assert JOB["env"][name] == RELEASE["env"][name]
    assert selector()(tag, "a" * 40) == (
        JOB["env"]["BUILDER_WORKFLOW"],
        JOB["env"]["BUILDER_COMMIT"],
    )


@pytest.mark.parametrize(
    ("tag", "sha"), [("main", "a" * 40), ("v0.5.0\ninjected", "a" * 40), ("v0.5.0", "bad")]
)
def test_signer_policy_rejects_invalid_release_identity(tag, sha):
    with pytest.raises(ValueError, match="Invalid release identity"):
        selector()(tag, sha)


def test_online_and_bundle_verification_use_selected_policy():
    commands = [
        step["run"] for step in JOB["steps"] if "gh attestation verify" in step.get("run", "")
    ]
    assert len(commands) == 2
    for source in commands:
        assert source.count("gh attestation verify") == 2
        assert source.count('--signer-workflow "$SIGNER_WORKFLOW"') == 2
        assert source.count('--signer-digest "$SIGNER_COMMIT"') == 2
        assert source.count('--source-digest "$EXPECTED_SHA"') == 2
        assert source.count('--source-ref "refs/tags/$RELEASE_TAG"') == 2


@pytest.mark.skipif(sys.platform == "win32", reason="Release verifier uses bash")
@pytest.mark.parametrize("unexpected", ["", "wheel.whl", "source.tar.gz"])
def test_post_publication_checks_each_provenance_certificate(tmp_path, monkeypatch, unexpected):
    import json
    import os
    import subprocess

    assets = tmp_path / "release-verification" / "assets"
    assets.mkdir(parents=True)
    expected = {
        "workflow": {
            "repository": "https://github.com/reponomics/best-practices-mcp",
            "ref": "refs/tags/v0.6.0",
            "path": ".github/workflows/release.yml",
        }
    }
    result = {
        "verificationResult": {
            "statement": {"predicate": {"buildDefinition": {"externalParameters": expected}}},
            "signature": {
                "certificate": {
                    "buildConfigURI": "https://github.com/reponomics/best-practices-mcp/.github/workflows/release.yml@refs/tags/v0.6.0",
                    "buildConfigDigest": "a" * 40,
                }
            },
        }
    }
    (tmp_path / "result.json").write_text(json.dumps(result))
    gh_script = tmp_path / "mock gh.py"
    gh_script.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "if '--format' in sys.argv:\n"
        "    item = json.loads((Path(os.environ['RUNNER_TEMP']) / 'result.json').read_text())\n"
        "    if sys.argv[3] == os.environ['UNEXPECTED_ARTIFACT']:\n"
        "        cert = item['verificationResult']['signature']['certificate']\n"
        "        cert['buildConfigURI'] = 'unexpected'\n"
        "    print(json.dumps([item]))\n"
    )
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nexec "$TEST_PYTHON" "$TEST_GH_SCRIPT" "$@"\n')
    gh.chmod(0o755)
    for key, value in {
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "RUNNER_TEMP": str(tmp_path),
        "REPOSITORY": "reponomics/best-practices-mcp",
        "RELEASE_TAG": "v0.6.0",
        "EXPECTED_SHA": "a" * 40,
        "WHEEL": "wheel.whl",
        "SDIST": "source.tar.gz",
        "SIGNER_WORKFLOW": JOB["env"]["BUILDER_WORKFLOW"],
        "SIGNER_COMMIT": JOB["env"]["BUILDER_COMMIT"],
        "UNEXPECTED_ARTIFACT": unexpected,
        "TEST_PYTHON": sys.executable,
        "TEST_GH_SCRIPT": str(gh_script),
    }.items():
        monkeypatch.setenv(key, value)
    source = next(
        item["run"]
        for item in JOB["steps"]
        if item["name"] == "2. Verify the distributions' workflow provenance"
    )
    completed = subprocess.run(["bash", "-eo", "pipefail", "-c", source], capture_output=True)
    assert (completed.returncode == 0) is (not unexpected)
    if unexpected:
        assert b"Unexpected authenticated source workflow" in completed.stdout + completed.stderr
