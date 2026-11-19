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
    catalog: dict[str, Any] = json.loads(resource.read_text(encoding="utf-8"))
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
    data: dict[str, Any] = json.loads(resource.read_text(encoding="utf-8"))
    return data


_SEPARATORS = str.maketrans("-.", "__")


def _name_key(name: str) -> str:
    """Reduce a criterion name as BadgeApp does: lower case, with - and . changed to _."""
    return name.casefold().translate(_SEPARATORS)


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


def _level_definitions(level: str) -> dict[str, dict[str, Any]]:
    """Map a level's criterion identifiers to definitions, in the order of the edit form.

    The catalog lists criteria as the upstream criteria files do, and every selection
    below keeps that order.
    """
    catalog = _catalog()
    if level not in catalog["levels"]:
        raise DomainError("invalid_level", "Choose one of the supported badge levels.")
    return {c["criterion_id"]: c for c in catalog["criteria"] if c["level"] == level}


def _resolved(definitions: dict[str, dict[str, Any]], names: list[str]) -> list[str | None]:
    """Map each name to a criterion identifier of the level, or to None.

    A name is an identifier or one of the criterion's source-identified aliases, such as the
    display form OSPS-AC-01.01. Letter case is ignored, and a hyphen or a period counts as an
    underscore. Results always carry the identifier.
    """
    known = {
        _name_key(name): identifier
        for identifier, definition in definitions.items()
        for name in (identifier, *definition["aliases"])
    }
    return [name if name in definitions else known.get(_name_key(name)) for name in names]


def _other_levels(names: list[str]) -> dict[str, list[str]]:
    """For each name that some level defines, list those levels in catalog order."""
    found: dict[str, list[str]] = {}
    for level in catalog_levels():
        resolved = _resolved(_level_definitions(level), names)
        for name, identifier in zip(names, resolved):
            if identifier is not None:
                found.setdefault(name, []).append(level)
    return found


def _selected(
    definitions: dict[str, dict[str, Any]], level: str, criterion_ids: list[str]
) -> list[dict[str, Any]]:
    if any(type(value) is not str for value in criterion_ids):
        raise DomainError("invalid_criterion", "Criterion identifiers must be strings.")
    resolved = _resolved(definitions, criterion_ids)
    unknown = {name for name, identifier in zip(criterion_ids, resolved) if identifier is None}
    if unknown:
        elsewhere = _other_levels(sorted(unknown))
        raise DomainError(
            "invalid_criterion",
            "The selected level does not define the requested criterion identifiers.",
            details={"level": level, "criterion_ids": sorted(unknown), "other_levels": elsewhere},
            recovery=(
                "Use a level that details.other_levels gives for the identifier."
                if elsewhere
                else "Call get_criteria with this level to list its criterion identifiers."
            ),
        )
    identifiers = [identifier for identifier in resolved if identifier is not None]
    chosen = set(identifiers)
    if len(identifiers) != len(chosen):
        raise DomainError("invalid_criterion", "Criterion identifiers must be distinct.")
    return [definition for key, definition in definitions.items() if key in chosen]


def _in_category(
    definitions: dict[str, dict[str, Any]], level: str, category: str
) -> list[dict[str, Any]]:
    categories = _categories(definitions)
    if category not in categories:
        raise DomainError(
            "invalid_category",
            "The selected level has no such category.",
            details={"level": level, "allowed": categories},
            recovery="Use one of the allowed category names exactly as written.",
        )
    return [definition for definition in definitions.values() if definition["category"] == category]


def _categories(definitions: dict[str, dict[str, Any]]) -> list[str]:
    """Name the level's categories once each, in the order the edit form presents them."""
    return list(dict.fromkeys(definition["category"] for definition in definitions.values()))


def criterion_definitions(
    level: str | None,
    criterion_ids: list[str] | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
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
        selected = list(definitions.values())
    return copy.deepcopy(selected)


def level_summary(level: str) -> dict[str, Any]:
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
) -> dict[str, Any]:
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
