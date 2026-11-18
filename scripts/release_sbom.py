"""Create public reference-installation evidence without altering release archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

PROJECT = "best-practices-mcp"


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def public_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "urn:redacted:local-source"
    host = parsed.hostname
    if parsed.port:
        host += f":{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def public_data(value: Any) -> Any:
    """Drop credentials, URL query strings and absolute local paths recursively."""
    if isinstance(value, dict):
        return {key: public_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [public_data(item) for item in value]
    if isinstance(value, str):
        if value.startswith(("https://", "http://", "file:")):
            return public_url(value)
        if value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value):
            return "<local-path>"
    return value


def installation_packages(report: dict[str, Any]) -> list[dict[str, Any]]:
    """The pip install report identifies the resolved runtime dependency closure."""
    if report.get("version") != "1" or not isinstance(report.get("install"), list):
        raise ValueError("Expected a version-one pip installation report")
    packages = []
    names = set()
    for item in report["install"]:
        metadata = item["metadata"]
        name, version = metadata["name"], metadata["version"]
        if not isinstance(name, str) or not isinstance(version, str) or not version:
            raise ValueError("Invalid installed package identity")
        canonical = normalized(name)
        if canonical in names:
            raise ValueError("Duplicate package in installation report")
        names.add(canonical)
        packages.append({"name": name, "version": version, "ecosystem": "PyPI"})
    if PROJECT not in names:
        raise ValueError("Installation report does not contain the release candidate")
    return sorted(packages, key=lambda package: normalized(package["name"]))


def sanitized_installation(report: dict[str, Any]) -> dict[str, Any]:
    """Publish only installation facts, never full descriptions or local paths."""
    selected = []
    for item in report["install"]:
        download = item.get("download_info", {})
        selected.append(
            {
                "metadata": {key: item["metadata"][key] for key in ("name", "version")},
                "requested": item.get("requested", False),
                "is_direct": item.get("is_direct", False),
                "download_info": {
                    "url": public_url(download.get("url", "")),
                    "archive_info": download.get("archive_info", {}),
                },
            }
        )
    installation: dict[str, Any] = public_data(
        {
            "version": report["version"],
            "pip_version": report.get("pip_version"),
            "environment": report.get("environment", {}),
            "install": selected,
        }
    )
    return installation


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def annotate_sbom(
    document: dict[str, Any], artifact: Path, installation: dict[str, Any], source_sha: str
) -> dict[str, Any]:
    if document.get("bomFormat") != "CycloneDX" or document.get("specVersion") != "1.6":
        raise ValueError("Expected CycloneDX JSON 1.6")
    metadata = document["metadata"]
    component = metadata["component"]
    if normalized(component.get("name", "")) != PROJECT:
        raise ValueError("SBOM root component must identify the release candidate")
    component["hashes"] = [
        {"alg": "SHA-256", "content": hashlib.sha256(artifact.read_bytes()).hexdigest()}
    ]
    facts = {
        "scope": "reference installation; includes environment bootstrap tools",
        "artifact": artifact.name,
        "source-commit": source_sha,
        "created-at": datetime.now(UTC).isoformat(),
        "python": installation.get("environment", {}).get("python_full_version", "unknown"),
        "platform": installation.get("environment", {}).get("platform_system", "unknown"),
        "machine": installation.get("environment", {}).get("platform_machine", "unknown"),
    }
    metadata.setdefault("properties", []).extend(
        {"name": f"reponomics:reference-installation:{key}", "value": value}
        for key, value in facts.items()
    )
    annotated: dict[str, Any] = public_data(document)
    return annotated


def generate_reference(
    artifact: Path,
    runtime_python: Path,
    tool_python: Path,
    installation_path: Path,
    output: Path,
    root: Path,
    source_sha: str,
    run: Callable[[str, list[str]], Any],
) -> dict[str, str]:
    kind = "wheel" if artifact.suffix == ".whl" else "sdist"
    installation = json.loads(installation_path.read_text(encoding="utf-8"))
    packages = installation_packages(installation)
    output.mkdir(parents=True, exist_ok=True)
    sbom = output / f"runtime-{kind}.cdx.json"
    raw_sbom = installation_path.parent / "reference-sbom.json"
    run(
        f"{kind}: generate reference SBOM",
        [
            str(tool_python),
            "-m",
            "cyclonedx_py",
            "environment",
            str(runtime_python),
            "--pyproject",
            str(root / "pyproject.toml"),
            "--spec-version",
            "1.6",
            "--output-format",
            "JSON",
            "--output-file",
            str(raw_sbom),
            "--validate",
        ],
    )
    document = json.loads(raw_sbom.read_text(encoding="utf-8"))
    write_json(sbom, annotate_sbom(document, artifact, installation, source_sha))
    run(
        f"{kind}: validate public SBOM",
        [str(tool_python), str(Path(__file__).resolve()), "--validate", str(sbom)],
    )
    inventory = output / f"runtime-{kind}.inventory.json"
    write_json(
        inventory,
        {
            "results": [
                {
                    "packages": [
                        {"package": package}
                        for package in packages
                        if normalized(package["name"]) != PROJECT
                    ]
                }
            ]
        },
    )
    pip_report = output / f"pip-{kind}.json"
    write_json(pip_report, sanitized_installation(installation))
    return {"sbom": sbom.name, "inventory": inventory.name, "installation": pip_report.name}


def main() -> None:
    from cyclonedx.schema import SchemaVersion
    from cyclonedx.validation.json import JsonStrictValidator

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", type=Path, required=True)
    args = parser.parse_args()
    errors = JsonStrictValidator(SchemaVersion.V1_6).validate_str(args.validate.read_text())
    if errors is not None:
        raise ValueError("Public SBOM failed CycloneDX schema validation")


if __name__ == "__main__":
    main()
