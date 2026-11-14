"""Compact badge observations and SVG artifacts, without drafts or remote writes."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import TYPE_CHECKING

from best_practices_mcp.badgeapp import (
    ORIGIN,
    _optional_text,
    _positive_integer,
    _record,
    _upstream,
)
from best_practices_mcp.errors import DomainError

if TYPE_CHECKING:
    from best_practices_mcp.http import BadgeAppHTTP, FetchResult

FAMILIES = {
    "best_practices": ("badge", "passing", "OpenSSF Best Practices"),
    "baseline": ("baseline", "baseline-1", "OpenSSF Baseline"),
}
EARNED_LEVELS = {
    "best_practices": frozenset({"passing", "silver", "gold"}),
    "baseline": frozenset({"baseline-1", "baseline-2", "baseline-3"}),
}
BASELINE_PROGRESS = re.compile(r"baseline-pct-(?:0|[1-9][0-9]?)\Z")
RFC3339 = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])\Z"
)
SERVICE_ATTRIBUTION = "OpenSSF Best Practices badge contributors"
ATTRIBUTION_CAVEAT = (
    "Service credit identifies the BadgeApp source; this endpoint does not supply "
    "project-entry attribution or license fields."
)


def _family(project_id: int, family: str) -> tuple[str, str, str]:
    _positive_integer(project_id, "project_id")
    if type(family) is not str or family not in FAMILIES:
        raise DomainError("invalid_field", "family must be best_practices or baseline.")
    return FAMILIES[family]


def _observation(result: FetchResult) -> dict:
    return {
        "source_url": result.source_url,
        "fetched_at": result.fetched_at,
        "service_attribution": SERVICE_ATTRIBUTION,
        "project_entry_attribution": None,
        "project_entry_license": None,
    }


def _badge_state(value: str | None, family: str) -> str:
    if value is None:
        return "unknown"
    if value in EARNED_LEVELS[family]:
        return "earned"
    if family == "best_practices" and value == "in_progress":
        return "in_progress"
    if family == "baseline" and BASELINE_PROGRESS.fullmatch(value):
        return "in_progress"
    return "unrecognized"


def _progress(record: dict, family: str) -> dict:
    field = "tiered_percentage" if family == "best_practices" else "badge_percentage"
    value = record.get(field)
    if value is not None and (
        type(value) not in (int, float) or (type(value) is float and not math.isfinite(value))
    ):
        raise _upstream("A public badge progress field has an unexpected value.", field)
    return {
        "field": field,
        "value": value,
        "level": "baseline-1" if family == "baseline" else None,
    }


def _timestamp_status(value: str | None) -> str:
    if value is None:
        return "missing"
    if RFC3339.fullmatch(value) is None:
        return "invalid"
    try:
        datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
    except ValueError:
        return "invalid"
    return "valid"


async def get_project_badge_status(
    http: BadgeAppHTTP, project_id: int, family: str = "best_practices"
) -> dict:
    """Read one family-specific observation without fetching detailed project answers."""
    suffix, _, _ = _family(project_id, family)
    result = await http.get_json(f"/projects/{project_id}/{suffix}.json")
    record = _record(result.data, project_id)
    badge_level = _optional_text(record, "badge_level")
    updated_at = _optional_text(record, "updated_at")
    return {
        "schema_version": 1,
        "project": {"project_id": record["id"], "name": _optional_text(record, "name")},
        "family": family,
        "badge_level": badge_level,
        "badge_state": _badge_state(badge_level, family),
        "progress": _progress(record, family),
        "updated_at": updated_at,
        "updated_at_status": _timestamp_status(updated_at),
        "observation": _observation(result),
        "caveats": [
            "updated_at is the reported project-record update time; fetched_at is when this "
            "response was retrieved. To compare specific saved answers, use get_project_progress.",
            ATTRIBUTION_CAVEAT,
        ],
    }


def _svg_artifact(svg: object, project_id: int, suffix: str) -> dict:
    if type(svg) is not str:
        raise _upstream("The public badge image must contain SVG text.")
    try:
        size = len(svg.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise _upstream("The public badge image must contain valid UTF-8 text.") from exc
    return {
        "svg": svg,
        "media_type": "image/svg+xml",
        "suggested_filename": f"bestpractices-{project_id}-{suffix}.svg",
        "encoded_size_bytes": size,
    }


async def get_project_badge_svg(http: BadgeAppHTTP, project_id: int, family: str) -> dict:
    """Fetch one SVG snapshot and construct dynamic embedding links for the host."""
    suffix, section, label = _family(project_id, family)
    path = f"/projects/{project_id}/{suffix}.svg"
    result = await http.get_svg(path)
    image_url = ORIGIN + path
    project_url = f"{ORIGIN}/en/projects/{project_id}/{section}"
    return {
        "schema_version": 1,
        "project_id": project_id,
        "family": family,
        "image_url": image_url,
        "project_url": project_url,
        "markdown": f"[![{label} — project {project_id}]({image_url})]({project_url})",
        "artifact": _svg_artifact(result.data, project_id, suffix),
        "observation": _observation(result),
        "caveats": [
            "The downloaded SVG is a snapshot. The dynamic image URL can reflect later badge "
            "changes, subject to upstream caching.",
            "The SVG is returned as data without rendering or execution; the host decides "
            "whether to save the artifact or insert the Markdown snippet.",
            ATTRIBUTION_CAVEAT,
        ],
    }
