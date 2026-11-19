"""Generate the offline criteria catalog from verified, vendored BadgeApp inputs.

Generation never fetches network data. Update the source snapshot and its manifest
explicitly when reviewing a new upstream revision; --check compares exact bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Hashable
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("passing", "silver", "gold", "baseline-1", "baseline-2", "baseline-3")
SOURCE_LEVELS = dict(zip(("0", "1", "2", *LEVELS[3:]), LEVELS, strict=True))
RANKS = {"0": 0, "1": 1, "2": 2, "baseline-1": 1, "baseline-2": 2, "baseline-3": 3}
FLAGS = (
    "na_allowed",
    "na_justification_required",
    "met_justification_required",
    "met_url_required",
)
# Upstream's lifecycle flags: a retired criterion, or one not yet in effect. Neither is
# part of a badge application, so neither enters the catalog.
EXCLUDING_FLAGS = ("obsolete", "future")
INPUTS = ("criteria/criteria.yml", "criteria/baseline_criteria.yml", "config/locales/en.yml")
# Baseline YAML files every control under one group; upstream documents the category
# of a control as the two-letter code in its identifier.
CATEGORY_GUIDE = "docs/automation-proposals.md"
CATEGORY_HEADING = "**OSPS category codes:**"
CATEGORY_ROW = re.compile(r"^\| `([a-z]{2})` \| (.+?) \|$", re.MULTILINE)
BASELINE_ID = re.compile(r"osps_([a-z]{2})_[0-9]{2}_[0-9]{2}")


class SourceLoader(yaml.SafeLoader):
    """Safe loader supporting upstream's ordered maps without losing keys."""


def ordered_mapping(loader: SourceLoader, node: yaml.SequenceNode) -> dict[Hashable, Any]:
    result: dict[Hashable, Any] = {}
    for child in node.value:
        item = loader.construct_mapping(child, deep=True)
        if len(item) != 1 or result.keys() & item.keys():
            raise ValueError("Invalid or duplicate ordered-map key")
        result.update(item)
    return result


