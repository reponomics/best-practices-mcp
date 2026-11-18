"""Check packaged criteria against pinned source-derived independent expectations."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import pytest
import yaml

from best_practices_mcp import criteria as criteria_module
from best_practices_mcp.contracts import validate_output
from best_practices_mcp.criteria import (
    catalog_levels,
    catalog_reference,
    criterion_definitions,
    field_aliases,
    get_criteria,
    provenance,
)
from best_practices_mcp.errors import DomainError

ROOT = Path(__file__).resolve().parents[1]
COUNTS = {
    "passing": 67,
    "silver": 55,
    "gold": 23,
    "baseline-1": 24,
    "baseline-2": 19,
    "baseline-3": 21,
}
# Transcribed from "OSPS category codes" in vendor/badgeapp/docs/automation-proposals.md,
# independently of the generator's reading of that table.
BASELINE_CATEGORIES = {
    "ac": "Access Control",
    "br": "Build and Release",
    "do": "Documentation",
    "gv": "Governance",
    "le": "Legal",
    "qa": "Quality",
    "sa": "Security Assessment",
    "vm": "Vulnerability Management",
}


@pytest.fixture(scope="module")
def source_manifest():
    return json.loads((ROOT / "vendor/badgeapp/source.json").read_text(encoding="utf-8"))


def _mapping_items(value):
    """PyYAML's standard safe loader returns !!omap as pairs, plain maps as dicts."""
    return value.items() if isinstance(value, dict) else value


def _flatten_criteria(groups):
    records = {}
    for category, subgroups in _mapping_items(groups):
        for _, criteria in _mapping_items(subgroups):
            for criterion_id, raw in _mapping_items(criteria):
                records[criterion_id] = (category, raw)
    return records


@pytest.fixture(scope="module")
def yaml_criteria():
    """Read the checked-in YAML independently of catalog generation."""
    definitions = {}
    for name in ("criteria.yml", "baseline_criteria.yml"):
        source = yaml.safe_load(
            (ROOT / "vendor/badgeapp/criteria" / name).read_text(encoding="utf-8")
        )
        for level, groups in _mapping_items(source):
            if level == "_metadata":
                continue
            definitions[level] = _flatten_criteria(groups)
    locale = yaml.safe_load(
        (ROOT / "vendor/badgeapp/config/locales/en.yml").read_text(encoding="utf-8")
    )
    return definitions, locale["en"]["criteria"]


@pytest.mark.parametrize(
    "level,source_levels",
    [
        ("passing", ("0",)),
        ("silver", ("1", "0")),
        ("gold", ("2", "1", "0")),
        ("baseline-1", ("baseline-1",)),
        ("baseline-2", ("baseline-2", "baseline-1")),
        ("baseline-3", ("baseline-3", "baseline-2", "baseline-1")),
    ],
)
def test_all_catalog_records_match_yaml_and_english_locale(
    yaml_criteria, source_manifest, level, source_levels
):
    # The agreed catalog contract uses locale wording, level-bounded inherited
    # details, original_id aliases, and YAML flags with their documented entailments.
    definitions, locale = yaml_criteria
    source_level = source_levels[0]
    expected = definitions[source_level]
    source_url = (
        f"{source_manifest['repository']}/blob/{source_manifest['revision']}/config/locales/en.yml"
    )
    result = get_criteria(level, detail="full")
    validate_output("get_criteria", result)
    assert result["catalog"]["text_source_url"] == source_url
    assert result["criteria"] == criterion_definitions(level)
    assert len(result["criteria"]) == COUNTS[level]
    assert {row["criterion_id"] for row in result["criteria"]} == set(expected)
    for row in result["criteria"]:
        criterion_id = row["criterion_id"]
        category, raw = expected[criterion_id]
        if level.startswith("baseline-"):
            assert category == "General"
            category = BASELINE_CATEGORIES[criterion_id.split("_")[1]]
        details = next(
            (
                locale[parent][criterion_id]["details"]
                for parent in source_levels
                if criterion_id in definitions[parent]
                and "details" in locale[parent].get(criterion_id, {})
            ),
            None,
        )
        assert row == {
            "criterion_id": criterion_id,
            "level": level,
            "description": locale[source_level][criterion_id]["description"],
            "details": details,
            "category": category,
            "requirement": raw["category"],
            "status_field": f"{criterion_id}_status",
            "justification_field": f"{criterion_id}_justification",
            "aliases": [raw["original_id"]] if raw.get("original_id") else [],
            "na_allowed": raw.get("na_allowed", False)
            or raw.get("na_justification_required", False),
            "na_justification_required": raw.get("na_justification_required", False),
            "met_justification_required": raw.get("met_justification_required", False)
            or raw.get("met_url_required", False),
            "met_url_required": raw.get("met_url_required", False),
        }


