"""Opt-in fresh wheel/sdist installation with downloads and isolated runtime probes.

Run with --allow-downloads to resolve and install dependencies from pip's
configured package index. Runtime probes use synthetic data and temporary draft roots.
"""

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from check_package import check_archives
from verification_support import git, source_fingerprint

ROOT = Path(__file__).resolve().parents[1]


def clean_environment(workspace: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "__PYVENV_LAUNCHER__",
        "PIP_TARGET",
        "PIP_PREFIX",
        "PIP_USER",
    ):
        env.pop(name, None)
    env.update(
        PYTHONNOUSERSITE="1",
        PYTHONUTF8="1",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PIP_CONFIG_FILE=os.devnull,
        BESTPRACTICES_DATA_DIR=str(workspace / "drafts"),
    )
    return env


def sanitized(text: str, workspace: Path) -> str:
    for path, label in ((workspace, "<temporary>"), (ROOT, "<repo>"), (Path.home(), "<home>")):
        text = text.replace(str(path), label)
    text = text.replace(tempfile.gettempdir(), "<temporary-root>")
    return re.sub(r"https?://\S+", "<package-url>", text)


def stage(report: dict, label: str, command: list[str], cwd: Path, env: dict, log: Path) -> str:
    record = {"stage": label, "status": "failed"}
    report["stages"].append(record)
    try:
        result = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        record["error"] = type(error).__name__
        raise RuntimeError(f"{label}: {type(error).__name__}") from error
    record["exit_code"] = result.returncode
    with log.open("a", encoding="utf-8") as stream:
        stream.write(f"\n[{label}]\n" + sanitized(result.stdout + result.stderr, cwd))
    if result.returncode:
        raise RuntimeError(f"{label} failed with exit {result.returncode}; inspect sanitized log.")
    record["status"] = "passed"
    print(f"{label}: passed", flush=True)
    return result.stdout


def copy_probe_inputs(sdist: Path, workspace: Path) -> None:
    with tarfile.open(sdist) as archive:
        for source, target in (
            ("scripts/package_probe.py", "package_probe.py"),
            ("tests/fixtures/read_server.py", "read_server.py"),
        ):
            members = [member for member in archive if member.name.endswith("/" + source)]
            assert len(members) == 1 and members[0].isfile(), source
            content = archive.extractfile(members[0])
            assert content is not None
            (workspace / target).write_bytes(content.read())


def qualify_artifact(
    artifact: Path,
    sdist: Path,
    workspace: Path,
    report: dict,
    log: Path,
    *,
    sbom_python: Path | None = None,
    reports: Path | None = None,
) -> None:
    kind = "wheel" if artifact.suffix == ".whl" else "sdist"
    workspace.mkdir()
    env = clean_environment(workspace)
    venv = workspace / "venv"
    stage(
        report,
        f"{kind}: create fresh venv",
        [sys.executable, "-m", "venv", str(venv)],
        workspace,
        env,
        log,
    )
    scripts = venv / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    executable = scripts / ("bestpractices-mcp.exe" if os.name == "nt" else "bestpractices-mcp")
    stage(
        report,
        f"{kind}: install with dependencies",
        [str(python), "-m", "pip", "install", str(artifact)]
        + (["--report", str(workspace / "installation.json")] if sbom_python else []),
        workspace,
        env,
        log,
    )
    stage(
        report,
        f"{kind}: dependency consistency",
        [str(python), "-m", "pip", "check"],
        workspace,
        env,
        log,
    )
    for option in ("--help", "--version"):
        stage(
            report, f"{kind}: entry point {option}", [str(executable), option], workspace, env, log
        )
    copy_probe_inputs(sdist, workspace)
    output = stage(
        report,
        f"{kind}: isolated MCP probe",
        [str(python), "-I", str(workspace / "package_probe.py")],
        workspace,
        env,
        log,
    )
    report["artifacts"][kind] = json.loads(output)
    if sbom_python is not None:
        from release_sbom import generate_reference

        if reports is None:
            raise ValueError("Release SBOM generation requires a reports directory")
        report["artifacts"][kind]["reference_evidence"] = generate_reference(
            artifact,
            python,
            sbom_python,
            workspace / "installation.json",
            reports,
            ROOT,
            git(ROOT, "rev-parse", "HEAD"),
            lambda label, command: stage(report, label, command, workspace, env, log),
        )


def execute(report: dict, log: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="bestpractices-fresh-package-") as temporary:
        workspace = Path(temporary)
        env = clean_environment(workspace)
        dist = workspace / "dist"
        stage(
            report,
            "build wheel and sdist",
            [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(dist)],
            ROOT,
            env,
            log,
        )
        wheel = check_archives(dist)
        sdist = next(dist.glob("*.tar.gz"))
        for artifact in (wheel, sdist):
            qualify_artifact(
                artifact, sdist, workspace / artifact.suffix.removeprefix("."), report, log
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-downloads", action="store_true", help="Allow pip dependency/build downloads"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build/verification/fresh-package.json"
    )
    args = parser.parse_args()
    if not args.allow_downloads:
        parser.error(
            "Fresh qualification downloads dependencies; pass --allow-downloads explicitly."
        )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    log = output.with_suffix(".log")
    log.write_text("Fresh package qualification (sanitized subprocess output)\n", encoding="utf-8")
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "os": platform.system(),
        "status": "failed",
        "downloads_authorized": True,
        "tested_commit": git(ROOT, "rev-parse", "HEAD"),
        "source_fingerprint": source_fingerprint(ROOT),
        "platform": platform.platform(),
        "stages": [],
        "artifacts": {},
    }
    try:
        execute(report, log)
        report["status"] = "passed"
    except (AssertionError, OSError, RuntimeError, ValueError) as error:
        report["failure"] = sanitized(str(error) or type(error).__name__, ROOT)
        print(report["failure"], file=sys.stderr)
    finally:
        report["source_changed_during_run"] = report["source_fingerprint"] != source_fingerprint(
            ROOT
        )
        if report["source_changed_during_run"]:
            report["status"] = "failed"
            report["failure"] = "Implementation inputs changed during qualification; rerun."
        report["finished_at"] = datetime.now(UTC).isoformat()
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
