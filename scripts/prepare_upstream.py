"""Prepare retained sources and generated data for review."""

from __future__ import annotations

import html
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from generate_catalog import catalog_content, encoded

if TYPE_CHECKING:
    from check_upstream import GitHub, Report


def source_timestamp(client: GitHub, sha: str) -> str:
    commit = client.api(f"/repos/ossf/best-practices-badge/git/commits/{sha}")
    if commit["sha"] != sha:
        raise ValueError("Unexpected source commit metadata")
    date = datetime.fromisoformat(commit["committer"]["date"].replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Source commit timestamp must include a timezone")
    return date.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_snapshot(
    report: Report, timestamp: str, directory: Path
) -> tuple[dict[str, bytes], str | None]:
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


def apply_snapshot(root: Path, report: Report, staged: Path, generated: dict[str, bytes]) -> None:
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


def error_text(value: str) -> str:
    return html.escape(value[:1500]).replace("@", "&#64;")


def preparation_body(result: dict[str, Any]) -> str:
    if not result["changed"]:
        return ""
    lines = ["", "## Preparation", ""]
    if result["generation_error"]:
        lines.extend(
            [
                "**Catalog generation failed.** The updated source inputs "
                "are included; the previous generated files remain unchanged. Fix generation and "
                "run `make catalog` before merging. CI must pass.",
                "",
                f"<pre>{error_text(result['generation_error'])}</pre>",
            ]
        )
    else:
        lines.append("Catalog and provenance regenerated successfully. CI still needs to pass.")
    lines.extend(
        [
            "",
            "Review changes to requirements, wording, documentation and notices in the diff.",
            "",
            "To make manual fixes on this generated branch, first set the repository variable "
            "`UPSTREAM_UPDATES_PAUSED=true`. Re-enable updates after merging or finishing the fix. "
            "The automation otherwise regenerates the branch from main.",
        ]
    )
    return "\n".join(lines) + "\n"


def prepare_update(client: GitHub, report: Report, root: Path, output: Path) -> str:
    result: dict[str, Any] = {"changed": bool(report.changed), "generation_error": None}
    if report.changed:
        timestamp = source_timestamp(client, report.production_revision)
        with tempfile.TemporaryDirectory(prefix="badgeapp-sources-") as temporary:
            staged = Path(temporary)
            generated, result["generation_error"] = build_snapshot(report, timestamp, staged)
            apply_snapshot(root, report, staged, generated)
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_bytes(encoded(result))
    return preparation_body(result)
