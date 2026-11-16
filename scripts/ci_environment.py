"""Record a small allowlist of CI environment facts; never dump secrets or paths."""

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from verification_support import make_version


def output(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "tested_commit": output(["git", "rev-parse", "HEAD"]),
        "python": platform.python_version(),
        "os": platform.platform(),
        "architecture": platform.machine(),
        "make": make_version(),
        "matrix_os": os.environ.get("CI_MATRIX_OS"),
        "matrix_python": os.environ.get("CI_MATRIX_PYTHON"),
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "runner_image": os.environ.get("ImageOS"),
        "runner_image_version": os.environ.get("ImageVersion"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "workflow_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "workflow_event": os.environ.get("GITHUB_EVENT_NAME"),
        "interpreter_implementation": sys.implementation.name,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
