"""Validate release identity and exact wheel/sdist candidates without publishing."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tempfile
import tomllib
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

from packaging.utils import canonicalize_name
from packaging.version import Version
from verification_support import make_version

ROOT = Path(__file__).resolve().parents[1]
TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-beta\.([1-9][0-9]*))?")
FORBIDDEN_PARTS = {"internal", ".git", "venv", ".venv", "node_modules", "__pycache__"}
UPSTREAM_NOTICE = "src/best_practices_mcp/data/BADGEAPP-LICENSE.txt"


def project_metadata(root: Path) -> dict[str, Any]:
    document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project: dict[str, Any] = document["project"]
    return project


def validate_source(root: Path, tag: str, prerelease: bool) -> Version:
    """A GitHub release, manifest and package must identify the same release."""
    if TAG.fullmatch(tag) is None:
        raise ValueError("Expected vX.Y.Z or vX.Y.Z-beta.N release tag")
    expected = Version(tag[1:])
    project = project_metadata(root)
    manifest = json.loads((root / ".github/.release-please-manifest.json").read_text("utf-8"))
    if Version(project["version"]) != expected or Version(manifest.get(".", "0")) != expected:
        raise ValueError("Release tag, project version and Release Please manifest must agree")
    if expected.is_prerelease != prerelease:
        raise ValueError("GitHub prerelease flag disagrees with release version")
    if project["name"] != "best-practices-mcp" or project.get("license") != "MIT":
        raise ValueError("Expected best-practices-mcp with explicit MIT metadata")
    return expected


def git_output(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=root, text=True, encoding="utf-8", timeout=30
    ).strip()


def validate_git(root: Path, tag: str, expected_sha: str) -> str:
    head = git_output(root, "rev-parse", "HEAD")
    tagged = git_output(root, "rev-parse", f"refs/tags/{tag}^{{commit}}")
    if head != expected_sha or tagged != head:
        raise ValueError("Checked-out revision does not match the release event and tag")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", head, "origin/main"],
        cwd=root,
        check=True,
        timeout=30,
    )
    return head


def read_archive(path: Path) -> dict[str, bytes]:
    if path.suffix == ".whl":
        with ZipFile(path) as archive:
            return {
                name: archive.read(name) for name in archive.namelist() if not name.endswith("/")
            }
    with tarfile.open(path) as archive:
        files = {}
        for member in archive:
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"{path.name}: nonregular archive entry {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"{path.name}: unreadable archive entry")
            files[member.name] = stream.read()
        return files


def verify_paths(files: dict[str, bytes]) -> None:
    for name in files:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError(f"Unsafe archive path: {name}")
        if FORBIDDEN_PARTS.intersection(part.lower() for part in path.parts):
            raise ValueError(f"Private/development path in release: {name}")


def verify_metadata(metadata: bytes, project: dict[str, Any]) -> None:
    headers = BytesParser().parsebytes(metadata)
    if canonicalize_name(headers["Name"] or "") != canonicalize_name(project["name"]):
        raise ValueError("Distribution name does not match project")
    if Version(headers["Version"] or "0") != Version(project["version"]):
        raise ValueError("Distribution version does not match project")
    for key, expected in {
        "Requires-Python": project["requires-python"],
        "License-Expression": "MIT",
        "Description-Content-Type": "text/markdown",
    }.items():
        if headers[key] != expected:
            raise ValueError(f"Distribution {key} does not match release metadata")
    readme = headers.get_payload()
    if not isinstance(readme, str) or not readme.strip():
        raise ValueError("Missing distribution README")
    for label, url in project.get("urls", {}).items():
        if f"{label}, {url}" not in headers.get_all("Project-URL", []):
            raise ValueError(f"Missing project URL: {label}")


def license_paths(root: Path, project: dict[str, Any]) -> set[str]:
    paths = {
        path.relative_to(root).as_posix()
        for pattern in project.get("license-files", [])
        for path in root.glob(pattern)
        if path.is_file()
    }
    if not {"LICENSE", "THIRD_PARTY_NOTICES.md", UPSTREAM_NOTICE} <= paths:
        raise ValueError("Project license-files must include project and third-party notices")
    return paths


def verify_wheel(files: dict[str, bytes], root: Path, project: dict[str, Any]) -> None:
    metadata_paths = [name for name in files if name.endswith(".dist-info/METADATA")]
    if len(metadata_paths) != 1:
        raise ValueError("Expected exactly one wheel METADATA")
    metadata_root = metadata_paths[0].rsplit("/", 1)[0]
    verify_metadata(files[metadata_paths[0]], project)
    for name in files:
        if not name.startswith(("best_practices_mcp/", metadata_root + "/")):
            raise ValueError(f"Unexpected wheel content: {name}")
    if files.get(metadata_root + "/licenses/LICENSE") != (root / "LICENSE").read_bytes():
        raise ValueError("Wheel is missing the exact project license")
    if (
        files.get("best_practices_mcp/data/BADGEAPP-LICENSE.txt")
        != (root / UPSTREAM_NOTICE).read_bytes()
    ):
        raise ValueError("Wheel is missing the exact BadgeApp notice")
    declared = set(BytesParser().parsebytes(files[metadata_paths[0]]).get_all("License-File", []))
    if declared != license_paths(root, project):
        raise ValueError("Wheel License-File declarations do not match project notices")
    for name in declared:
        if files.get(metadata_root + "/licenses/" + name) != (root / name).read_bytes():
            raise ValueError(f"Wheel license metadata/content mismatch: {name}")


def verify_sdist(files: dict[str, bytes], root: Path, project: dict[str, Any]) -> None:
    prefixes = {PurePosixPath(name).parts[0] for name in files}
    if len(prefixes) != 1:
        raise ValueError("Expected one source-distribution root")
    prefix = prefixes.pop() + "/"
    relative = {name.removeprefix(prefix): data for name, data in files.items()}
    if "PKG-INFO" not in relative:
        raise ValueError("Source distribution is missing PKG-INFO")
    verify_metadata(relative["PKG-INFO"], project)
    for name in license_paths(root, project) | {"pyproject.toml"}:
        if relative.get(name) != (root / name).read_bytes():
            raise ValueError(f"Source distribution is missing or changed: {name}")


def verify_artifacts(root: Path, dist: Path) -> dict[str, Any]:
    paths = sorted(dist.iterdir())
    wheels = [path for path in paths if path.suffix == ".whl"]
    sdists = [path for path in paths if path.name.endswith(".tar.gz")]
    if len(paths) != 2 or len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Release directory must contain exactly one wheel and one sdist")
    project = project_metadata(root)
    result = {}
    for path in (wheels[0], sdists[0]):
        files = read_archive(path)
        verify_paths(files)
        if path.suffix == ".whl":
            verify_wheel(files, root, project)
        else:
            verify_sdist(files, root, project)
        result[path.name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
    return result


def qualify_exact_archives(
    dist: Path,
    output: Path,
    report: dict[str, Any] | None = None,
    *,
    sbom_python: Path | None = None,
) -> dict[str, Any]:
    """Reuse installed-package probes without rebuilding the reviewed candidate."""
    from check_fresh_package import qualify_artifact

    if report is None:
        report = {"status": "failed", "stages": [], "artifacts": {}}
    log = output.with_suffix(".log")
    log.write_text("Exact release archive qualification\n", encoding="utf-8")
    sdist = next(dist.glob("*.tar.gz"))
    wheel = next(dist.glob("*.whl"))
    with tempfile.TemporaryDirectory(prefix="bestpractices-release-") as temporary:
        workspace = Path(temporary)
        for kind, artifact in (("wheel", wheel), ("sdist", sdist)):
            options = (
                {}
                if sbom_python is None
                else {"sbom_python": sbom_python, "reports": output.parent / "reports"}
            )
            qualify_artifact(artifact, sdist, workspace / kind, report, log, **options)
    report["status"] = "passed"
    return report


def check_candidate(
    root: Path, dist: Path, output: Path, allow_downloads: bool, *, sbom_python: Path | None = None
) -> dict[str, Any]:
    """Replace prior evidence before checking; preserve partial evidence on failure."""
    output.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "status": "running",
        "artifacts": {},
        "toolchain": {"make": make_version()},
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    output.with_suffix(".log").write_text("Release candidate validation\n", encoding="utf-8")
    try:
        report["version"] = str(Version(project_metadata(root)["version"]))
        before = verify_artifacts(root, dist)
        report["artifacts"] = before
        if allow_downloads:
            report["installation"] = {"status": "failed", "stages": [], "artifacts": {}}
            qualify_exact_archives(dist, output, report["installation"], sbom_python=sbom_python)
        if before != verify_artifacts(root, dist):
            raise ValueError("Release artifacts changed during qualification")
        report["status"] = "passed"
    finally:
        if report["status"] != "passed":
            report["status"] = "failed"
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    source = sub.add_parser("source")
    source.add_argument(
        "--tag", default=os.environ.get("RELEASE_TAG"), required="RELEASE_TAG" not in os.environ
    )
    source.add_argument(
        "--prerelease",
        choices=("true", "false"),
        default=os.environ.get("RELEASE_PRERELEASE", "false"),
    )
    source.add_argument(
        "--sha", default=os.environ.get("GITHUB_SHA"), required="GITHUB_SHA" not in os.environ
    )
    artifacts = sub.add_parser("artifacts")
    artifacts.add_argument("--dist", type=Path, default=ROOT / "build/release/dist")
    artifacts.add_argument("--output", type=Path, default=ROOT / "build/release/evidence.json")
    artifacts.add_argument(
        "--allow-downloads",
        action="store_true",
        help="Qualify exact archives with fresh dependency installs",
    )
    artifacts.add_argument("--sbom-python", type=Path, help="Isolated release-tools interpreter")
    args = parser.parse_args()
    if args.command == "source":
        version = validate_source(ROOT, args.tag, args.prerelease == "true")
        revision = validate_git(ROOT, args.tag, args.sha)
        print(f"Validated {args.tag} ({version}) at {revision} on main")
        return 0
    args.dist = args.dist.resolve()
    if args.sbom_python is not None and not args.allow_downloads:
        parser.error("--sbom-python requires --allow-downloads qualification")
    # Preserve the venv interpreter symlink: resolving it would select the base Python.
    sbom_python = args.sbom_python.absolute() if args.sbom_python is not None else None
    args.output = args.output.absolute()
    report = check_candidate(
        ROOT, args.dist, args.output, args.allow_downloads, sbom_python=sbom_python
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
