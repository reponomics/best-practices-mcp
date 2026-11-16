"""Verification fingerprints track implementation inputs and sanitize local logs."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verification_support", ROOT / "scripts" / "verification_support.py"
)
assert SPEC and SPEC.loader
verification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verification)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "sample.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    return tmp_path


def test_git_uses_requested_repository_and_strips_output(repo: Path) -> None:
    assert verification.git(repo, "ls-files") == "src/sample.py"


def test_git_failure_propagates(repo: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        verification.git(repo, "rev-parse", "--verify", "refs/heads/missing")


def test_source_fingerprint_ignores_reports_and_docs_but_detects_code(repo: Path) -> None:
    before = verification.source_fingerprint(repo)
    report = repo / "build" / "verification" / "report.html"
    report.parent.mkdir(parents=True)
    report.write_text("new report", encoding="utf-8")
    (repo / "README.md").write_text("Documentation update", encoding="utf-8")
    assert verification.source_fingerprint(repo) == before
    (repo / "src" / "sample.py").write_text("value = 2\n", encoding="utf-8")
    assert verification.source_fingerprint(repo) != before


def test_new_implementation_files_change_fingerprint_before_staging(repo: Path) -> None:
    before = verification.source_fingerprint(repo)
    (repo / "src" / "new.py").write_text("value = 2\n", encoding="utf-8")
    after = verification.source_fingerprint(repo)
    assert after != before
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    assert verification.source_fingerprint(repo) == after


def test_ignored_untracked_files_do_not_change_fingerprint(repo: Path) -> None:
    (repo / ".gitignore").write_text("src/generated.py\n", encoding="utf-8")
    before = verification.source_fingerprint(repo)
    (repo / "src" / "generated.py").write_text("value = 2\n", encoding="utf-8")
    assert verification.source_fingerprint(repo) == before


def test_deleted_implementation_file_changes_fingerprint(repo: Path) -> None:
    before = verification.source_fingerprint(repo)
    (repo / "src" / "sample.py").unlink()
    assert verification.source_fingerprint(repo) != before


def test_example_host_changes_change_fingerprint(repo: Path) -> None:
    (repo / "examples").mkdir()
    host = repo / "examples" / "host.py"
    host.write_text("print('host')\n", encoding="utf-8")
    before = verification.source_fingerprint(repo)
    host.write_text("raise RuntimeError('host failure')\n", encoding="utf-8")
    assert verification.source_fingerprint(repo) != before


@pytest.mark.parametrize(
    "name",
    [
        "Makefile",
        "pyproject.toml",
        "MANIFEST.in",
        "uv.lock",
        "osv-scanner.toml",
        ".pre-commit-config.yaml",
        ".gitattributes",
        ".python-version",
        "codecov.yml",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        ".github/dependabot.yml",
        ".github/release-please-config.json",
        ".github/workflows/ci.yml",
        ".github/workflows/actionlint.yml",
    ],
)
def test_dependency_build_and_release_input_changes_change_fingerprint(repo: Path, name: str):
    source = repo / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("{}", encoding="utf-8")
    before = verification.source_fingerprint(repo)
    source.write_text('{"changed":true}', encoding="utf-8")
    assert verification.source_fingerprint(repo) != before


def test_sanitizer_removes_account_paths_and_url_queries(repo: Path) -> None:
    result = verification.sanitize(
        f"{repo}/file {Path.home()}/secret https://example.org/edit?answer=secret", repo
    )
    assert result == "<repo>/file <home>/secret https://example.org/edit?<redacted>"


def test_sanitizer_preserves_status_and_urls_without_queries(repo: Path) -> None:
    text = "3 passed, 1 skipped\nSee https://example.org/checks for details."
    assert verification.sanitize(text, repo) == text


@pytest.mark.parametrize("version", ["3.81", "4.4.1"])
def test_make_version_uses_selected_executable_without_retaining_paths(monkeypatch, version):
    executable = "/custom tools/gmake"
    monkeypatch.setenv("VERIFICATION_MAKE", executable)

    def run(command, **kwargs):
        assert command == [executable, "--version"]
        assert kwargs == {"capture_output": True, "text": True, "timeout": 10, "check": True}
        return subprocess.CompletedProcess(command, 0, f"GNU Make {version}\nPrivate build path")

    monkeypatch.setattr(verification.subprocess, "run", run)
    assert verification.make_version() == version


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError(),
        subprocess.CalledProcessError(1, "make"),
        subprocess.TimeoutExpired("make", 10),
    ],
)
def test_make_version_reports_unavailable_on_probe_failure(monkeypatch, error):
    def run(*args, **kwargs):
        raise error

    monkeypatch.setattr(verification.subprocess, "run", run)
    assert verification.make_version() == "unavailable"


def test_make_version_rejects_unrecognized_output(monkeypatch):
    monkeypatch.delenv("VERIFICATION_MAKE", raising=False)

    def run(command, **kwargs):
        assert command == ["make", "--version"]
        return subprocess.CompletedProcess(command, 0, "different tool: /private/path")

    monkeypatch.setattr(verification.subprocess, "run", run)
    assert verification.make_version() == "unavailable"
