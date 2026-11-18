"""Pure, bounded draft normalization, patching, and provenance checks."""

from typing import Any
from urllib.parse import urlsplit

from best_practices_mcp.criteria import catalog_levels, criterion_definitions, field_aliases
from best_practices_mcp.documents import normalize_document, serialize_document
from best_practices_mcp.errors import DomainError

METADATA_FIELDS = frozenset({"name", "description", "license", "implementation_languages"})
PROVENANCE_FIELDS = frozenset({"id", "repo_url"})
VALID_STATUSES = frozenset({"Met", "Unmet", "N/A", "?"})
STATUS_MESSAGE = 'Status must be exactly "Met", "Unmet", "N/A" or "?".'


def field_definitions() -> dict[str, dict[str, Any]]:
    """Describe every writable canonical field without choosing a badge level."""
    fields = {field: {"kind": "metadata", "criterion_id": None} for field in METADATA_FIELDS}
    for level in catalog_levels():
        for criterion in criterion_definitions(level):
            for kind in ("status", "justification"):
                fields[criterion[f"{kind}_field"]] = {
                    "kind": kind,
                    "criterion_id": criterion["criterion_id"],
                }
    return fields


def normalize_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Copy a readable document, resolving only pinned, explicit aliases."""
    return normalize_document(draft, field_aliases())


def _field_issue(
    field: str, value: Any, definition: dict[str, Any] | None
) -> dict[str, Any] | None:
    if definition is None:
        if field in PROVENANCE_FIELDS:
            return None
        return {"field": field, "code": "unknown_field", "message": "Unrecognized field preserved."}
    if type(value) is not str:
        return {"field": field, "code": "invalid_type", "message": "Field must be a string."}
    if definition["kind"] == "status" and value not in VALID_STATUSES:
        return {"field": field, "code": "invalid_status", "message": STATUS_MESSAGE}
    return None


def structural_issues(draft: dict[str, Any]) -> list[dict[str, str]]:
    """Describe known answer shape and unfamiliar fields, without credit rules."""
    fields = field_definitions()
    issues = [_field_issue(field, value, fields.get(field)) for field, value in draft.items()]
    return sorted(
        (issue for issue in issues if issue is not None), key=lambda issue: issue["field"]
    )


def build_draft(draft: dict[str, Any], changes: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply a canonical patch atomically in memory, allowing repairs before validation."""
    candidate = normalize_draft(draft)
    patch = normalize_draft({} if changes is None else changes)
    writable = field_definitions()
    for field, value in patch.items():
        if value is None:
            candidate.pop(field, None)
        elif field not in writable:
            raise DomainError(
                "invalid_field", "Patch field is not writable.", details={"field": field}
            )
        else:
            candidate[field] = value
    issues = structural_issues(candidate)
    invalid = [issue for issue in issues if issue["code"] != "unknown_field"]
    if invalid:
        raise DomainError(
            "invalid_field",
            "Draft contains invalid answer fields.",
            details={"issues": invalid},
            recovery="Correct each listed field as its message describes and try again.",
        )
    return {
        "schema_version": 1,
        "draft": candidate,
        "issues": issues,
        "serialized_size_bytes": len(serialize_document(candidate)),
    }


def _check_id(project_id: int, draft: dict[str, Any]) -> str:
    if type(project_id) is not int or project_id <= 0:
        raise DomainError("project_identity_unresolved", "Project ID must be a positive integer.")
    if "id" not in draft:
        return "absent"
    identity = draft["id"]
    if type(identity) is not int or identity <= 0:
        raise DomainError("project_identity_unresolved", "Document ID is not a positive integer.")
    if identity != project_id:
        raise DomainError("project_mismatch", "Document ID does not match the requested project.")
    return "matched"


def _comparable_repo(value: Any) -> tuple[Any, ...]:
    """Normalize only scheme, hostname and a scheme's default port."""
    if type(value) is not str or any(
        ord(character) <= 32 or character.isspace() for character in value
    ):
        raise ValueError("Repository URL must be a string without whitespace.")
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Repository URL must be absolute HTTP(S).")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Repository URL must not include credentials.")
    port = parsed.port
    if port == {"http": 80, "https": 443}[parsed.scheme.lower()]:
        port = None
    return (
        parsed.scheme.lower(),
        parsed.hostname.lower(),
        port,
        parsed.path,
        parsed.query,
        parsed.fragment,
    )


def _check_repo(draft: dict[str, Any], record: dict[str, Any] | None) -> str:
    if "repo_url" not in draft:
        return "absent"
    try:
        supplied = _comparable_repo(draft["repo_url"])
        observed = _comparable_repo(None if record is None else record.get("repo_url"))
    except ValueError as exc:
        raise DomainError(
            "project_identity_unresolved", "Repository provenance cannot be compared."
        ) from exc
    if supplied != observed:
        raise DomainError("project_mismatch", "Repository provenance does not match the project.")
    return "matched"


def check_identity(
    project_id: int,
    draft: dict[str, Any],
    *,
    record: dict[str, Any] | None = None,
    check_repo: bool = False,
) -> dict[str, str]:
    """Check supplied provenance; this establishes association, not authentication."""
    return {
        "association": "document_provenance"
        if PROVENANCE_FIELDS.intersection(draft)
        else "explicit_target",
        "id_check": _check_id(project_id, draft),
        "repo_check": _check_repo(draft, record) if check_repo else "not_checked",
    }