def test_level_specific_flags_wording_and_inherited_details() -> None:
    silver = get_criteria("silver", ["hardening"])["criteria"][0]
    gold = get_criteria("gold", ["hardening"])["criteria"][0]
    assert silver["met_justification_required"] is True
    assert silver["met_url_required"] is False
    assert gold["met_justification_required"] is True
    assert gold["met_url_required"] is True
    assert silver["description"] != gold["description"]
    assert silver["details"] == gold["details"]
    assert provenance()["criteria_metadata"]["gold/hardening"]["details_key"] == (
        "en.criteria.1.hardening.details"
    )


def test_populated_catalog_flags_include_entailed_requirements() -> None:
    for level in COUNTS:
        for row in criterion_definitions(level):
            assert not row["met_url_required"] or row["met_justification_required"]
            assert not row["na_justification_required"] or row["na_allowed"]
    example = get_criteria("gold", ["build_reproducible"])["criteria"][0]
    assert all(
        example[flag]
        for flag in (
            "na_allowed",
            "na_justification_required",
            "met_justification_required",
            "met_url_required",
        )
    )


@pytest.fixture(scope="module")
def catalog_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_catalog", ROOT / "scripts/generate_catalog.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_reads_documented_baseline_category_codes(tmp_path, catalog_generator):
    assert catalog_generator.baseline_categories(ROOT / "vendor/badgeapp") == BASELINE_CATEGORIES
    assert provenance()["criteria_metadata"]["baseline-1/osps_ac_01_01"]["major"] == "General"
    guide = tmp_path / catalog_generator.CATEGORY_GUIDE
    guide.parent.mkdir()
    guide.write_text("# Guide\n\n| `zz` | Outside the code table |\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing OSPS category codes"):
        catalog_generator.baseline_categories(tmp_path)


@pytest.mark.parametrize(
    "level,criterion_id,expected",
    [
        ("0", "osps_ac_01_01", "Basics"),
        ("baseline-2", "osps_vm_01_01", "Vulnerability Management"),
    ],
)
def test_generator_uses_code_categories_only_for_baseline(
    catalog_generator, level, criterion_id, expected
):
    category = catalog_generator.category(
        level, criterion_id, {"major": "Basics"}, BASELINE_CATEGORIES
    )
    assert category == expected


@pytest.mark.parametrize("criterion_id", ["osps_zz_01_01", "osps_ac_1_01", "interact"])
def test_generator_rejects_baseline_ids_without_a_documented_code(catalog_generator, criterion_id):
    with pytest.raises(ValueError, match=f"No documented category code: baseline-1/{criterion_id}"):
        catalog_generator.category(
            "baseline-1", criterion_id, {"major": "General"}, BASELINE_CATEGORIES
        )


@pytest.mark.parametrize(
    "raw,true_flags",
    [
        ({}, set()),
        ({"met_url_required": True}, {"met_url_required", "met_justification_required"}),
        ({"na_justification_required": True}, {"na_justification_required", "na_allowed"}),
        ({"met_justification_required": True}, {"met_justification_required"}),
        ({"na_allowed": True}, {"na_allowed"}),
        (
            {"met_url_required": True, "met_justification_required": False},
            {"met_url_required", "met_justification_required"},
        ),
        (
            {"na_justification_required": True, "na_allowed": False},
            {"na_justification_required", "na_allowed"},
        ),
    ],
)
def test_generator_expands_only_documented_implications(catalog_generator, raw, true_flags):
    original = dict(raw)
    flags = catalog_generator.boolean_flags(raw)
    assert set(flags) == set(catalog_generator.FLAGS)
    assert all(type(value) is bool for value in flags.values())
    assert {flag for flag, value in flags.items() if value} == true_flags
    assert raw == original


@pytest.mark.parametrize(
    "flag",
    ("na_allowed", "na_justification_required", "met_justification_required", "met_url_required"),
)
@pytest.mark.parametrize("invalid", (1, "true", None))
def test_generator_rejects_nonboolean_flags_before_entailment(catalog_generator, flag, invalid):
    raw = dict.fromkeys(catalog_generator.FLAGS, True)
    raw[flag] = invalid
    with pytest.raises(ValueError, match=f"Non-boolean criterion flag: {flag}"):
        catalog_generator.boolean_flags(raw)


