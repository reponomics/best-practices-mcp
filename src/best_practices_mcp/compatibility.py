"""Shared section selection and observed proposal compatibility advisories."""

from best_practices_mcp.criteria import get_criteria
from best_practices_mcp.errors import DomainError


def section_catalog(section: str) -> dict:
    """Keep level-qualified definitions when section selection is deferred."""
    if section is None:
        raise DomainError("invalid_level", "Select a badge level or choose_section.")
    if section != "choose_section":
        return get_criteria(section)
    catalog = get_criteria()
    catalog["criteria"] = [
        criterion for level in catalog["levels"] for criterion in get_criteria(level)["criteria"]
    ]
    return catalog


def unknown_status_warnings(draft: dict, fields) -> list[dict]:
    affected = sorted(
        field for field in fields if field.endswith("_status") and draft.get(field) == "?"
    )
    if not affected:
        return []
    return [
        {
            "code": "unknown_status_reset_unsupported",
            "fields": affected,
            "message": (
                "URL proposals to reset a status to '?' are observed not to work, even with "
                "overrides, despite conflicting BadgeApp documentation. Set the status manually "
                "in BadgeApp if a reset is intended."
            ),
            "observed_on": "2026-11-16",
            "scope": "Silver and Baseline Level 2 previews.",
        }
    ]
