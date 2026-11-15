"""Release candidates must preserve identity, notices and exact uploaded bytes."""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("release_check", ROOT / "scripts/release_check.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples/host.py").write_text("# reference host\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT project notice\n", encoding="utf-8")
    (tmp_path / "THIRD_PARTY_NOTICES.md").write_text("Upstream notices\n", encoding="utf-8")
    upstream = tmp_path / release.UPSTREAM_NOTICE
    upstream.parent.mkdir(parents=True)
    upstream.write_text("BadgeApp notice\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="best-practices-mcp"\nversion="0.1.0b1"\n'
        'requires-python=">=3.11"\nlicense="MIT"\n'
        'license-files=["LICENSE","THIRD_PARTY_NOTICES.md",'
        f'"{release.UPSTREAM_NOTICE}"]\n',
        encoding="utf-8",
    )
    (tmp_path / ".github/.release-please-manifest.json").write_text(
        '{".":"0.1.0-beta.1"}', encoding="utf-8"
    )
    return tmp_path


def metadata(root, version="0.1.0b1"):
    notices = release.license_paths(root, release.project_metadata(root))
    return (
        "Metadata-Version: 2.4\nName: best-practices-mcp\n"
        f"Version: {version}\nRequires-Python: >=3.11\nLicense-Expression: MIT\n"
        "Description-Content-Type: text/markdown\n"
        + "".join(f"License-File: {path}\n" for path in sorted(notices))
        + "\n# Package description\n"
    ).encode()


def archive_files(root):
    info = "best_practices_mcp-0.1.0b1.dist-info"
    wheel = {
        info + "/METADATA": metadata(root),
        "best_practices_mcp/__init__.py": b"# package\n",
        "best_practices_mcp/data/BADGEAPP-LICENSE.txt": (
            root / release.UPSTREAM_NOTICE
        ).read_bytes(),
    }
    for path in release.license_paths(root, release.project_metadata(root)):
        wheel[info + "/licenses/" + path] = (root / path).read_bytes()
    sdist = {"PKG-INFO": metadata(root)}
    for path in release.license_paths(root, release.project_metadata(root)) | {
        "pyproject.toml",
        "examples/host.py",
    }:
        sdist[path] = (root / path).read_bytes()
    return wheel, {"best_practices_mcp-0.1.0b1/" + name: data for name, data in sdist.items()}


def write_archives(root, wheel, sdist):
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    with ZipFile(dist / "best_practices_mcp-0.1.0b1-py3-none-any.whl", "w") as archive:
        for name, data in wheel.items():
            archive.writestr(name, data)
    with tarfile.open(dist / "best_practices_mcp-0.1.0b1.tar.gz", "w:gz") as archive:
        for name, data in sdist.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return dist


def test_beta_identity_accepts_normalized_package_and_semver_tag(project):
    version = release.validate_source(project, "v0.1.0-beta.1", True)
    assert str(version) == "0.1.0b1"
    path = project / "pyproject.toml"
    path.write_text(path.read_text().replace("0.1.0b1", "0.1.0-beta.1"))
    assert release.validate_source(project, "v0.1.0-beta.1", True) == version


def test_stable_transition_requires_new_version_and_stable_flag(project):
    path = project / "pyproject.toml"
    path.write_text(path.read_text().replace("0.1.0b1", "0.1.0"))
    (project / ".github/.release-please-manifest.json").write_text('{".":"0.1.0"}')
    assert str(release.validate_source(project, "v0.1.0", False)) == "0.1.0"
    with pytest.raises(ValueError, match="prerelease flag"):
        release.validate_source(project, "v0.1.0", True)


@pytest.mark.parametrize(
    "tag", ["v0.1.0", "v0.1.0-beta.2", "v1.0.0", "v01.0.0", "v0.1.0b1", "main"]
)
def test_wrong_or_unsupported_release_identity_fails(project, tag):
    with pytest.raises(ValueError):
        release.validate_source(project, tag, True)


