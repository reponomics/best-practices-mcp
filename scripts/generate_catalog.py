"""Generate the offline criteria catalog from verified, vendored BadgeApp inputs.

Generation never fetches network data. Update the source snapshot and its manifest
explicitly when reviewing a new upstream revision; --check compares exact bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

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
INPUTS = ("criteria/criteria.yml", "criteria/baseline_criteria.yml", "config/locales/en.yml")


class SourceLoader(yaml.SafeLoader):
    """Safe loader supporting upstream's ordered maps without losing keys."""


def ordered_mapping(loader: SourceLoader, node: yaml.SequenceNode) -> dict:
    result = {}
    for child in node.value:
        item = loader.construct_mapping(child, deep=True)
        if len(item) != 1 or result.keys() & item.keys():
            raise ValueError("Invalid or duplicate ordered-map key")
        result.update(item)
    return result


SourceLoader.add_constructor("tag:yaml.org,2002:omap", ordered_mapping)


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def read_sources(source_dir: Path) -> tuple[dict, dict, dict]:
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


def flatten(groups: dict) -> dict[str, dict]:
    result = {}
    for major, minors in groups.items():
        for minor, criteria in minors.items():
            for criterion_id, raw in criteria.items():
                if criterion_id in result:
                    raise ValueError(f"Duplicate criterion: {criterion_id}")
                result[criterion_id] = {**raw, "major": major, "minor": minor}
    return result


def inherited_details(level: str, criterion_id: str, definitions: dict, english: dict) -> tuple:
    # Mirrors Criteria#get_text_if_exists: reverse defined-level order, with rank bound.
    for candidate in reversed(definitions):
        if RANKS[candidate] > RANKS[level] or criterion_id not in definitions[candidate]:
            continue
        text = english.get(candidate, {}).get(criterion_id, {})
        if "details" in text:
            return text["details"], candidate
    return None, None


def boolean_flags(raw: dict) -> dict[str, bool]:
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
    level: str, criterion_id: str, raw: dict, definitions: dict, english: dict
) -> tuple[dict, dict]:
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
        "category": raw["major"],
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
    criteria = []
    metadata = {}
    for level, definitions_at_level in definitions.items():
        for criterion_id, raw in sorted(definitions_at_level.items()):
            record, criterion_metadata = criterion_record(
                level, criterion_id, raw, definitions, english
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
        "counts": {level: sum(c["level"] == level for c in criteria) for level in LEVELS},
        "license_file": "BADGEAPP-LICENSE.txt",
        "text_policy": "English locale descriptions; upstream rank-bounded details inheritance",
        "flag_policy": (
            "Explicit requirements include upstream entailments: met_url_required implies "
            "met_justification_required; na_justification_required implies na_allowed."
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
