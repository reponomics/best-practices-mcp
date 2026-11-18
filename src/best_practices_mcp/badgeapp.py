"""Public BadgeApp lookup/progress mapping; no drafts or website mutations."""

from __future__ import annotations

import copy
import json
import math
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from best_practices_mcp.criteria import (
    catalog_reference,
    criterion_definitions,
    field_aliases,
    level_summary,
)
from best_practices_mcp.documents import validate_document
from best_practices_mcp.drafts import VALID_STATUSES
from best_practices_mcp.errors import DomainError
from best_practices_mcp.models import LEVELS

if TYPE_CHECKING:
    from best_practices_mcp.http import BadgeAppHTTP

ORIGIN = "https://www.bestpractices.dev"
PROJECTS_PATH = "/projects.json"
ASCII_WHITESPACE = " \t\r\n\v\f"
PERCENTAGES = dict(
    zip(
        LEVELS,
        (
            "badge_percentage_0",
            "badge_percentage_1",
            "badge_percentage_2",
            "badge_percentage_baseline_1",
            "badge_percentage_baseline_2",
            "badge_percentage_baseline_3",
        ),
        strict=True,
    )
)


def _upstream(message: str, field: str | None = None) -> DomainError:
    return DomainError(
        "upstream_invalid_response",
        message,
        details={} if field is None else {"field": field},
        recovery="Retry the public read later; report a persistent upstream format change.",
    )


