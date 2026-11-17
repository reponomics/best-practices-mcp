"""Classify supplied fields for artifact generation without comparing saved answers."""

from collections import defaultdict
from typing import Any

from best_practices_mcp.compatibility import section_catalog
from best_practices_mcp.criteria import get_criteria
from best_practices_mcp.drafts import (
    METADATA_FIELDS,
    PROVENANCE_FIELDS,
    VALID_STATUSES,
    check_identity,
    field_definitions,
    normalize_draft,
)
from best_practices_mcp.errors import DomainError


def _criteria_by_id(catalog):
    criteria = defaultdict(list)
    for item in catalog["criteria"]:
        criteria[item["criterion_id"]].append(item)
    return criteria


def transfer_context(project_id, section, draft, record, observation):
    """Resolve shared source context without performing I/O or inventing answers."""
    catalog = section_catalog(section)
    normalized = normalize_draft(draft)
    identity = check_identity(project_id, normalized, record=record, check_repo=True)
    criteria = _criteria_by_id(catalog)
    scope = set(METADATA_FIELDS)
    for item in catalog["criteria"]:
        scope.update((item["status_field"], item["justification_field"]))
    result = {
        "schema_version": 2,
        "project_id": project_id,
        "section": section,
        "catalog": catalog["catalog"],
        "draft_source": {"kind": "explicit", "location": None},
        "observation": dict(observation),
        "identity": identity,
    }
    return normalized, criteria, scope, result


def _override_fields(requested, draft, scope):
    fields = requested.get("fields")
    if set(requested) != {"mode", "fields"} or type(fields) is not list or not fields:
        raise DomainError("invalid_override", "Selected overrides require a nonempty fields list.")
    for field in fields:
        if type(field) is not str or field not in scope or field not in draft:
            raise DomainError("invalid_override", "Override must name a supplied in-scope field.")
    return sorted(set(fields))


def override_scope(requested, draft, scope):
    """Resolve an explicit none, all, or selected-fields override intention."""
    if type(requested) is not dict or requested.get("mode") not in ("none", "all", "fields"):
        raise DomainError("invalid_override", "Overrides must choose none, all, or fields mode.")
    mode = requested["mode"]
    if mode == "fields":
        fields = _override_fields(requested, draft, scope)
        return {"mode": mode, "fields": fields}, set(fields)
    if set(requested) != {"mode"}:
        raise DomainError("invalid_override", "Only fields mode accepts a fields list.")
    return {"mode": mode}, set(draft) & scope if mode == "all" else set()


def row(field, disposition, reason, override=False):
    return {
        "field": field,
        "disposition": disposition,
        "reason": reason,
        "override": override,
        "applicable_levels": [],
        "restrictions": [],
    }


def _status_problem(value, criterion):
    if type(value) is not str:
        return "invalid_type"
    if value not in VALID_STATUSES:
        return "invalid_status"
    if value == "N/A" and not criterion["na_allowed"]:
        return "na_not_supported"
    return None


def _answer_problem(field, draft, definition, criterion):
    kind = definition["kind"]
    if kind == "status":
        return _status_problem(draft[field], criterion)
    if kind == "justification":
        status = criterion["status_field"]
        if status in draft and _status_problem(draft[status], criterion):
            return "invalid_companion_status"
    if type(draft[field]) is not str:
        return "invalid_type"
    return None


def _scope_problem(field, scope, definitions):
    if field in PROVENANCE_FIELDS:
        return row(field, "omitted", "provenance_not_editable")
    if field not in definitions:
        return row(field, "unsupported", "unknown_field")
    if field not in scope:
        return row(field, "outside_level", "outside_selected_level")
    return None


def _value_report(field, draft, definition, candidates):
    restrictions = []
    for criterion in candidates:
        problem = _answer_problem(field, draft, definition, criterion)
        if problem:
            restrictions.append({"level": criterion["level"], "reason": problem})
    if len(restrictions) == len(candidates):
        problem = restrictions[0]["reason"]
        disposition = "omitted" if problem == "invalid_companion_status" else "invalid"
        report = row(field, disposition, problem)
    else:
        report = row(field, "encoded", "eligible_field")
    report["restrictions"] = restrictions
    return report


def _field_report(field, draft, criteria, scope, definitions):
    report = _scope_problem(field, scope, definitions)
    if report is not None:
        return report
    definition = definitions[field]
    if definition["kind"] == "metadata":
        if type(draft[field]) is not str:
            return row(field, "invalid", "invalid_type")
        return row(field, "encoded", "eligible_field")
    return _value_report(field, draft, definition, criteria[definition["criterion_id"]])


def transfer_rows(draft, criteria, scope, overrides):
    """Report inclusion, applicable levels and restrictions for each supplied field."""
    definitions = field_definitions()
    all_criteria = _criteria_by_id(section_catalog("choose_section"))
    levels = get_criteria()["levels"]
    rows = []
    for field in sorted(draft):
        report = _field_report(field, draft, criteria, scope, definitions)
        if field in METADATA_FIELDS:
            report["applicable_levels"] = levels
        elif field in definitions:
            identifier = definitions[field]["criterion_id"]
            report["applicable_levels"] = [item["level"] for item in all_criteria[identifier]]
        report["override"] = report["disposition"] == "encoded" and field in overrides
        rows.append(report)
    return rows


def finish_result(result: dict[str, Any], rows):
    requested = [item for item in rows if item["field"] not in PROVENANCE_FIELDS]
    encoded = any(item["disposition"] == "encoded" for item in requested)
    omitted = any(
        item["disposition"] in {"unsupported", "invalid", "omitted"} for item in requested
    )
    if encoded:
        outcome = "partial" if omitted else "complete"
    elif omitted:
        outcome = "no_transferable_changes"
    else:
        outcome = "no_supplied_transferable_answers"
    result.update(outcome=outcome, no_artifact_reason=None if encoded else outcome, transfer=rows)
    return encoded
