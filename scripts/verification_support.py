"""Shared source identity and log sanitization for verification tools."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def make_version() -> str:
    """Record only the GNU Make version, without executable paths or license text."""
    executable = os.environ.get("VERIFICATION_MAKE", "make")
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=10, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    match = re.match(r"GNU Make ([0-9]+(?:\.[0-9]+)+)\b", result.stdout)
    return match[1] if match else "unavailable"


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def source_fingerprint(root: Path) -> str:
    """Ignore report/docs-only edits; include tracked and new implementation inputs."""
    names = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    digest = hashlib.sha256()
    for name in sorted(set(names.split("\0"))):
        path = root / name
        relevant = name.split("/", 1)[0] in {"src", "tests", "scripts", "vendor"}
        relevant |= name.startswith(".github/")
        relevant |= name in {
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
        }
        if relevant and path.is_file():
            digest.update(name.encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def sanitize(text: str, root: Path) -> str:
    """Local logs are transient; still remove local account paths and URL queries."""
    text = text.replace(str(root), "<repo>").replace(str(Path.home()), "<home>")
    return re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?<redacted>", text)
