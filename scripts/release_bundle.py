"""Assemble qualified release bytes and evidence before immutable publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from release_check import ROOT, git_output, verify_artifacts

REQUIRED_REPORTS = (
    "runtime-wheel.cdx.json",
    "runtime-sdist.cdx.json",
    "runtime-wheel.inventory.json",
    "runtime-sdist.inventory.json",
    "pip-wheel.json",
    "pip-sdist.json",
    "osv-vulnerabilities.sarif",
    "osv-licenses.json",
    "tooling.cdx.json",
)
POLICY_INPUTS = (
    ("osv-scanner.toml", "osv-scanner.toml"),
    ("uv.lock", "uv.lock"),
    ("pyproject.toml", "pyproject.toml"),
    (".pre-commit-config.yaml", "pre-commit-config.yaml"),
    (".github/workflows/release.yml", "release-workflow.yml"),
)


def file_identity(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular file: {path.name}")
    content = path.read_bytes()
    return {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def copy_evidence(source: Path, destination: Path) -> None:
    file_identity(source)
    if destination.exists():
        raise ValueError(f"Duplicate release evidence name: {destination.name}")
    shutil.copyfile(source, destination)


def verify_qualification(root: Path, dist: Path, evidence: Path) -> dict:
    file_identity(evidence)
    report = json.loads(evidence.read_text(encoding="utf-8"))
    if report.get("status") != "passed" or report.get("installation", {}).get("status") != "passed":
        raise ValueError("Release candidates must pass fresh-install qualification")
    actual = verify_artifacts(root, dist)
    if report.get("artifacts") != actual:
        raise ValueError("Candidate archives differ from qualification evidence")
    return report


def copy_reports(root: Path, reports: Path, evidence: Path, destination: Path) -> None:
    for name in REQUIRED_REPORTS:
        source = reports / name
        file_identity(source)
        json.loads(source.read_text(encoding="utf-8"))
        copy_evidence(source, destination / name)
    copy_evidence(evidence, destination / "qualification.json")
    copy_evidence(evidence.with_suffix(".log"), destination / "qualification.log")
    for source, name in POLICY_INPUTS:
        copy_evidence(root / source, destination / name)


def write_manifest(output: Path, metadata: dict) -> None:
    files = sorted(path for path in output.rglob("*") if path.is_file())
    identities = {path.relative_to(output).as_posix(): file_identity(path) for path in files}
    if len({path.name for path in files}) != len(files):
        raise ValueError("Release asset filenames must be unique")
    metadata["artifacts"] = identities
    manifest = output / "release.json"
    manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    identities["release.json"] = file_identity(manifest)
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{identities[name]['sha256']}  {Path(name).name}\n"
            for name in sorted(identities, key=lambda name: Path(name).name)
        ),
        encoding="utf-8",
    )


def assemble(
    root: Path, dist: Path, evidence: Path, reports: Path, output: Path, *, tag: str, sha: str
) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None or git_output(root, "rev-parse", "HEAD") != sha:
        raise ValueError("Release evidence must identify the checked-out commit")
    # The release identity/main-ancestry gate runs before building; repeat the tag
    # binding here so a report bundle cannot silently identify another revision.
    if git_output(root, "rev-parse", f"refs/tags/{tag}^{{commit}}") != sha:
        raise ValueError("Release tag does not identify the candidate commit")
    report = verify_qualification(root, dist, evidence)
    if output.exists():
        raise ValueError("Release bundle output must not already exist")
    (output / "dist").mkdir(parents=True)
    (output / "reports").mkdir()
    for path in sorted(dist.iterdir()):
        copy_evidence(path, output / "dist" / path.name)
    copy_reports(root, reports, evidence, output / "reports")
    write_manifest(
        output,
        {
            "schema_version": 1,
            "tag": tag,
            "commit": sha,
            "version": report["version"],
            "created_at": datetime.now(UTC).isoformat(),
            "scanner": {
                "name": "osv-scanner",
                "version": os.environ.get("RELEASE_OSV_VERSION", "2.7.1"),
            },
            "runtime_sbom_scope": (
                "Reference fresh installations; not a universal or bundled dependency set"
            ),
            "tooling_sbom_scope": "Development Python lockfile",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assemble(
        ROOT,
        args.dist,
        args.evidence,
        args.reports,
        args.output,
        tag=os.environ["RELEASE_TAG"],
        sha=os.environ.get("GITHUB_SHA") or git_output(ROOT, "rev-parse", "HEAD"),
    )


if __name__ == "__main__":
    main()
