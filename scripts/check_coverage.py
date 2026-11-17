"""Measure offline server line/branch coverage, including Python subprocesses.

Produces HTML/XML/JSON reports and execution evidence under build/coverage by
default. An optional minimum applies independently to statement and branch coverage.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from verification_support import ROOT, sanitize, source_fingerprint


def wait_with_progress(process: subprocess.Popen, stage: str) -> bool:
    """Keep buffered, sanitized output while making long stages visibly active."""
    started = time.monotonic()
    deadline = started + 600
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            process.kill()
            process.wait()
            return True
        try:
            process.wait(timeout=min(15, remaining))
            return False
        except subprocess.TimeoutExpired:
            elapsed = int(time.monotonic() - started)
            print(f"Coverage {stage}: still running ({elapsed}s elapsed)", flush=True)


def command(args: list[str], env: dict[str, str], log: Path) -> int:
    print(f"Coverage {args[0]}: starting (stage output follows on completion)", flush=True)
    # A temporary file avoids pipe-draining waits on inherited descendant handles.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as captured:
        with subprocess.Popen(
            [sys.executable, "-m", "coverage", *args],
            cwd=ROOT,
            env=env,
            stdout=captured,
            stderr=subprocess.STDOUT,
        ) as process:
            try:
                timed_out = wait_with_progress(process, args[0])
            except BaseException:
                process.kill()
                process.wait()
                raise
        captured.seek(0)
        output = captured.read()
    output = sanitize(output, ROOT)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(output)
    print(output, end="", flush=True)
    status = 124 if timed_out else process.returncode
    result = "timed out after 600s" if timed_out else f"finished (exit {status})"
    print(f"Coverage {args[0]}: {result}", flush=True)
    return status


@contextmanager
def forward_sdk_coverage():
    """Keep coverage's config through the SDK's intentionally narrow child env.

    The temporary hook applies only to this development venv and is removed even
    after test failure. No production SDK or server file is modified.
    """
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("Coverage subprocess instrumentation requires a virtual environment.")
    directory = Path(sysconfig.get_path("purelib"))
    # Dependency hooks (notably pywin32.pth) must initialize before SDK import.
    descriptor, name = tempfile.mkstemp(
        prefix="zzzz_bestpractices_coverage_", suffix=".pth", dir=directory
    )
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(
                "import os; "
                "_coverage_active = bool(os.environ.get('COVERAGE_RCFILE') "
                "or os.environ.get('COVERAGE_PROCESS_CONFIG')); "
                "_coverage_mcp = __import__('mcp.client.stdio', fromlist=['']) "
                "if _coverage_active else None; "
                "_coverage_mcp and _coverage_mcp.DEFAULT_INHERITED_ENV_VARS"
                ".append('COVERAGE_PROCESS_CONFIG')\n"
            )
        yield
    finally:
        path.unlink(missing_ok=True)


def coverage_commands(output: Path, tests: list[str]) -> list[list[str]]:
    return [
        ["erase"],
        ["run", "-m", "pytest", f"--junitxml={output / 'junit.xml'}", *tests],
        ["combine"],
        ["report"],
        ["html", "-d", str(output / "html")],
        ["xml", "-o", str(output / "coverage.xml")],
        ["json", "-o", str(output / "coverage.json")],
    ]


def clear_reports(output: Path) -> None:
    """Remove only prior generated reports so failed runs cannot reuse a pass."""
    output.mkdir(parents=True, exist_ok=True)
    for name in ("coverage.json", "coverage.xml", "summary.json", "junit.xml"):
        (output / name).unlink(missing_ok=True)
    if (output / "html").exists():
        shutil.rmtree(output / "html")


def execute_checks(output: Path, tests: list[str], env: dict[str, str], log: Path) -> list[dict]:
    checks = []
    for args in coverage_commands(output, tests):
        try:
            status = command(args, env, log)
        except (OSError, subprocess.TimeoutExpired) as exc:
            status = 1
            print(f"Coverage stage {args[0]} failed: {type(exc).__name__}", flush=True)
        checks.append({"stage": args[0], "exit_code": status})
        if args[0] == "erase" and status:
            break
    return checks


def read_totals(report: Path) -> dict | None:
    """Retain execution evidence even when a coverage report is unavailable or invalid."""
    try:
        totals = json.loads(report.read_text(encoding="utf-8"))["totals"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return totals if isinstance(totals, dict) else None


def coverage_metric(totals: dict, metric: str, minimum: float) -> dict:
    covered_key, total_key = {
        "statements": ("covered_lines", "num_statements"),
        "branches": ("covered_branches", "num_branches"),
    }[metric]
    covered, total = totals.get(covered_key), totals.get(total_key)
    if type(covered) is not int or type(total) is not int:
        raise ValueError(f"Missing or invalid {metric} counts")
    if total < 0 or not 0 <= covered <= total:
        raise ValueError(f"Invalid {metric} counts")
    if metric == "statements" and total == 0:
        raise ValueError("No measured statements")
    return {
        "covered": covered,
        "total": total,
        "percentage": 100 * covered / total if total else 100.0,
        "passed": covered * 100 >= minimum * total,
    }


def check_minimum(totals: dict | None, minimum: float) -> dict:
    """Check unrounded counts, so strong statement coverage cannot hide missed branches."""
    try:
        if totals is None:
            raise ValueError("Missing or malformed coverage totals")
        metrics = {
            name: coverage_metric(totals, name, minimum) for name in ("statements", "branches")
        }
    except ValueError as exc:
        print(f"Coverage minimum: failed ({exc})", flush=True)
        return {"passed": False, "error": str(exc)}
    for name, result in metrics.items():
        status = "passed" if result["passed"] else "failed"
        print(
            f"Coverage {name}: {result['covered']}/{result['total']} "
            f"({result['percentage']:.4f}%), minimum {minimum:g}%: {status}",
            flush=True,
        )
    return {"passed": all(result["passed"] for result in metrics.values()), "metrics": metrics}


def run(output: Path, tests: list[str], minimum_coverage: float | None = None) -> int:
    clear_reports(output)
    log = output / "coverage.log"
    log.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "COVERAGE_FILE": str(output / ".coverage"),
        "COVERAGE_RCFILE": str(ROOT / "pyproject.toml"),
        "PYTHONUTF8": "1",
    }
    evidence = {
        "started_at": datetime.now(UTC).isoformat(),
        "tested_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_fingerprint": source_fingerprint(ROOT),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "coverage_version": version("coverage"),
        "scope": "Server package; line and branch coverage, including Python subprocesses.",
        "pytest_paths": tests or ["tests"],
        "sdk_subprocess_instrumentation": (
            "Temporary venv hook forwards COVERAGE_PROCESS_CONFIG only during coverage; "
            "removed after collection."
        ),
        "threshold": minimum_coverage,
        "checks": [],
    }
    with forward_sdk_coverage():
        evidence["checks"] = execute_checks(output, tests, env, log)
    totals = read_totals(output / "coverage.json")
    if totals is not None:
        evidence["totals"] = totals
    gate_failed = False
    if minimum_coverage is not None:
        evidence["coverage_gate"] = check_minimum(totals, minimum_coverage)
        gate_failed = not evidence["coverage_gate"]["passed"]
    evidence["finished_at"] = datetime.now(UTC).isoformat()
    evidence["source_changed_during_run"] = evidence["source_fingerprint"] != source_fingerprint(
        ROOT
    )
    failed = gate_failed or any(check["exit_code"] for check in evidence["checks"])
    evidence["status"] = "failed" if failed or evidence["source_changed_during_run"] else "passed"
    (output / "summary.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return int(evidence["status"] != "passed")


def coverage_minimum(value: str) -> float:
    minimum = float(value)
    if not 0 <= minimum <= 100:
        raise argparse.ArgumentTypeError(
            "minimum coverage must be a finite percentage from 0 to 100"
        )
    return minimum


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/coverage")
    parser.add_argument(
        "--minimum-coverage",
        type=coverage_minimum,
        help="Require this percentage separately for statements and branches (0-100)",
    )
    parser.add_argument("tests", nargs="*", help="Optional focused pytest paths")
    args = parser.parse_args()
    return run(args.output.resolve(), args.tests, args.minimum_coverage)


if __name__ == "__main__":
    raise SystemExit(main())
