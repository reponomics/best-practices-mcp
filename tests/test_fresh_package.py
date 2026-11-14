"""Fresh qualification must be opt-in, isolated and honest about failures."""

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


def test_package_probe_catalog_and_storage_against_real_server(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "package_probe", ROOT / "scripts/package_probe.py"
    )
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    params = StdioServerParameters(
        command=str(probe.executable()),
        cwd=str(tmp_path),
        env={"BESTPRACTICES_DATA_DIR": str(tmp_path / "drafts")},
    )

    async def exercise():
        async with asyncio.timeout(30):
            await probe.catalog_and_storage(params)

    asyncio.run(exercise())


@pytest.fixture
def checker(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "fresh_package", ROOT / "scripts/check_fresh_package.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downloads_require_explicit_opt_in(tmp_path):
    output = tmp_path / "evidence.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_fresh_package.py"), "--output", str(output)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "--allow-downloads" in result.stderr
    assert not output.exists()


def test_environment_cannot_inherit_source_or_install_destination(checker, monkeypatch, tmp_path):
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PIP_TARGET", "PIP_PREFIX", "PIP_USER"):
        monkeypatch.setenv(name, "/unsafe-inherited-location")
    env = checker.clean_environment(tmp_path)
    assert all("unsafe-inherited" not in value for value in env.values())
    assert env["BESTPRACTICES_DATA_DIR"] == str(tmp_path / "drafts")
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PIP_CONFIG_FILE"] == os.devnull


def test_failed_stage_keeps_failure_evidence(checker, monkeypatch, tmp_path):
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(sys, "argv", ["check", "--allow-downloads", "--output", str(output)])

    def fail(report, log):
        checker.stage(
            report,
            "failing probe",
            [sys.executable, "-c", "raise SystemExit(7)"],
            tmp_path,
            checker.clean_environment(tmp_path),
            log,
        )

    monkeypatch.setattr(checker, "execute", fail)
    assert checker.main() == 1
    report = json.loads(output.read_text())
    assert report["status"] == "failed"
    assert report["stages"] == [{"stage": "failing probe", "status": "failed", "exit_code": 7}]
    assert report["finished_at"]


def test_sanitized_logs_remove_paths_and_package_urls(checker, tmp_path):
    message = f"{tmp_path}/data {checker.ROOT}/source https://name:secret@example.org/index"
    result = checker.sanitized(message, tmp_path)
    assert str(tmp_path) not in result and str(checker.ROOT) not in result
    assert "secret" not in result and "example.org" not in result


def test_changed_inputs_cannot_record_a_pass(checker, monkeypatch, tmp_path):
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(sys, "argv", ["check", "--allow-downloads", "--output", str(output)])
    fingerprints = iter(["before", "after"])
    monkeypatch.setattr(checker, "source_fingerprint", lambda _: next(fingerprints))
    monkeypatch.setattr(checker, "execute", lambda *_: None)
    assert checker.main() == 1
    report = json.loads(output.read_text())
    assert report["status"] == "failed"
    assert report["source_changed_during_run"] is True
