"""Shared section selection and observed proposal compatibility advisories."""

from best_practices_mcp.criteria import catalog_levels, catalog_reference, criterion_definitions
from best_practices_mcp.errors import DomainError


def section_catalog(section: str) -> dict:
    """Keep level-qualified definitions when section selection is deferred."""
    if section is None:
        raise DomainError("invalid_level", "Select a badge level or choose_section.")
    levels = catalog_levels() if section == "choose_section" else [section]
    return {
        "criteria": [criterion for level in levels for criterion in criterion_definitions(level)],
        "catalog": catalog_reference(),
    }


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
                "overrides, despite conflicting BadgeApp documentation."
            ),
            "observed_on": "2026-11-16",
        }
    ]