def test_unreleased_bootstrap_manifest_cannot_authorize_publication(project):
    (project / ".github/.release-please-manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="must agree"):
        release.validate_source(project, "v0.1.0-beta.1", True)


def test_beta_cannot_be_published_with_stable_flag(project):
    with pytest.raises(ValueError, match="prerelease flag"):
        release.validate_source(project, "v0.1.0-beta.1", False)


def test_release_git_identity_must_match_event_tag_and_main_ancestry(tmp_path):
    def git(*args):
        return subprocess.check_output(
            ["git", "-c", "tag.gpgsign=false", "-c", "commit.gpgsign=false", *args],
            cwd=tmp_path,
            text=True,
            timeout=20,
            env={
                **os.environ,
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_EDITOR": "true",
                "GIT_TERMINAL_PROMPT": "0",
            },
        ).strip()

    git("init", "--initial-branch=main")
    git("config", "user.name", "Release test")
    git("config", "user.email", "release@example.invalid")
    git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "Initial commit")
    head = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", head)
    git("tag", "v0.1.0-beta.1")
    assert release.validate_git(tmp_path, "v0.1.0-beta.1", head) == head
    with pytest.raises(ValueError, match="release event"):
        release.validate_git(tmp_path, "v0.1.0-beta.1", "0" * 40)
    git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "feat: unreleased")
    ahead = git("rev-parse", "HEAD")
    git("tag", "v0.1.0-beta.2")
    with pytest.raises(subprocess.CalledProcessError):
        release.validate_git(tmp_path, "v0.1.0-beta.2", ahead)


def test_archives_include_exact_notices_and_record_byte_hashes(project):
    wheel, sdist = archive_files(project)
    dist = write_archives(project, wheel, sdist)
    hashes = release.verify_artifacts(project, dist)
    assert len(hashes) == 2
    assert all(len(value["sha256"]) == 64 and value["bytes"] > 0 for value in hashes.values())


@pytest.mark.parametrize("notice", ["LICENSE", "THIRD_PARTY_NOTICES.md", release.UPSTREAM_NOTICE])
def test_upstream_notice_does_not_substitute_for_project_or_other_notices(project, notice):
    wheel, sdist = archive_files(project)
    path = "best_practices_mcp-0.1.0b1.dist-info/licenses/" + notice
    del wheel[path]
    dist = write_archives(project, wheel, sdist)
    with pytest.raises(ValueError, match="license|License"):
        release.verify_artifacts(project, dist)


def test_changed_upstream_notice_fails(project):
    wheel, sdist = archive_files(project)
    wheel["best_practices_mcp/data/BADGEAPP-LICENSE.txt"] = b"incomplete notice"
    with pytest.raises(ValueError, match="BadgeApp notice"):
        release.verify_artifacts(project, write_archives(project, wheel, sdist))


def test_sdist_must_preserve_reference_host_and_project_notice(project):
    wheel, sdist = archive_files(project)
    del sdist["best_practices_mcp-0.1.0b1/examples/host.py"]
    with pytest.raises(ValueError, match="examples/host.py"):
        release.verify_artifacts(project, write_archives(project, wheel, sdist))


def test_distribution_version_must_match_source(project):
    wheel, sdist = archive_files(project)
    wheel["best_practices_mcp-0.1.0b1.dist-info/METADATA"] = metadata(project, "0.1.0")
    with pytest.raises(ValueError, match="version"):
        release.verify_artifacts(project, write_archives(project, wheel, sdist))


@pytest.mark.parametrize(
    "name", ["INTERNAL/draft.json", "venv/bin/python", ".venv/bin/python", "../secret", "/absolute"]
)
def test_private_or_unsafe_archive_members_fail(project, name):
    wheel, sdist = archive_files(project)
    wheel[name] = b"not for distribution"
    with pytest.raises(ValueError, match="path"):
        release.verify_artifacts(project, write_archives(project, wheel, sdist))


def test_unexpected_wheel_top_level_fails(project):
    wheel, sdist = archive_files(project)
    wheel["vendor/controller.rb"] = b"optional development source"
    with pytest.raises(ValueError, match="Unexpected wheel"):
        release.verify_artifacts(project, write_archives(project, wheel, sdist))


