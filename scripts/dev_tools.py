"""Small shell-independent operations used by the canonical Makefile."""

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def show_help(makefile: Path) -> None:
    """Generate help from the Makefile's existing target annotations."""
    for line in makefile.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([a-zA-Z0-9_-]+):.*?## (.+)$", line)
        if match:
            print(f"  {match[1]:<22} {match[2]}")


def check_tooling(root: Path) -> None:
    """Check uv inventory and the checkout's first-party OSV license evidence."""
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    uv = project["tool"]["uv"]
    requirement = uv["required-version"]
    if re.fullmatch(r"==[0-9]+\.[0-9]+\.[0-9]+", requirement) is None:
        raise ValueError("tool.uv.required-version must pin an exact uv release")
    groups = project["dependency-groups"]
    if groups["audit-tools"] != [f"uv{requirement}"]:
        raise ValueError("audit-tools must match tool.uv.required-version")
    if uv.get("default-groups", ["dev"]) != ["dev"]:
        raise ValueError("Only the dev group should be installed by default")
    if any(re.match(r"uv(?:[<>=!~;\[]|$)", entry) for entry in groups["dev"]):
        raise ValueError("uv belongs in audit-tools, not the installed dev group")
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    versions = {package["version"] for package in lock["package"] if package["name"] == "uv"}
    if versions != {requirement.removeprefix("==")}:
        raise ValueError("uv.lock must contain the required uv release for OSV")
    check_first_party_license(root, project["project"], lock)
    print("uv bootstrap requirement and audit inventory agree")


def check_first_party_license(root: Path, project: dict, lock: dict) -> None:
    """Bind the version-independent correction to this MIT-licensed local project."""
    if project.get("license") != "MIT":
        raise ValueError("Reassess the first-party OSV override when the project license changes")
    packages = [package for package in lock["package"] if package["name"] == project["name"]]
    if len(packages) != 1 or packages[0].get("source") != {"editable": "."}:
        raise ValueError("The first-party OSV override requires a unique local editable root")
    policy = tomllib.loads((root / "osv-scanner.toml").read_text(encoding="utf-8"))
    overrides = [
        {key: value for key, value in entry.items() if key != "reason"}
        for entry in policy.get("PackageOverrides", [])
        if entry.get("name") == project["name"]
    ]
    expected = {
        "name": project["name"],
        "ecosystem": "PyPI",
        "license": {"override": [project["license"]]},
    }
    if overrides != [expected]:
        raise ValueError("Require one first-party MIT license override without filters or ignores")


def check_distributions(dist: Path) -> None:
    """Pass distribution filenames to Twine without relying on shell globbing."""
    artifacts = sorted([*dist.glob("*.whl"), *dist.glob("*.tar.gz")])
    if not artifacts:
        raise ValueError("No wheel or source distribution found")
    subprocess.run(
        [sys.executable, "-m", "twine", "check", "--strict", *map(str, artifacts)],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("help")
    sub.add_parser("tooling-check")
    artifacts = sub.add_parser("check-dist")
    artifacts.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "help":
        show_help(ROOT / "Makefile")
    elif args.command == "tooling-check":
        check_tooling(ROOT)
    else:
        check_distributions(args.dist)


if __name__ == "__main__":
    main()
