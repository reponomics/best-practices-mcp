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
    for criterion in catalog["criteria"]:
        criterion["source_url"] = f"{base_url}/config/locales/en.yml"
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


def _selected_criteria(level: str, criterion_ids: list[str] | None) -> list[dict]:
    definitions = {c["criterion_id"]: c for c in _catalog()["criteria"] if c["level"] == level}
    if criterion_ids is None:
        return [definitions[key] for key in sorted(definitions)]
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
            recovery="Choose canonical criterion identifiers from this level's catalog.",
        )
    return [definitions[key] for key in sorted(criterion_ids)]


def get_criteria(level: str | None = None, criterion_ids: list[str] | None = None) -> dict:
    """Return a level index or definitions; this is a domain accessor, not an MCP tool."""
    catalog = _catalog()
    if level is None and criterion_ids is not None:
        raise DomainError("invalid_level", "A criterion filter requires a level.")
    if level is not None and level not in catalog["levels"]:
        raise DomainError("invalid_level", "Choose one of the supported badge levels.")
    criteria = [] if level is None else _selected_criteria(level, criterion_ids)
    return copy.deepcopy(
        {
            "schema_version": 1,
            "level": level,
            "levels": catalog["levels"],
            "criteria": criteria,
            "catalog": catalog["catalog"],
        }
    )