SourceLoader.add_constructor("tag:yaml.org,2002:omap", ordered_mapping)


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def read_sources(source_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = json.loads((source_dir / "source.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        actual = hashlib.sha256((source_dir / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Source hash mismatch: {name}")
    metal, baseline, english = [
        yaml.load((source_dir / name).read_text(encoding="utf-8"), Loader=SourceLoader)
        for name in INPUTS
    ]
    merged = {**metal, **{key: value for key, value in baseline.items() if key != "_metadata"}}
    return manifest, merged, english["en"]["criteria"]


def baseline_categories(source_dir: Path) -> dict[str, str]:
    """Read the documented category name for each OSPS identifier code."""
    guide = (source_dir / CATEGORY_GUIDE).read_text(encoding="utf-8")
    table = guide.partition(CATEGORY_HEADING)[2].strip().split("\n\n")[0]
    categories = dict(CATEGORY_ROW.findall(table))
    if not categories:
        raise ValueError(f"Missing OSPS category codes: {CATEGORY_GUIDE}")
    return categories


def category(level: str, criterion_id: str, raw: dict[str, Any], baseline: dict[str, str]) -> str:
    if not level.startswith("baseline-"):
        major: str = raw["major"]
        return major
    match = BASELINE_ID.fullmatch(criterion_id)
    if match is None or match[1] not in baseline:
        raise ValueError(f"No documented category code: {level}/{criterion_id}")
    return baseline[match[1]]


def flatten(groups: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for major, minors in groups.items():
        for minor, criteria in minors.items():
            for criterion_id, raw in criteria.items():
                if criterion_id in result:
                    raise ValueError(f"Duplicate criterion: {criterion_id}")
                result[criterion_id] = {**raw, "major": major, "minor": minor}
    return result


def inherited_details(
    level: str, criterion_id: str, definitions: dict[str, Any], english: dict[str, Any]
) -> tuple[str | None, str | None]:
    # Mirrors Criteria#get_text_if_exists: reverse defined-level order, with rank bound.
    for candidate in reversed(definitions):
        if RANKS[candidate] > RANKS[level] or criterion_id not in definitions[candidate]:
            continue
        text = english.get(candidate, {}).get(criterion_id, {})
        if "details" in text:
            return text["details"], candidate
    return None, None


def exclusion(raw: dict[str, Any]) -> str | None:
    """Name the upstream lifecycle flag that keeps a criterion out of the catalog."""
    for flag in EXCLUDING_FLAGS:
        value = raw.get(flag, False)
        if type(value) is not bool:
            raise ValueError(f"Non-boolean criterion flag: {flag}")
        if value:
            return flag
    return None


def boolean_flags(raw: dict[str, Any]) -> dict[str, bool]:
    """Expand upstream's omitted entailed flags into explicit requirements."""
    result = {}
    for flag in FLAGS:
        value = raw.get(flag, False)
        if type(value) is not bool:
            raise ValueError(f"Non-boolean criterion flag: {flag}")
        result[flag] = value
    result["met_justification_required"] |= result["met_url_required"]
    result["na_allowed"] |= result["na_justification_required"]
    return result


def criterion_record(
    level: str,
    criterion_id: str,
    raw: dict[str, Any],
    definitions: dict[str, Any],
    english: dict[str, Any],
    baseline: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    text = english[level][criterion_id]
    details, inherited_level = inherited_details(level, criterion_id, definitions, english)
    description = text["description"]
    if not isinstance(description, str) or not description:
        raise ValueError(f"Missing official description: {level}/{criterion_id}")
    alias = raw.get("original_id")
    aliases = [alias] if alias else []
    record = {
        "criterion_id": criterion_id,
        "level": SOURCE_LEVELS[level],
        "description": description,
        "details": details,
        "category": category(level, criterion_id, raw, baseline),
        "requirement": raw["category"],
        "status_field": f"{criterion_id}_status",
        "justification_field": f"{criterion_id}_justification",
        "aliases": aliases,
        **boolean_flags(raw),
    }
    metadata = {
        "major": raw["major"],
        "minor": raw["minor"],
        "future": raw.get("future", False),
        "obsolete": raw.get("obsolete", False),
        "description_key": f"en.criteria.{level}.{criterion_id}.description",
        "details_key": None
        if inherited_level is None
        else f"en.criteria.{inherited_level}.{criterion_id}.details",
    }
    return record, metadata


def catalog_content(source_dir: Path) -> dict[str, bytes]:
    manifest, groups, english = read_sources(source_dir)
    if set(groups) != set(SOURCE_LEVELS):
        raise ValueError("Source levels differ from the six supported levels")
    definitions = {level: flatten(group) for level, group in groups.items()}
    baseline = baseline_categories(source_dir)
    criteria = []
    metadata = {}
    excluded = {}
    # The catalog keeps the order of the criteria files, which is the order of the edit form.
    for level, definitions_at_level in definitions.items():
        for criterion_id, raw in definitions_at_level.items():
            if reason := exclusion(raw):
                excluded[f"{SOURCE_LEVELS[level]}/{criterion_id}"] = reason
                continue
            record, criterion_metadata = criterion_record(
                level, criterion_id, raw, definitions, english, baseline
            )
            criteria.append(record)
            metadata[f"{SOURCE_LEVELS[level]}/{criterion_id}"] = criterion_metadata
    provenance = {
        **manifest,
        "generator": {
            "path": "scripts/generate_catalog.py",
            "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "format_version": 2,
        },
        "criteria_metadata": metadata,
        "excluded_criteria": excluded,
        "counts": {level: sum(c["level"] == level for c in criteria) for level in LEVELS},
        "license_file": "BADGEAPP-LICENSE.txt",
        "text_policy": "English locale descriptions; upstream rank-bounded details inheritance",
        "category_policy": (
            "Criteria major group, except Baseline levels, which use the OSPS category code "
            f"table in {CATEGORY_GUIDE}; criteria_metadata keeps each upstream major group."
        ),
        "flag_policy": (
            "Explicit requirements include upstream entailments: met_url_required implies "
            "met_justification_required; na_justification_required implies na_allowed."
        ),
        "lifecycle_policy": (
            "Criteria that upstream marks obsolete or future are left out of the catalog and "
            "named in excluded_criteria."
        ),
        "generated_at_policy": "Source-manifest generation timestamp preserved on regeneration",
    }
    return {
        "catalog.json": encoded({"format_version": 2, "levels": LEVELS, "criteria": criteria}),
        "provenance.json": encoded(provenance),
        "BADGEAPP-LICENSE.txt": (source_dir / "LICENSE").read_bytes(),
    }


def write_or_check(content: dict[str, bytes], output_dir: Path, check: bool) -> bool:
    if not check:
        output_dir.mkdir(parents=True, exist_ok=True)
    mismatched = []
    for name, value in content.items():
        target = output_dir / name
        if check:
            if not target.exists() or target.read_bytes() != value:
                mismatched.append(name)
        else:
            target.write_bytes(value)
    if mismatched:
        print("Catalog differs: " + ", ".join(mismatched))
        return False
    print("Catalog verified" if check else "Catalog generated")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "vendor/badgeapp")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "src/best_practices_mcp/data")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return 0 if write_or_check(catalog_content(args.source_dir), args.output_dir, args.check) else 1


if __name__ == "__main__":
    raise SystemExit(main())