def test_index_filters_and_caller_mutation_do_not_change_catalog() -> None:
    index = get_criteria()
    validate_output("get_criteria", index)
    assert catalog_levels() == list(COUNTS)
    assert {entry["level"]: entry["criterion_count"] for entry in index["levels"]} == COUNTS
    assert index["level"] is None and index["detail"] is None
    assert index["criteria"] == []
    assert get_criteria("passing", [])["criteria"] == []
    selected = get_criteria("passing", ["interact", "description_good"])
    assert [c["criterion_id"] for c in selected["criteria"]] == ["description_good", "interact"]
    selected["criteria"][0]["description"] = "caller changed this"
    index["levels"].clear()
    index["catalog"].clear()
    catalog_levels().clear()
    catalog_reference().clear()
    assert len(get_criteria()["levels"]) == 6
    assert get_criteria()["catalog"]["revision"] == catalog_reference()["revision"]
    assert get_criteria("passing", ["description_good"])["criteria"][0]["description"] != (
        "caller changed this"
    )


def test_level_summaries_name_categories_in_lexical_order() -> None:
    summaries = {entry["level"]: entry["categories"] for entry in get_criteria()["levels"]}
    assert summaries["passing"] == [
        "Analysis",
        "Basics",
        "Change Control",
        "Quality",
        "Reporting",
        "Security",
    ]
    assert "Reporting" not in summaries["gold"]
    named = set(BASELINE_CATEGORIES.values())
    assert set(summaries["baseline-1"]) == named - {"Security Assessment"}
    assert set(summaries["baseline-2"]) == named
    assert set(summaries["baseline-3"]) == named - {"Legal"}
    assert get_criteria("gold")["levels"] == [
        {"level": "gold", "criterion_count": 23, "categories": summaries["gold"]}
    ]


@pytest.mark.parametrize("level", COUNTS)
def test_a_level_defaults_to_an_index_of_every_criterion(level) -> None:
    index = get_criteria(level)
    validate_output("get_criteria", index)
    assert index["detail"] == "index"
    assert index["criteria"] == [
        {key: row[key] for key in ("criterion_id", "category", "requirement")}
        for row in criterion_definitions(level)
    ]
    assert len(index["criteria"]) == COUNTS[level]
    full = get_criteria(level, detail="full")
    assert len(json.dumps(index)) * 5 < len(json.dumps(full))


def test_detail_defaults_to_full_only_for_named_criteria() -> None:
    assert get_criteria("passing", ["interact"])["detail"] == "full"
    assert get_criteria("passing", [])["detail"] == "full"
    assert get_criteria("passing", category="Basics")["detail"] == "index"
    named = get_criteria("passing", ["interact"], detail="index")
    assert named["criteria"] == [
        {"criterion_id": "interact", "category": "Basics", "requirement": "MUST"}
    ]


def test_category_narrows_either_form_of_a_level() -> None:
    index = get_criteria("passing", category="Security")
    full = get_criteria("passing", category="Security", detail="full")
    validate_output("get_criteria", full)
    assert len(index["criteria"]) == 16
    assert [row["criterion_id"] for row in full["criteria"]] == [
        row["criterion_id"] for row in index["criteria"]
    ]
    assert {row["category"] for row in full["criteria"]} == {"Security"}
    assert "description" in full["criteria"][0] and "description" not in index["criteria"][0]
    access = get_criteria("baseline-1", category="Access Control")["criteria"]
    assert [row["criterion_id"] for row in access] == [
        "osps_ac_01_01",
        "osps_ac_02_01",
        "osps_ac_03_01",
        "osps_ac_03_02",
    ]
    with pytest.raises(DomainError):
        get_criteria("baseline-1", category="General")


def test_unknown_category_lists_the_level_categories() -> None:
    with pytest.raises(DomainError) as error:
        get_criteria("gold", category="security")
    assert error.value.code == "invalid_category"
    assert error.value.details == {
        "level": "gold",
        "allowed": ["Analysis", "Basics", "Change Control", "Quality", "Security"],
    }
    with pytest.raises(DomainError) as error:
        get_criteria("gold", ["hardening"], category="Security")
    assert error.value.code == "invalid_category"


@pytest.mark.parametrize("arguments", [{"category": "Basics"}, {"detail": "full"}])
def test_category_and_detail_require_a_level(arguments) -> None:
    with pytest.raises(DomainError) as error:
        get_criteria(**arguments)
    assert error.value.code == "invalid_level"


@pytest.mark.parametrize(
    ("level", "ids", "code"),
    [
        ("bronze", None, "invalid_level"),
        (None, [], "invalid_level"),
        ("passing", ["hardening"], "invalid_criterion"),
        ("passing", ["interact", "interact"], "invalid_criterion"),
        ("passing", [False], "invalid_criterion"),
    ],
)
def test_bad_level_or_filter_is_actionable(level, ids, code) -> None:
    with pytest.raises(DomainError) as error:
        get_criteria(level, ids)
    assert error.value.code == code


