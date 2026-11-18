"""Prepare one deterministic URL using BadgeApp's documented query proposal route."""

from typing import Any
from urllib.parse import quote, urlencode

from best_practices_mcp.compatibility import unknown_status_warnings
from best_practices_mcp.transfer import (
    finish_result,
    override_scope,
    transfer_context,
    transfer_rows,
)

ORIGIN = "https://www.bestpractices.dev"


def prepare_update_url(
    project_id: int,
    section: str,
    draft: dict[str, Any],
    record: dict[str, Any],
    observation: dict[str, Any],
    overrides: Any = None,
) -> dict[str, Any]:
    """Encode supplied values and override intent without changing answer text."""
    draft, criteria, scope, result = transfer_context(
        project_id, section, draft, record, observation
    )
    requested, effective = override_scope(
        {"mode": "none"} if overrides is None else overrides, draft, scope
    )
    rows = transfer_rows(draft, criteria, scope, effective)
    encoded = {item["field"] for item in rows if item["disposition"] == "encoded"}
    effective.intersection_update(encoded)
    result.update(
        overrides=requested,
        effective_overrides=sorted(effective),
        warnings=unknown_status_warnings(draft, encoded),
        artifact=None,
    )
    if finish_result(result, rows):
        params = {field: draft[field] for field in encoded}
        if effective:
            params["overrides"] = "*" if requested["mode"] == "all" else ",".join(sorted(effective))
        query = urlencode(sorted(params.items()), quote_via=quote)
        route = "choose" if section == "choose_section" else section
        url = f"{ORIGIN}/en/projects/{project_id}/{route}/edit?{query}"
        result["artifact"] = {"url": url, "encoded_size_bytes": len(url.encode("utf-8"))}
    return result
