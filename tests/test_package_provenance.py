"""The isolated package probe must compare against the caller's source snapshot."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_package import PROBE

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("matching", [True, False])
def test_package_probe_checks_expected_source_revision(tmp_path, matching):
    manifest = json.loads((ROOT / "vendor/badgeapp/source.json").read_text(encoding="utf-8"))
    expected = manifest["revision"] if matching else "0" * 40
    result = subprocess.run(
        [sys.executable, "-I", "-c", PROBE, str(ROOT / "src"), expected],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if matching:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["installed_catalog"] == "passed"
    else:
        assert result.returncode != 0
        assert "Installed revision differs from manifest" in result.stderr