def test_baseline_aliases_cover_both_fields_without_guessing() -> None:
    aliases = field_aliases()
    assert len(aliases) == 64 * 2
    assert aliases["OSPS-AC-01.01_status"] == "osps_ac_01_01_status"
    assert aliases["OSPS-AC-01.01_justification"] == "osps_ac_01_01_justification"
    assert "osps-ac-01.01_status" not in aliases
    assert "OSPS_AC_01_01_status" not in aliases
    aliases.clear()
    assert field_aliases()


def test_provenance_identifies_all_inputs_and_retains_source_metadata(source_manifest) -> None:
    source = source_manifest
    data = provenance()
    assert data["revision"] == source["revision"]
    assert data["repository"] == source["repository"]
    assert data["generated_at"] == source["generated_at"]
    base_url = f"{source['repository']}/blob/{source['revision']}"
    assert catalog_reference() == {
        "revision": source["revision"],
        "source_url": f"{base_url}/criteria/criteria.yml",
        "generated_at": source["generated_at"],
        "format_version": 1,
    }
    assert get_criteria()["catalog"] == {
        **catalog_reference(),
        "text_source_url": f"{base_url}/config/locales/en.yml",
    }
    assert data["counts"] == COUNTS
    assert data["files"] == source["files"]
    assert (
        data["generator"]["sha256"]
        == hashlib.sha256((ROOT / "scripts/generate_catalog.py").read_bytes()).hexdigest()
    )
    for name, digest in data["files"].items():
        assert hashlib.sha256((ROOT / "vendor/badgeapp" / name).read_bytes()).hexdigest() == digest
    assert len(data["criteria_metadata"]) == sum(COUNTS.values())
    assert all({"future", "obsolete"} <= row.keys() for row in data["criteria_metadata"].values())
    license_text = (
        files("best_practices_mcp")
        .joinpath("data/BADGEAPP-LICENSE.txt")
        .read_text(encoding="utf-8")
    )
    assert license_text == (ROOT / "vendor/badgeapp/LICENSE").read_text(encoding="utf-8")
    assert "The MIT License" in license_text


def test_regeneration_is_byte_reproducible_from_vendored_sources(tmp_path: Path) -> None:
    output = tmp_path / "generated"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/generate_catalog.py"), "--output-dir", str(output)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    assert "Catalog generated" in result.stdout
    for name in ("catalog.json", "provenance.json", "BADGEAPP-LICENSE.txt"):
        assert (output / name).read_bytes() == files("best_practices_mcp").joinpath(
            f"data/{name}"
        ).read_bytes()


def test_metadata_refresh_preserves_catalog_bytes_and_updates_public_references(
    tmp_path, catalog_generator, monkeypatch
):
    source = tmp_path / "source"
    shutil.copytree(ROOT / "vendor/badgeapp", source)
    before = catalog_generator.catalog_content(source)
    manifest_path = source / "source.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(revision="a" * 40, generated_at="2030-01-01T00:00:00Z")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    after = catalog_generator.catalog_content(source)
    assert after["catalog.json"] == before["catalog.json"]
    assert after["provenance.json"] != before["provenance.json"]

    data = tmp_path / "package" / "data"
    data.mkdir(parents=True)
    for name, content in after.items():
        (data / name).write_bytes(content)
    monkeypatch.setattr(criteria_module, "files", lambda package: data.parent)
    criteria_module._catalog.cache_clear()
    try:
        result = get_criteria("passing")
        validate_output("get_criteria", result)
        base_url = f"{manifest['repository']}/blob/{manifest['revision']}"
        assert result["catalog"] == {
            "revision": manifest["revision"],
            "generated_at": manifest["generated_at"],
            "source_url": f"{base_url}/criteria/criteria.yml",
            "format_version": 1,
            "text_source_url": f"{base_url}/config/locales/en.yml",
        }
    finally:
        criteria_module._catalog.cache_clear()


def test_unsupported_packaged_catalog_format_is_rejected(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "catalog.json").write_text('{"format_version": 999}', encoding="utf-8")
    monkeypatch.setattr(criteria_module, "files", lambda package: tmp_path)
    criteria_module._catalog.cache_clear()
    try:
        with pytest.raises(ValueError, match="Unsupported packaged catalog format"):
            get_criteria()
    finally:
        criteria_module._catalog.cache_clear()


def test_generator_refuses_tampered_source_and_check_refuses_drift(tmp_path: Path) -> None:
    source = tmp_path / "source"
    shutil.copytree(ROOT / "vendor/badgeapp", source)
    (source / "criteria/criteria.yml").write_text("tampered: true\n")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/generate_catalog.py"),
            "--source-dir",
            str(source),
            "--output-dir",
            str(tmp_path / "output"),
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "Source hash mismatch" in result.stderr
    assert not (tmp_path / "output").exists()
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/generate_catalog.py"),
            "--check",
            "--output-dir",
            str(tmp_path / "missing"),
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "Catalog differs" in result.stdout
    assert not (tmp_path / "missing").exists()
