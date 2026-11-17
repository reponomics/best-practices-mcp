"""Offline mechanical checks of represented answers using the pinned catalog."""

import re
from typing import Any

from best_practices_mcp.compatibility import section_catalog, unknown_status_warnings
from best_practices_mcp.drafts import (
    check_identity,
    field_definitions,
    normalize_draft,
    structural_issues,
)

_URL = re.compile(r"https?://[^/. ]+\.[^ ]")
_CONDITIONAL_CHECKS = ["conditional_requirements"]


def usable_justification(value: Any) -> bool:
    """Apply the agreed advisory minimum length and exact comment prefix."""
    return type(value) is str and len(value) >= 5 and not value.startswith("// ")


def contains_url(value: Any) -> bool:
    """Apply the agreed advisory URL pattern without parsing or fetching URLs."""
    return type(value) is str and not value.startswith("// ") and _URL.search(value) is not None


def _finding(criterion: dict, field: str, code: str, requirement: str, message: str) -> dict:
    return {
        "criterion_id": criterion["criterion_id"],
        "level": criterion["level"],
        "field": field,
        "code": code,
        "requirement": requirement,
        "message": message,
    }


def _requires_justification(criterion: dict, status: str) -> bool:
    # A required URL entails usable justification. Report the stronger URL
    # requirement alone, matching upstream's ordered Met checks.
    if status == "Met" and criterion["met_url_required"]:
        return False
    flag = {"Met": "met_justification_required", "N/A": "na_justification_required"}.get(status)
    return flag is not None and criterion[flag]


def _conditional_findings(criterion: dict, status: str, justification: Any) -> list[dict]:
    findings = []
    if status == "N/A" and not criterion["na_allowed"]:
        findings.append(
            _finding(
                criterion,
                criterion["status_field"],
                "na_not_allowed",
                "na_allowed",
                "This criterion does not allow N/A.",
            )
        )
    if _requires_justification(criterion, status) and not usable_justification(justification):
        findings.append(
            _finding(
                criterion,
                criterion["justification_field"],
                "missing_required_justification",
                f"{status}: justification of at least five characters, not prefixed // ",
                "Required usable justification is missing.",
            )
        )
    if status == "Met" and criterion["met_url_required"] and not contains_url(justification):
        findings.append(
            _finding(
                criterion,
                criterion["justification_field"],
                "missing_required_url",
                "met_url_required",
                "Required URL text is missing.",
            )
        )
    return findings


def _skip_reason(draft: dict, criterion: dict) -> str | None:
    field = criterion["status_field"]
    if field not in draft:
        return "status_absent"
    status = draft[field]
    if status == "?":
        return "status_unknown"
    if type(status) is not str or status not in {"Met", "Unmet", "N/A"}:
        return "status_invalid"
    return None


def _shape_findings(draft: dict, selected: list[dict], fields: dict) -> list[dict]:
    levels = {}
    for criterion in selected:
        levels.setdefault(criterion["criterion_id"], []).append(criterion["level"])
    findings = []
    for issue in structural_issues(draft):
        definition = fields.get(issue["field"], {})
        criterion_id = definition.get("criterion_id")
        applicable = [None] if criterion_id is None else levels.get(criterion_id, [])
        findings.extend(
            {
                **issue,
                "criterion_id": criterion_id,
                "level": level,
                "requirement": "recognized_field_shape" if definition else "recognized_field",
            }
            for level in applicable
        )
    return findings


def _represented(draft: dict, fields: dict) -> set[str]:
    return {
        fields[field]["criterion_id"]
        for field in draft
        if field in fields and fields[field]["criterion_id"] is not None
    }


def _identity(criterion: dict) -> dict:
    return {"level": criterion["level"], "criterion_id": criterion["criterion_id"]}


def _other_level_skips(represented: set[str], selected: list[dict]) -> list[dict]:
    outside = represented - {criterion["criterion_id"] for criterion in selected}
    if not outside:
        return []
    return [
        {
            **_identity(criterion),
            "reason": "other_level",
            "checks": ["field_shape", *_CONDITIONAL_CHECKS],
        }
        for criterion in section_catalog("choose_section")["criteria"]
        if criterion["criterion_id"] in outside
    ]


def _check_criterion(document: dict, criterion: dict) -> tuple[list[dict], list[dict]]:
    reason = _skip_reason(document, criterion)
    if reason is not None:
        return [], [{**_identity(criterion), "reason": reason, "checks": list(_CONDITIONAL_CHECKS)}]
    return _conditional_findings(
        criterion,
        document[criterion["status_field"]],
        document.get(criterion["justification_field"]),
    ), []


def validate_draft(project_id: int, section: str, draft: dict[str, Any]) -> dict:
    """Report level-qualified checks of supplied answers, without completing them."""
    catalog = section_catalog(section)
    document = normalize_draft(draft)
    identity = check_identity(project_id, document)
    fields = field_definitions()
    represented = _represented(document, fields)
    selected = catalog["criteria"]
    checked = [criterion for criterion in selected if criterion["criterion_id"] in represented]
    findings = _shape_findings(document, selected, fields)
    skipped = _other_level_skips(represented, selected)
    for criterion in checked:
        criterion_findings, criterion_skips = _check_criterion(document, criterion)
        findings.extend(criterion_findings)
        skipped.extend(criterion_skips)
    return {
        "schema_version": 2,
        "project_id": project_id,
        "section": section,
        "draft_source": {"kind": "explicit", "location": None},
        "identity": identity,
        "catalog": catalog["catalog"],
        "findings": sorted(
            findings,
            key=lambda finding: (finding["field"], finding["level"] or "", finding["code"]),
        ),
        "checked_criteria": sorted(
            (_identity(criterion) for criterion in checked),
            key=lambda item: (item["level"], item["criterion_id"]),
        ),
        "skipped_criteria": sorted(skipped, key=lambda item: (item["level"], item["criterion_id"])),
        "warnings": unknown_status_warnings(
            document, {criterion["status_field"] for criterion in selected}
        ),
    }