def _positive_integer(value: Any, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise DomainError("invalid_field", f"{field} must be a positive integer.")
    return value


def _comparable_url(value: Any) -> str | None:
    if not isinstance(value, str) or any(ord(char) <= 32 for char in value):
        return None
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    scheme = parts.scheme.lower()
    host = parts.hostname.lower()
    host = f"[{host}]" if ":" in host else host
    if port is not None and port != {"http": 80, "https": 443}[scheme]:
        host = f"{host}:{port}"
    return urlunsplit((scheme, host, parts.path, parts.query, parts.fragment))


def _classify_query(query: str, page: int) -> tuple[str, str]:
    _positive_integer(page, "page")
    if type(query) is not str or not (query := query.strip(ASCII_WHITESPACE)):
        raise DomainError("invalid_query", "Supply a nonempty project ID, URL, or search text.")
    try:
        query.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise DomainError("invalid_query", "Query text must contain valid Unicode.") from exc
    try:
        numeric = bool(re.fullmatch(r"[0-9]+", query)) and int(query) > 0
    except ValueError as exc:
        raise DomainError("invalid_query", "The numeric identifier is too large.") from exc
    if numeric:
        if page != 1:
            raise DomainError("invalid_query", "Numeric project lookup accepts only page 1.")
        return str(int(query)), "id"
    if re.match(r"https?:", query, flags=re.IGNORECASE):
        if _comparable_url(query) is None:
            raise DomainError("invalid_query", "Use an absolute HTTP(S) URL without credentials.")
        return query, "url"
    return query, "text"


def _record(value: Any, expected_id: int | None = None) -> dict:
    if type(value) is not dict:
        raise _upstream("A project response must contain a JSON object.")
    project_id = value.get("id")
    if type(project_id) is not int or project_id <= 0:
        raise _upstream("The public project identifier is missing or invalid.", "id")
    if expected_id is not None and project_id != expected_id:
        raise DomainError(
            "project_mismatch",
            "The public record does not match the requested project.",
            details={"project_id": expected_id, "observed_project_id": project_id},
            recovery="Verify the project ID and retry the public read.",
        )
    return value


def _optional_text(record: dict, field: str) -> str | None:
    value = record.get(field)
    if value is not None and type(value) is not str:
        raise _upstream("A public project text field has an unexpected type.", field)
    return value


def _project(record: dict) -> dict:
    return {
        "project_id": record["id"],
        **{field: _optional_text(record, field) for field in ("name", "repo_url", "homepage_url")},
    }


def _match_basis(record: dict, query: str, kind: str) -> str:
    if kind != "url":
        return kind
    wanted = _comparable_url(query)
    for field in ("repo_url", "homepage_url"):
        if _comparable_url(record.get(field)) == wanted:
            return field
    # Upstream deliberately normalizes some spellings more broadly than identity checks.
    return "url_query"


def _next_link(header: str) -> list[str]:
    links = []
    for url, parameters in re.findall(r"<([^>]*)>([^<]*)", header):
        relation = re.search(r';\s*rel\s*=\s*(?:"([^"]*)"|([^\s;,]+))', parameters, re.I)
        if relation and "next" in (relation.group(1) or relation.group(2)).split():
            links.append(url)
    return links


def _next_page(url: str, source_url: str, params: dict) -> int | None:
    try:
        resolved = urljoin(source_url, url)
        parts = urlsplit(resolved)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    if origin != ORIGIN or parts.path != PROJECTS_PATH or parts.fragment:
        return None
    expected = {key: [str(value)] for key, value in params.items() if key != "page"}
    if {key: value for key, value in query.items() if key != "page"} != expected:
        return None
    pages = query.get("page", [])
    if len(pages) != 1 or not re.fullmatch(r"[0-9]+", pages[0]):
        return None
    try:
        page = int(pages[0])
    except ValueError:
        return None
    return page if page > params["page"] else None


def _pagination(result: Any, params: dict, empty: bool) -> tuple[int | None, bool]:
    if empty:
        return None, True
    header = next((v for k, v in result.headers.items() if k.lower() == "link"), "")
    links = _next_link(header)
    if len(links) != 1:
        return None, False
    return _next_page(links[0], result.source_url, params), False


def _normalized_record(record: dict) -> dict:
    aliases = field_aliases()
    normalized = {}
    for field, value in record.items():
        canonical = aliases.get(field, field)
        if canonical in normalized:
            before = json.dumps(normalized[canonical], sort_keys=True, allow_nan=False)
            after = json.dumps(value, sort_keys=True, allow_nan=False)
            if before != after:
                raise _upstream("Conflicting canonical and alias values in public data.", canonical)
        normalized[canonical] = value
    return normalized


def _matches(record: dict, definition: dict, statuses: list[str] | None) -> bool:
    """Apply a status filter; values outside the known set match only without one."""
    if statuses is None:
        return True
    status = record.get(definition["status_field"])
    return type(status) is str and status in VALID_STATUSES.intersection(statuses)


def _saved_answers(
    record: dict, definitions: list[dict], statuses: list[str] | None, justifications: bool
) -> tuple[dict, list[str]]:
    """Copy the supplied fields of matching criteria; missing fields stay missing.

    BadgeApp stores a status for every criterion, "?" until one is chosen, so a status
    missing from the record was not retrieved. It is reported, never read as an answer.
    """
    kinds = ("status", "justification") if justifications else ("status",)
    answers, not_retrieved = {}, []
    for definition in definitions:
        if definition["status_field"] not in record:
            not_retrieved.append(definition["criterion_id"])
        if not _matches(record, definition, statuses):
            continue
        for kind in kinds:
            field = definition[f"{kind}_field"]
            if field in record:
                answers[field] = copy.deepcopy(record[field])
    _check_answer_bounds(answers)
    return answers, not_retrieved


def _check_answer_bounds(answers: dict) -> None:
    try:
        validate_document(answers)
    except DomainError as exc:
        if exc.code == "document_too_large":
            raise DomainError(
                "response_too_large",
                "Selected public answers exceed the document response budget.",
                recovery="Request fewer criterion IDs, or set include_justifications to false.",
            ) from exc
        raise _upstream("Public answers contain unsupported JSON values or nesting.") from exc


def _percentage(record: dict, field: str) -> float | int | None:
    value = record.get(field)
    invalid_number = type(value) is float and not math.isfinite(value)
    if value is not None and (type(value) not in (int, float) or invalid_number):
        raise _upstream("A public progress percentage has an unexpected value.", field)
    return value


def _level_statuses(record: dict) -> list[dict]:
    """Copy each level's reported percentage and achievement times; compute nothing."""
    statuses = []
    for level, field in PERCENTAGES.items():
        stem = level.replace("-", "_")
        statuses.append(
            {
                "level": level,
                "percentage": _percentage(record, field),
                "achieved_at": _optional_text(record, f"achieved_{stem}_at"),
                "lost_at": _optional_text(record, f"lost_{stem}_at"),
            }
        )
    return statuses


def _observation(result: Any, record: dict) -> dict:
    return {
        "project_id": record["id"],
        "source_url": result.source_url,
        "fetched_at": result.fetched_at,
        "attribution": _optional_text(record, "project_entry_attribution"),
        "license": _optional_text(record, "project_entry_license"),
    }


class BadgeAppClient:
    """Translate public records into contract payloads using one shared HTTP adapter."""

    def __init__(self, http: BadgeAppHTTP) -> None:
        self.http = http

    async def find_project(self, query: str, page: int = 1) -> dict:
        query, kind = _classify_query(query, page)
        if kind == "id":
            return await self._find_id(query)
        params = {"url" if kind == "url" else "q": query, "page": page}
        result = await self.http.get_json(PROJECTS_PATH, params)
        if type(result.data) is not list:
            raise _upstream("Project search must return a JSON array.")
        records = [_record(value) for value in result.data]
        next_page, complete = _pagination(result, params, not records)
        return self._search_result(query, kind, page, records, result, next_page, complete)

    async def _find_id(self, query: str) -> dict:
        path = f"/projects/{query}.json"
        try:
            result = await self.http.get_json(path)
        except DomainError as exc:
            if exc.code != "project_not_found":
                raise
            return {
                "schema_version": 1,
                "query": query,
                "query_kind": "id",
                "page": 1,
                "candidates": [],
                "next_page": None,
                "pagination_complete": True,
                "observation": {
                    "source_url": exc.details.get("source_url", ORIGIN + path),
                    "fetched_at": exc.details.get("fetched_at", datetime.now(UTC).isoformat()),
                },
            }
        record = _record(result.data, int(query))
        return self._search_result(query, "id", 1, [record], result, None, True)

    @staticmethod
    def _search_result(query, kind, page, records, result, next_page, complete) -> dict:
        return {
            "schema_version": 1,
            "query": query,
            "query_kind": kind,
            "page": page,
            "candidates": [
                {"project": _project(record), "match_basis": _match_basis(record, query, kind)}
                for record in records
            ],
            "next_page": next_page,
            "pagination_complete": complete,
            "observation": {"source_url": result.source_url, "fetched_at": result.fetched_at},
        }

    async def get_project_snapshot(self, project_id: int) -> tuple[dict, dict]:
        """Read public project identity and observation metadata for artifact preparation."""
        _positive_integer(project_id, "project_id")
        result = await self.http.get_json(f"/projects/{project_id}.json")
        record = _record(result.data, project_id)
        observation = _observation(result, record)
        return record, observation

    async def get_project_status(self, project_id: int) -> dict:
        """Report the badge level and per-level progress that BadgeApp records."""
        _positive_integer(project_id, "project_id")
        result = await self.http.get_json(f"/projects/{project_id}.json")
        record = _record(result.data, project_id)
        return {
            "schema_version": 1,
            "project": _project(record),
            "badge_level": _optional_text(record, "badge_level"),
            "levels": _level_statuses(record),
            "updated_at": _optional_text(record, "updated_at"),
            "observation": _observation(result, record),
        }

    async def get_project_answers(
        self,
        project_id: int,
        level: str,
        criterion_ids: list[str] | None = None,
        statuses: list[str] | None = None,
        include_justifications: bool = True,
    ) -> dict:
        """Return the answers saved for one level, optionally narrowed."""
        _positive_integer(project_id, "project_id")
        if level is None:
            raise DomainError("invalid_level", "Saved answers are read one badge level at a time.")
        definitions = criterion_definitions(level, criterion_ids)
        result = await self.http.get_json(f"/projects/{project_id}.json")
        record = _normalized_record(_record(result.data, project_id))
        answers, not_retrieved = _saved_answers(
            record, definitions, statuses, include_justifications
        )
        return {
            "schema_version": 1,
            "project": _project(record),
            "level": level,
            "answers": answers,
            "statuses_not_retrieved": not_retrieved,
            "level_criterion_count": level_summary(level)["criterion_count"],
            "observation": _observation(result, record),
            "catalog": catalog_reference(),
        }
