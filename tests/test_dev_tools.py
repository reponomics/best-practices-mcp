"""Check bootstrap inventory consistency and shell-independent Make helpers."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "dev_tools", Path(__file__).resolve().parents[1] / "scripts" / "dev_tools.py"
)
assert SPEC and SPEC.loader
TOOLS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOLS)


@pytest.mark.parametrize("override", [None, "command-line", "environment"])
def test_make_selects_one_project_environment_for_uv_and_python(tmp_path, override):
    make = os.environ.get("VERIFICATION_MAKE") or shutil.which("make")
    assert make, "GNU Make is required for development tooling checks"
    probe = tmp_path / "environment probe.py"
    probe.write_text(
        "import json, os, sys\n"
        "print(json.dumps([os.environ['UV_PROJECT_ENVIRONMENT'], *sys.argv[1:]]))\n",
        encoding="utf-8",
    )
    makefile = tmp_path / "probe.mk"
    makefile.write_text(
        ".PHONY: inspect-project-environment\n"
        "inspect-project-environment:\n"
        '\t@"$(PROBE_PYTHON)" "$(PROBE_SCRIPT)" "$(VENV)" "$(PYTHON)"\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    for name in ("VENV", "PYTHON", "MAKEFLAGS", "MFLAGS", "MAKELEVEL", "GNUMAKEFLAGS"):
        env.pop(name, None)
    # Make must export its selected directory even when a shell has an old override.
    env["UV_PROJECT_ENVIRONMENT"] = "stale-environment"
    selected = ".venv" if override is None else "build/custom venv"
    arguments = []
    if override == "command-line":
        arguments.append(f"VENV={selected}")
    elif override == "environment":
        env["VENV"] = selected
    result = subprocess.run(
        [
            make,
            "--no-print-directory",
            "-f",
            "Makefile",
            "-f",
            str(makefile),
            "inspect-project-environment",
            f"PROBE_PYTHON={sys.executable}",
            f"PROBE_SCRIPT={probe}",
            *arguments,
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    interpreter = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    assert json.loads(result.stdout) == [selected, selected, f"{selected}/{interpreter}"]


@pytest.fixture
def inventory(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "best-practices-mcp"\nversion = "0.2.0-beta.1"\nlicense = "MIT"\n'
        '[dependency-groups]\ndev = ["pytest==9.2.0"]\n'
        'audit-tools = ["uv==0.13.7"]\n'
        '[tool.uv]\nrequired-version = "==0.13.7"\ndefault-groups = ["dev"]\n'
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "uv"\nversion = "0.13.7"\n'
        '[[package]]\nname = "best-practices-mcp"\nversion = "0.2.0b1"\n'
        'source = { editable = "." }\n'
    )
    (tmp_path / "osv-scanner.toml").write_text(
        '[[PackageOverrides]]\nname = "best-practices-mcp"\necosystem = "PyPI"\n'
        'license.override = ["MIT"]\nreason = "First-party metadata"\n'
    )
    return tmp_path


def test_help_uses_target_annotations(tmp_path, capsys):
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        "# comment\nsetup: ## Sync environment\n"
        "check: quality ## Check everything\nprivate:\n\t@echo hidden\n"
    )
    TOOLS.show_help(makefile)
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines] == ["setup", "check"]
    assert lines[1].endswith("Check everything")


def test_consistent_inventory(inventory, capsys):
    TOOLS.check_tooling(inventory)
    assert "agree" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("filename", "before", "after", "error"),
    [
        ("pyproject.toml", 'required-version = "==', 'required-version = ">=', "exact"),
        ("pyproject.toml", 'audit-tools = ["uv==0.13.7"]', "audit-tools = []", "match"),
        (
            "pyproject.toml",
            'default-groups = ["dev"]',
            'default-groups = ["audit-tools"]',
            "default",
        ),
        ("pyproject.toml", 'dev = ["pytest==9.2.0"]', 'dev = ["uv==0.13.7"]', "belongs"),
        ("uv.lock", 'version = "0.13.7"', 'version = "0.13.6"', "uv.lock"),
        ("uv.lock", 'name = "uv"', 'name = "another"', "uv.lock"),
    ],
)
def test_inventory_rejects_drift(inventory, filename, before, after, error):
    path = inventory / filename
    path.write_text(path.read_text().replace(before, after))
    with pytest.raises(ValueError, match=error):
        TOOLS.check_tooling(inventory)


@pytest.mark.parametrize(
    ("filename", "before", "after", "error"),
    [
        ("pyproject.toml", 'license = "MIT"', 'license = "Apache-2.0"', "project license"),
        ("uv.lock", 'editable = "."', 'registry = "https://pypi.org/simple"', "local editable"),
        ("uv.lock", 'name = "best-practices-mcp"', 'name = "another-project"', "local editable"),
        ("osv-scanner.toml", 'name = "best-practices-mcp"', 'name = "another-project"', "override"),
        ("osv-scanner.toml", 'ecosystem = "PyPI"', 'ecosystem = "npm"', "override"),
        ("osv-scanner.toml", 'license.override = ["MIT"]', "license.ignore = true", "override"),
        (
            "osv-scanner.toml",
            'license.override = ["MIT"]',
            'license.override = ["ISC"]',
            "override",
        ),
    ],
)
def test_first_party_license_rejects_metadata_drift(inventory, filename, before, after, error):
    path = inventory / filename
    path.write_text(path.read_text().replace(before, after))
    with pytest.raises(ValueError, match=error):
        TOOLS.check_tooling(inventory)


@pytest.mark.parametrize(
    "setting",
    [
        "ignore = true",
        "vulnerability.ignore = true",
        "license.ignore = true",
        'version = "0.2.0-beta.1"',
        'group = "dev"',
        "nameIsRegex = true",
    ],
)
def test_first_party_override_cannot_suppress_or_filter_candidates(inventory, setting):
    policy = inventory / "osv-scanner.toml"
    policy.write_text(policy.read_text() + setting + "\n")
    with pytest.raises(ValueError, match="without filters or ignores"):
        TOOLS.check_tooling(inventory)


def test_first_party_license_allows_next_unpublished_version_without_policy_edit(inventory):
    for filename, before, after in (
        ("pyproject.toml", "0.2.0-beta.1", "0.2.0-beta.2"),
        ("uv.lock", "0.2.0b1", "0.2.0b2"),
    ):
        path = inventory / filename
        path.write_text(path.read_text().replace(before, after))
    TOOLS.check_tooling(inventory)


@pytest.mark.parametrize("filename", ["uv.lock", "osv-scanner.toml"])
def test_first_party_identity_must_be_unique(inventory, filename):
    path = inventory / filename
    content = path.read_text()
    path.write_text(content + content)
    with pytest.raises(ValueError, match="unique|one first-party"):
        TOOLS.check_tooling(inventory)


def test_distribution_paths_preserve_spaces(tmp_path, monkeypatch):
    dist = tmp_path / "release candidates"
    dist.mkdir()
    for name in ("pkg.whl", "pkg.tar.gz", "notes.txt"):
        (dist / name).touch()
    calls = []
    monkeypatch.setattr(
        TOOLS.subprocess, "run", lambda argv, **kwargs: calls.append((argv, kwargs))
    )
    TOOLS.check_distributions(dist)
    argv, kwargs = calls[0]
    assert argv == [
        TOOLS.sys.executable,
        "-m",
        "twine",
        "check",
        "--strict",
        str(dist / "pkg.tar.gz"),
        str(dist / "pkg.whl"),
    ]
    assert kwargs == {"check": True}


def test_empty_distribution_directory_fails(tmp_path):
    with pytest.raises(ValueError, match="No wheel"):
        TOOLS.check_distributions(tmp_path)


def test_twine_failure_propagates(tmp_path, monkeypatch):
    (tmp_path / "pkg.whl").touch()

    def fail(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(TOOLS.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        TOOLS.check_distributions(tmp_path)


def test_tool_launcher_uses_resolved_path(monkeypatch, tmp_path):
    launcher = str(tmp_path / "Node installation" / "npm.cmd")
    calls = []
    monkeypatch.setattr(TOOLS.shutil, "which", lambda name: launcher)
    monkeypatch.setattr(
        TOOLS.subprocess, "run", lambda argv, **kwargs: calls.append((argv, kwargs))
    )
    TOOLS.run_tool(["npm.cmd", "ci", "--ignore-scripts"])
    assert calls == [([launcher, "ci", "--ignore-scripts"], {"check": True})]


def test_missing_tool_launcher_fails(monkeypatch):
    monkeypatch.setattr(TOOLS.shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError, match="Executable not found: npm.cmd"):
        TOOLS.run_tool(["npm.cmd", "ci"])


def test_tool_launcher_failure_propagates(monkeypatch):
    monkeypatch.setattr(TOOLS.shutil, "which", lambda name: name)

    def fail(argv, **kwargs):
        raise subprocess.CalledProcessError(2, argv)

    monkeypatch.setattr(TOOLS.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        TOOLS.run_tool(["npm.cmd", "ci"])
