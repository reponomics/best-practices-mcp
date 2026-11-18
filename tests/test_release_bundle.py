"""Release evidence must remain bound to the qualified archives and commit."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("release_bundle", SCRIPTS / "release_bundle.py")
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)
SHA = "a" * 40


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "example.whl").write_bytes(b"qualified wheel")
    (dist / "example.tar.gz").write_bytes(b"qualified source")
    reports = tmp_path / "reports"
    reports.mkdir()
    for name in bundle.REQUIRED_REPORTS:
        (reports / name).write_text("{}")
    for source, _ in bundle.POLICY_INPUTS:
        path = tmp_path / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("policy input")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "status": "passed",
                "installation": {"status": "passed"},
                "version": "1.0.0",
                "artifacts": {path.name: bundle.file_identity(path) for path in dist.iterdir()},
            }
        )
    )
    evidence.with_suffix(".log").write_text("sanitized qualification log")
    monkeypatch.setattr(bundle, "git_output", lambda *args: SHA)
    monkeypatch.setattr(
        bundle,
        "verify_artifacts",
        lambda root, path: {item.name: bundle.file_identity(item) for item in path.iterdir()},
    )
    return tmp_path, dist, evidence, reports, tmp_path / "bundle"


def test_bundle_records_exact_qualified_bytes(candidate):
    bundle.assemble(*candidate, tag="v1.0.0", sha=SHA)
    output = candidate[-1]
    manifest = json.loads((output / "release.json").read_text())
    assert manifest["commit"] == SHA
    assert manifest["tag"] == "v1.0.0"
    assert manifest["artifacts"]["dist/example.whl"] == bundle.file_identity(
        candidate[1] / "example.whl"
    )
    recorded = {}
    paths = {path.name: path for path in output.rglob("*") if path.is_file()}
    for line in (output / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert bundle.file_identity(paths[name])["sha256"] == digest
        recorded[name] = digest
    assert set(recorded) == {Path(name).name for name in manifest["artifacts"]} | {"release.json"}


def test_changed_candidate_cannot_reuse_qualification(candidate):
    (candidate[1] / "example.whl").write_bytes(b"modified after testing")
    with pytest.raises(ValueError, match="differ from qualification"):
        bundle.assemble(*candidate, tag="v1.0.0", sha=SHA)
    assert not candidate[-1].exists()


def test_failed_installation_cannot_be_released(candidate):
    evidence = json.loads(candidate[2].read_text())
    evidence["installation"]["status"] = "failed"
    candidate[2].write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match="fresh-install"):
        bundle.assemble(*candidate, tag="v1.0.0", sha=SHA)


def test_wrong_commit_rejected(candidate):
    with pytest.raises(ValueError, match="checked-out commit"):
        bundle.assemble(*candidate, tag="v1.0.0", sha="b" * 40)


def test_missing_report_prevents_complete_bundle(candidate):
    (candidate[3] / "osv-licenses.json").unlink()
    with pytest.raises(ValueError, match="regular file"):
        bundle.assemble(*candidate, tag="v1.0.0", sha=SHA)
    assert not (candidate[-1] / "SHA256SUMS").exists()


def test_existing_bundle_is_not_overwritten(candidate):
    bundle.assemble(*candidate, tag="v1.0.0", sha=SHA)
    with pytest.raises(ValueError, match="must not already exist"):
        bundle.assemble(*candidate, tag="v1.0.0", sha=SHA)
