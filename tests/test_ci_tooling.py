"""CI evidence must preserve failures and exclude stale successful reports."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("check_coverage", ROOT / "scripts/check_coverage.py")
coverage_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage_check)


@pytest.fixture
def simulated_coverage(tmp_path, monkeypatch):
    """Exercise gate integration without executing another test suite."""
    from contextlib import nullcontext

    monkeypatch.setattr(coverage_check, "forward_sdk_coverage", nullcontext)

    def collect(payload, minimum=95):
        def execute(args, env, log):
            if args[0] == "run":
                (tmp_path / "junit.xml").write_text("test results")
            if args[0] == "html":
                (tmp_path / "html").mkdir()
                (tmp_path / "html/index.html").write_text("coverage details")
            if args[0] == "xml":
                (tmp_path / "coverage.xml").write_text("coverage results")
            if args[0] == "json" and payload is not None:
                content = payload if isinstance(payload, str) else json.dumps(payload)
                (tmp_path / "coverage.json").write_text(content)
            return 0

        monkeypatch.setattr(coverage_check, "command", execute)
        status = coverage_check.run(tmp_path, [], minimum)
        summary = json.loads((tmp_path / "summary.json").read_text())
        return status, summary

    return collect


@pytest.mark.parametrize(
    ("covered_lines", "num_statements", "covered_branches", "num_branches", "expected_status"),
    [
        (95, 100, 19, 20, 0),
        (94, 100, 20, 20, 1),
        (990, 1000, 18, 20, 1),
        (94999, 100000, 20, 20, 1),
        (100, 100, 0, 0, 0),
    ],
)
def test_coverage_minimum_checks_each_unrounded_metric(
    simulated_coverage,
    covered_lines,
    num_statements,
    covered_branches,
    num_branches,
    expected_status,
):
    totals = {
        "covered_lines": covered_lines,
        "num_statements": num_statements,
        "covered_branches": covered_branches,
        "num_branches": num_branches,
        # This combined display metric cannot satisfy an independent branch gate.
        "percent_covered": 99.99,
    }
    status, summary = simulated_coverage({"totals": totals})
    assert status == expected_status
    assert summary["coverage_gate"]["passed"] is (expected_status == 0)
    assert summary["status"] == ("passed" if expected_status == 0 else "failed")
    assert summary["threshold"] == 95
    assert summary["totals"] == totals


def test_below_minimum_retains_reports_and_explains_failure(simulated_coverage, tmp_path, capsys):
    totals = {
        "covered_lines": 99,
        "num_statements": 100,
        "covered_branches": 18,
        "num_branches": 20,
    }
    status, summary = simulated_coverage({"totals": totals})
    assert status == 1
    assert summary["coverage_gate"]["metrics"]["statements"]["passed"] is True
    assert summary["coverage_gate"]["metrics"]["branches"]["passed"] is False
    assert "Coverage branches: 18/20 (90.0000%), minimum 95%: failed" in capsys.readouterr().out
    for report in ("coverage.json", "coverage.xml", "html/index.html", "junit.xml"):
        assert (tmp_path / report).is_file()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "invalid json",
        [],
        {},
        {"totals": []},
        {"totals": {"percent_covered": 100}},
        {
            "totals": {
                "covered_lines": 100,
                "num_statements": 100,
                "covered_branches": "20",
                "num_branches": 20,
            }
        },
        {
            "totals": {
                "covered_lines": True,
                "num_statements": 1,
                "covered_branches": 1,
                "num_branches": 1,
            }
        },
        {
            "totals": {
                "covered_lines": 101,
                "num_statements": 100,
                "covered_branches": 20,
                "num_branches": 20,
            }
        },
        {
            "totals": {
                "covered_lines": 0,
                "num_statements": 0,
                "covered_branches": 0,
                "num_branches": 0,
            }
        },
    ],
)
def test_coverage_minimum_cannot_pass_without_valid_measurements(simulated_coverage, payload):
    status, summary = simulated_coverage(payload)
    assert status == 1
    assert summary["status"] == "failed"
    assert summary["coverage_gate"]["passed"] is False
    assert summary["coverage_gate"]["error"]


def test_focused_diagnostics_do_not_require_a_minimum(simulated_coverage):
    totals = {
        "covered_lines": 10,
        "num_statements": 100,
        "covered_branches": 1,
        "num_branches": 20,
    }
    status, summary = simulated_coverage({"totals": totals}, minimum=None)
    assert status == 0
    assert summary["threshold"] is None
    assert "coverage_gate" not in summary


@pytest.mark.parametrize("minimum", ["-1", "101", "nan", "inf", "-inf", "not-a-number"])
def test_invalid_minimum_is_rejected_before_test_execution(monkeypatch, minimum):
    monkeypatch.setattr(sys, "argv", ["check_coverage.py", f"--minimum-coverage={minimum}"])
    monkeypatch.setattr(
        coverage_check, "run", lambda *args: pytest.fail("Must reject before running")
    )
    with pytest.raises(SystemExit) as error:
        coverage_check.main()
    assert error.value.code == 2


def test_slow_coverage_stage_announces_progress(monkeypatch, capsys):
    import subprocess
    from unittest.mock import Mock

    process = Mock()
    process.wait.side_effect = [subprocess.TimeoutExpired("coverage", 15), 0]
    ticks = iter([0, 0, 15, 15])
    monkeypatch.setattr(coverage_check.time, "monotonic", lambda: next(ticks))
    assert coverage_check.wait_with_progress(process, "run") is False
    assert "Coverage run: still running (15s elapsed)" in capsys.readouterr().out
    assert process.wait.call_count == 2
    process.kill.assert_not_called()


def test_coverage_stage_deadline_kills_child(monkeypatch):
    import subprocess
    from unittest.mock import Mock

    process = Mock()
    process.wait.side_effect = [
        subprocess.TimeoutExpired("coverage", 15),
        -9,
    ]
    ticks = iter([0, 590, 600, 600])
    monkeypatch.setattr(coverage_check.time, "monotonic", lambda: next(ticks))
    assert coverage_check.wait_with_progress(process, "run") is True
    assert process.wait.call_args_list[0].kwargs == {"timeout": 10}
    process.kill.assert_called_once()


def test_coverage_command_preserves_failure_and_sanitizes_output(tmp_path, monkeypatch, capsys):
    from unittest.mock import MagicMock

    process = MagicMock(returncode=7)
    process.__enter__.return_value = process

    def launch(*args, **kwargs):
        kwargs["stdout"].write(f"failure in {ROOT}: https://example.com/?private=1\n")
        return process

    monkeypatch.setattr(coverage_check.subprocess, "Popen", launch)
    log = tmp_path / "coverage.log"
    assert coverage_check.command(["run"], {}, log) == 7
    output = capsys.readouterr().out
    assert "Coverage run: starting" in output
    assert "finished (exit 7)" in output
    assert "private=1" not in output + log.read_text()
    assert str(ROOT) not in output + log.read_text()
    assert "failure in <repo>" in log.read_text()


def test_failed_test_run_still_reports_and_does_not_reuse_stale_totals(tmp_path, monkeypatch):
    (tmp_path / "coverage.json").write_text('{"totals":{"percent_covered":100}}')
    (tmp_path / "html").mkdir()
    (tmp_path / "html/index.html").write_text("old success")
    called = []

    def execute(args, env, log):
        called.append(args[0])
        assert Path(env["COVERAGE_FILE"]).is_absolute()
        assert Path(env["COVERAGE_RCFILE"]).is_absolute()
        return 1 if args[0] == "run" else 0

    monkeypatch.setattr(coverage_check, "command", execute)
    assert coverage_check.run(tmp_path, []) == 1
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert called == ["erase", "run", "combine", "report", "html", "xml", "json"]
    assert summary["status"] == "failed"
    assert "totals" not in summary
    assert not (tmp_path / "html/index.html").exists()


def test_report_failure_cannot_be_overridden_by_successful_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(
        coverage_check,
        "command",
        lambda args, env, log: 1 if args[0] == "combine" else 0,
    )
    assert coverage_check.run(tmp_path, []) == 1
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["checks"][1] == {"stage": "run", "exit_code": 0}
    assert summary["status"] == "failed"


def test_coverage_measures_read_dispatch_inside_sdk_stdio_children(tmp_path):
    import os
    import subprocess

    report = tmp_path / "coverage"
    env = {key: value for key, value in os.environ.items() if not key.startswith("COVERAGE_")}
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_coverage.py"),
            "--output",
            str(report),
            "tests/test_read_tools.py",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    coverage = json.loads((report / "coverage.json").read_text(encoding="utf-8"))
    server = ROOT / "src/best_practices_mcp/server.py"
    files = {name.replace("\\", "/"): data for name, data in coverage["files"].items()}
    executed = files[server.relative_to(ROOT).as_posix()]["executed_lines"]
    expected = {
        "return get_criteria(**values)",
        "return await client.find_project(**values)",
        "return await client.get_project_progress(**values)",
    }
    dispatch_lines = {
        index
        for index, line in enumerate(server.read_text(encoding="utf-8").splitlines(), 1)
        if line.strip() in expected
    }
    assert len(dispatch_lines) == 3
    assert dispatch_lines <= set(executed)


def test_sdk_coverage_hook_is_removed_after_failure(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(coverage_check.sysconfig, "get_path", lambda name: str(tmp_path))
    existing = tmp_path / "existing.pth"
    existing.write_text("untouched")
    with pytest.raises(RuntimeError, match="test failure"):
        with coverage_check.forward_sdk_coverage():
            assert len(list(tmp_path.glob("*.pth"))) == 2
            raise RuntimeError("test failure")
    assert list(tmp_path.iterdir()) == [existing]
    assert existing.read_text() == "untouched"


def test_sdk_coverage_hook_does_not_change_unmeasured_processes():
    import os
    import subprocess

    env = {key: value for key, value in os.environ.items() if not key.startswith("COVERAGE_")}
    with coverage_check.forward_sdk_coverage():
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from mcp.client.stdio import DEFAULT_INHERITED_ENV_VARS as names; "
                "assert 'COVERAGE_PROCESS_CONFIG' not in names",
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    assert result.returncode == 0, result.stderr


def test_sdk_coverage_hook_runs_after_dependency_path_initialization(tmp_path, monkeypatch):
    import os
    import subprocess

    monkeypatch.setattr(coverage_check.sysconfig, "get_path", lambda name: str(tmp_path))
    (tmp_path / "pywin32.pth").write_text(
        "import os; os.environ['BESTPRACTICES_ORDERING_PROBE'] = 'initialized'\n",
        encoding="utf-8",
    )
    probe = """
import builtins, os, site, sys
from types import SimpleNamespace
os.environ.pop('BESTPRACTICES_ORDERING_PROBE', None)
original_import = builtins.__import__
stdio = SimpleNamespace(DEFAULT_INHERITED_ENV_VARS=[])
def guarded_import(name, *args, **kwargs):
    if name == 'mcp.client.stdio':
        assert os.environ.get('BESTPRACTICES_ORDERING_PROBE') == 'initialized'
        return stdio
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
site.addsitedir(sys.argv[1])
assert stdio.DEFAULT_INHERITED_ENV_VARS == ['COVERAGE_PROCESS_CONFIG']
"""
    env = {key: value for key, value in os.environ.items() if not key.startswith("COVERAGE_")}
    env["COVERAGE_RCFILE"] = "ordering-probe"
    with coverage_check.forward_sdk_coverage():
        result = subprocess.run(
            [sys.executable, "-S", "-c", probe, str(tmp_path)],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