def test_stale_or_extra_distribution_fails(project):
    dist = write_archives(project, *archive_files(project))
    (dist / "old.whl").write_bytes(b"stale")
    with pytest.raises(ValueError, match="exactly one"):
        release.verify_artifacts(project, dist)


def test_qualification_receives_exact_candidates_without_rebuilding(project, monkeypatch):
    import check_fresh_package

    dist = write_archives(project, *archive_files(project))
    calls = []

    def qualify(artifact, sdist, workspace, report, log):
        calls.append((artifact, sdist))
        assert artifact.parent == dist
        report["stages"].append({"status": "passed"})

    monkeypatch.setattr(check_fresh_package, "qualify_artifact", qualify)
    report = release.qualify_exact_archives(dist, project / "evidence.json")
    assert report["status"] == "passed"
    assert {path.suffix for path, _ in calls} == {".whl", ".gz"}


def test_failed_candidate_validation_replaces_previous_pass(project, monkeypatch):
    monkeypatch.setattr(release, "make_version", lambda: "4.4.1")
    output = project / "evidence.json"
    output.write_text('{"status":"passed","artifacts":{"old.whl":{}}}')
    output.with_suffix(".log").write_text("Old successful installation")
    dist = project / "empty-dist"
    dist.mkdir()
    with pytest.raises(ValueError, match="exactly one"):
        release.check_candidate(project, dist, output, False)
    evidence = json.loads(output.read_text())
    assert evidence["status"] == "failed"
    assert evidence["artifacts"] == {}
    assert evidence["toolchain"]["make"] == "4.4.1"
    assert "Old successful" not in output.with_suffix(".log").read_text()


def test_failed_installation_preserves_partial_evidence(project, monkeypatch):
    import check_fresh_package

    dist = write_archives(project, *archive_files(project))
    output = project / "evidence.json"
    output.write_text('{"status":"passed"}')

    def fail_install(artifact, sdist, workspace, report, log):
        assert json.loads(output.read_text())["status"] == "running"
        report["stages"].append({"stage": "fresh install", "status": "failed"})
        raise RuntimeError("Installation failed")

    monkeypatch.setattr(check_fresh_package, "qualify_artifact", fail_install)
    with pytest.raises(RuntimeError, match="Installation failed"):
        release.check_candidate(project, dist, output, True)
    evidence = json.loads(output.read_text())
    assert evidence["status"] == "failed"
    assert len(evidence["artifacts"]) == 2
    assert evidence["installation"]["status"] == "failed"
    assert evidence["installation"]["stages"] == [{"stage": "fresh install", "status": "failed"}]


def test_release_configuration_tracks_package_and_documentation_versions():
    config = json.loads((ROOT / ".github/release-please-config.json").read_text())
    package = config["packages"]["."]
    assert config["release-type"] == "python"
    assert package["package-name"] == "best-practices-mcp"
    if "release-as" in package:
        assert release.Version(package["release-as"]).is_prerelease == package.get(
            "prerelease", False
        )
    assert {item["path"] for item in package["extra-files"]} >= {"README.md", "uv.lock"}
    manifest = json.loads((ROOT / ".github/.release-please-manifest.json").read_text())
    if manifest:
        assert release.Version(manifest["."]) == release.Version(
            release.project_metadata(ROOT)["version"]
        )


def test_sbom_cli_preserves_isolated_interpreter_and_absolute_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "base-python"
    base.touch()
    interpreter = tmp_path / "tools-python"
    try:
        interpreter.symlink_to(base)
    except OSError:
        pytest.skip("Creating interpreter symlinks requires additional Windows privileges")
    calls = []

    def check(root, dist, output, allow_downloads, *, sbom_python):
        calls.append((output, sbom_python))
        return {"status": "passed"}

    monkeypatch.setattr(release, "check_candidate", check)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_check.py",
            "artifacts",
            "--allow-downloads",
            "--sbom-python",
            "tools-python",
            "--output",
            "reports/evidence.json",
        ],
    )
    assert release.main() == 0
    assert calls == [(tmp_path / "reports/evidence.json", interpreter)]
