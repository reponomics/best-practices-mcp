"""Badge SVG artifacts and embedding links, without drafts or remote writes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from best_practices_mcp.badgeapp import ORIGIN, _positive_integer, _upstream
from best_practices_mcp.errors import DomainError

if TYPE_CHECKING:
    from best_practices_mcp.http import BadgeAppHTTP, FetchResult

FAMILIES = {
    "best_practices": ("badge", "passing", "OpenSSF Best Practices"),
    "baseline": ("baseline", "baseline-1", "OpenSSF Baseline"),
}
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
