"""Prepare retained sources, generated data and maintained documentation for review."""

from __future__ import annotations

import html
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml
from generate_catalog import SourceLoader, catalog_content, encoded, flatten

DOC_PINS = (
    "docs/upstream-compatibility.md",
    "docs/transfer-rules.md",
    "docs/design.md",
    "docs/specification.md",
    "THIRD_PARTY_NOTICES.md",
)


def criterion_ids(contents: dict[str, bytes | None]) -> set[str]:
    """Compare identities only; this advisory never judges requirement semantics."""
    result = set()
    for name in ("criteria/criteria.yml", "criteria/baseline_criteria.yml"):
        raw = yaml.load(contents[name], Loader=SourceLoader)
        for level, groups in raw.items():
            if level == "_metadata":
                continue
            for criterion_id in flatten(groups):
                identity = f"{level}/{criterion_id}"
                if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", identity):
                    raise ValueError("Unrecognized level or criterion identifier")
                result.add(identity)
    return result


def id_advisory(source: Path, remote: dict[str, bytes | None]) -> dict:
    try:
        before = criterion_ids({name: (source / name).read_bytes() for name in remote})
        after = criterion_ids(remote)
        return {"added": sorted(after - before), "removed": sorted(before - after), "error": None}
    except Exception as exc:
        # A schema change must reach the PR even when this advisory cannot parse it.
        return {"added": [], "removed": [], "error": f"{type(exc).__name__}: {exc}"}


def source_timestamp(client, sha: str) -> str:
    commit = client.api(f"/repos/ossf/best-practices-badge/git/commits/{sha}")
    if commit["sha"] != sha:
        raise ValueError("Unexpected source commit metadata")
    date = datetime.fromisoformat(commit["committer"]["date"].replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Source commit timestamp must include a timezone")
    return date.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_snapshot(report, timestamp: str, directory: Path) -> tuple[dict[str, bytes], str | None]:
    """Generate before applying writes; retain a reviewable source patch on failure."""
    sources = {
        name: content for name, content in report.production_files.items() if content is not None
    }
    for name, content in sources.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = {
        "repository": "https://github.com/ossf/best-practices-badge",
        "revision": report.production_revision,
        "generated_at": timestamp,
        "files": {name: digest for name, digest in report.production_hashes.items() if digest},
    }
    (directory / "source.json").write_bytes(encoded(manifest))
    missing = [name for name, content in report.production_files.items() if content is None]
    if missing:
        return {}, "Retained upstream source files are missing: " + ", ".join(sorted(missing))
    try:
        return catalog_content(directory), None
    except Exception as exc:
        # CI must reject stale generated data, but the proposed input change remains reviewable.
        return {}, f"{type(exc).__name__}: {exc}".replace(str(directory), "<sources>")


def apply_snapshot(root: Path, report, staged: Path, generated: dict[str, bytes]) -> None:
    source = root / "vendor/badgeapp"
    for name, content in report.production_files.items():
        path = source / name
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    (source / "source.json").write_bytes((staged / "source.json").read_bytes())
    for name, content in generated.items():
        (root / "src/best_practices_mcp/data" / name).write_bytes(content)
    for name in DOC_PINS:
        path = root / name
        path.write_bytes(
            path.read_bytes().replace(
                report.bundled_revision.encode(), report.production_revision.encode()
            )
        )


def error_text(value: str) -> str:
    return html.escape(value[:1500]).replace("@", "&#64;")


def preparation_body(result: dict) -> str:
    if not result["changed"]:
        return ""
    lines = ["", "## Preparation", ""]
    if result["generation_error"]:
        lines.extend(
            [
                "**Catalog generation failed.** The updated source inputs and documentation pins "
                "are included; the previous generated files remain unchanged. Fix generation and "
                "run `make catalog` before merging. CI must pass.",
                "",
                f"<pre>{error_text(result['generation_error'])}</pre>",
            ]
        )
    else:
        lines.append("Catalog and provenance regenerated successfully. CI still needs to pass.")
    advisory = result["ids"]
    lines.extend(["", "## Criterion IDs (advisory)", ""])
    if advisory["error"]:
        lines.append(f"Comparison unavailable: <pre>{error_text(advisory['error'])}</pre>")
    else:
        for key in ("added", "removed"):
            values = ", ".join(f"`{value}`" for value in advisory[key]) or "none"
            lines.append(f"{key.capitalize()} (level-qualified): {values}.")
    lines.extend(
        [
            "",
            "Labels do not classify compatibility or authorize merging. Review changes to "
            "requirements, wording, documentation and notices in the diff.",
            "",
            "To make manual fixes on this generated branch, first set the repository variable "
            "`UPSTREAM_UPDATES_PAUSED=true`. Re-enable updates after merging or finishing the fix. "
            "The automation otherwise regenerates the branch from main.",
        ]
    )
    return "\n".join(lines) + "\n"


def prepare_update(client, report, root: Path, output: Path) -> str:
    result = {
        "changed": bool(report.changed),
        "ids": {"added": [], "removed": [], "error": None},
        "generation_error": None,
    }
    if report.changed:
        timestamp = source_timestamp(client, report.production_revision)
        result["ids"] = id_advisory(root / "vendor/badgeapp", report.production_files)
        # Check all managed documentation exists before modifying any repository files.
        for name in DOC_PINS:
            (root / name).read_bytes()
        with tempfile.TemporaryDirectory(prefix="badgeapp-sources-") as temporary:
            staged = Path(temporary)
            generated, result["generation_error"] = build_snapshot(report, timestamp, staged)
            apply_snapshot(root, report, staged, generated)
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_bytes(encoded(result))
    return preparation_body(result)
