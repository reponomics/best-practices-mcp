"""Offline access to the generated, revisioned BadgeApp criteria catalog."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

from best_practices_mcp.errors import DomainError


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    resource = files("best_practices_mcp").joinpath("data/catalog.json")
    catalog = json.loads(resource.read_text(encoding="utf-8"))
    if catalog["format_version"] != 2:
        raise ValueError("Unsupported packaged catalog format")
    source = provenance()
    base_url = f"{source['repository']}/blob/{source['revision']}"
    catalog["catalog"] = {
        "revision": source["revision"],
        "source_url": f"{base_url}/criteria/criteria.yml",
        "generated_at": source["generated_at"],
        "format_version": 1,
    }
    catalog["text_source_url"] = f"{base_url}/config/locales/en.yml"
    return catalog


def provenance() -> dict[str, Any]:
    """Return source hashes, generator identity, and upstream criterion metadata."""
    resource = files("best_practices_mcp").joinpath("data/provenance.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def field_aliases() -> dict[str, str]:
    """Return only source-identified display fields, never guessed spellings."""
    aliases = {}
    for criterion in _catalog()["criteria"]:
        for alias in criterion["aliases"]:
            for suffix in ("status", "justification"):
                aliases[f"{alias}_{suffix}"] = criterion[f"{suffix}_field"]
    return aliases


def catalog_levels() -> list[str]:
    """Return the supported levels in upstream order."""
    return list(_catalog()["levels"])


def catalog_reference() -> dict[str, Any]:
    """Identify the pinned upstream revision behind every definition."""
    return dict(_catalog()["catalog"])


def _level_definitions(level: str) -> dict[str, dict]:
    catalog = _catalog()
    if level not in catalog["levels"]:
        raise DomainError("invalid_level", "Choose one of the supported badge levels.")
    return {c["criterion_id"]: c for c in catalog["criteria"] if c["level"] == level}


def _selected(definitions: dict[str, dict], level: str, criterion_ids: list[str]) -> list[dict]:
    if any(type(value) is not str for value in criterion_ids):
        raise DomainError("invalid_criterion", "Criterion identifiers must be strings.")
    if len(criterion_ids) != len(set(criterion_ids)):
        raise DomainError("invalid_criterion", "Criterion identifiers must be distinct.")
    unknown = set(criterion_ids) - definitions.keys()
    if unknown:
        raise DomainError(
            "invalid_criterion",
            "The selected level does not define the requested criterion identifiers.",
            details={"level": level, "criterion_ids": sorted(unknown)},
            recovery="Call get_criteria with this level to list its criterion identifiers.",
        )
    return [definitions[key] for key in sorted(criterion_ids)]


def _in_category(definitions: dict[str, dict], level: str, category: str) -> list[dict]:
    categories = _categories(definitions)
    if category not in categories:
        raise DomainError(
            "invalid_category",
            "The selected level has no such category.",
            details={"level": level, "allowed": categories},
            recovery="Use one of the allowed category names exactly as written.",
        )
    return [
        definitions[key] for key in sorted(definitions) if definitions[key]["category"] == category
    ]


def _categories(definitions: dict[str, dict]) -> list[str]:
    return sorted({definition["category"] for definition in definitions.values()})


def criterion_definitions(
    level: str | None,
    criterion_ids: list[str] | None = None,
    category: str | None = None,
) -> list[dict]:
    """Return complete definitions for one level, optionally narrowed; none without a level."""
    if level is None:
        if criterion_ids is not None or category is not None:
            raise DomainError("invalid_level", "A criterion filter requires a level.")
        return []
    definitions = _level_definitions(level)
    if criterion_ids is not None and category is not None:
        raise DomainError(
            "invalid_category", "A category cannot be combined with criterion identifiers."
        )
    if criterion_ids is not None:
        selected = _selected(definitions, level, criterion_ids)
    elif category is not None:
        selected = _in_category(definitions, level, category)
    else:
        selected = [definitions[key] for key in sorted(definitions)]
    return copy.deepcopy(selected)


def level_summary(level: str) -> dict:
    """Count one level's criteria and name its categories."""
    definitions = _level_definitions(level)
    return {
        "level": level,
        "criterion_count": len(definitions),
        "categories": _categories(definitions),
    }


INDEX_FIELDS = ("criterion_id", "category", "requirement")


def get_criteria(
    level: str | None = None,
    criterion_ids: list[str] | None = None,
    category: str | None = None,
    detail: str | None = None,
) -> dict:
    """Build the get_criteria result: a level index, a criterion index, or full definitions."""
    criteria = criterion_definitions(level, criterion_ids, category)
    if level is None:
        if detail is not None:
            raise DomainError("invalid_level", "A detail choice requires a level.")
        levels = [level_summary(name) for name in catalog_levels()]
    else:
        levels = [level_summary(level)]
        detail = detail or ("full" if criterion_ids is not None else "index")
        if detail == "index":
            criteria = [{field: row[field] for field in INDEX_FIELDS} for row in criteria]
    return {
        "schema_version": 2,
        "level": level,
        "detail": detail,
        "levels": levels,
        "criteria": criteria,
        "catalog": {**catalog_reference(), "text_source_url": _catalog()["text_source_url"]},
    }
