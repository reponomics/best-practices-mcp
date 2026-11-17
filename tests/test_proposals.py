"""URL eligibility, explicit overrides and exact artifact encoding."""

from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

import pytest

from best_practices_mcp.criteria import get_criteria
from best_practices_mcp.errors import DomainError
from best_practices_mcp.models import PrepareURLResult
from best_practices_mcp.proposals import prepare_update_url

OBSERVATION = {
    "project_id": 123,
    "source_url": "https://www.bestpractices.dev/projects/123.json",
    "fetched_at": "2026-11-09T00:00:00Z",
    "attribution": None,
    "license": None,
}
STATUS = "description_good_status"
JUST = "description_good_justification"


def fields(*names):
    return {"mode": "fields", "fields": list(names)}


def prepare(draft, record=None, overrides=None, section="passing"):
    result = prepare_update_url(123, section, draft, record or {}, OBSERVATION, overrides)
    PrepareURLResult.model_validate(result)
    return result


def reports(result):
    return {item["field"]: item for item in result["transfer"]}


def params(result):
    return parse_qs(urlsplit(result["artifact"]["url"]).query, keep_blank_values=True)


@pytest.mark.parametrize(
    ("draft", "record", "outcome"),
    [
        ({STATUS: "Met"}, {}, "complete"),
        ({STATUS: "Met", "extra": 1}, {}, "partial"),
        ({STATUS: "Met", "extra": 1}, {STATUS: "Met"}, "partial"),
        ({STATUS: "Met"}, {STATUS: "Met"}, "complete"),
        ({STATUS: "?"}, {STATUS: "?"}, "complete"),
        ({}, {}, "no_supplied_transferable_answers"),
        ({"id": 123}, {}, "no_supplied_transferable_answers"),
        ({"access_continuity_status": 12}, {}, "no_supplied_transferable_answers"),
    ],
)
def test_outcomes(draft, record, outcome):
    result = prepare(draft, record)
    assert result["outcome"] == outcome
    assert (result["artifact"] is not None) == (outcome in {"complete", "partial"})
    assert result["no_artifact_reason"] == (None if result["artifact"] else outcome)


@pytest.mark.parametrize("saved", ["?", "", None, "Unmet", "Met", "nonsense", 3])
@pytest.mark.parametrize("forced", [False, True])
def test_status_value_and_explicit_override_do_not_depend_on_observed_answer(saved, forced):
    result = prepare(
        {STATUS: "Met"}, {STATUS: saved}, fields(STATUS) if forced else {"mode": "none"}
    )
    assert params(result) == {
        STATUS: ["Met"],
        **({"overrides": [STATUS]} if forced else {}),
    }
    assert reports(result)[STATUS]["disposition"] == "encoded"
    assert reports(result)[STATUS]["override"] is forced
    assert set(reports(result)[STATUS]) == {
        "field",
        "disposition",
        "reason",
        "override",
        "applicable_levels",
        "restrictions",
    }


def test_missing_observed_answers_do_not_prevent_supplied_fields():
    draft = {STATUS: "Met", JUST: "explanation", "name": "new"}
    result = prepare(draft)
    assert params(result) == {field: [value] for field, value in draft.items()}
    assert {row["disposition"] for row in result["transfer"]} == {"encoded"}


def test_status_override_is_encoded_once_without_adding_justification_override():
    result = prepare(
        {STATUS: "Met", JUST: "new"}, {STATUS: "Met", JUST: "old"}, fields(STATUS, STATUS)
    )
    assert result["overrides"] == fields(STATUS)
    assert result["effective_overrides"] == [STATUS]
    assert params(result) == {STATUS: ["Met"], JUST: ["new"], "overrides": [STATUS]}
    assert reports(result)[STATUS]["override"]
    assert not reports(result)[JUST]["override"]


def test_justification_override_does_not_suppress_or_force_supplied_status():
    result = prepare({STATUS: "Met", JUST: "new"}, {STATUS: "Unmet", JUST: "old"}, fields(JUST))
    assert params(result) == {STATUS: ["Met"], JUST: ["new"], "overrides": [JUST]}
    assert result["overrides"] == fields(JUST)
    assert result["effective_overrides"] == [JUST]
    assert not reports(result)[STATUS]["override"]
    assert reports(result)[JUST]["override"]


def test_effective_overrides_only_contain_fields_in_the_artifact():
    result = prepare({STATUS: "Met", JUST: 12}, overrides=fields(STATUS, JUST))
    assert result["overrides"] == fields(*sorted([STATUS, JUST]))
    assert result["effective_overrides"] == [STATUS]
    assert params(result) == {STATUS: ["Met"], "overrides": [STATUS]}
    assert reports(result)[STATUS]["override"]
    assert not reports(result)[JUST]["override"]


@pytest.mark.parametrize(
    "override", ["*", "id", "repo_url", "absent", "access_continuity_status", "description_good"]
)
def test_overrides_reject_non_supplied_or_noncanonical_scope(override):
    with pytest.raises(DomainError, match="Override") as error:
        prepare({STATUS: "Met"}, overrides=fields(override))
    assert error.value.code == "invalid_override"


@pytest.mark.parametrize(
    "overrides",
    [
        STATUS,
        [STATUS],
        False,
        {},
        {"mode": "bad"},
        {"mode": []},
        {"mode": "none", "fields": []},
        {"mode": "all", "fields": [STATUS]},
        {"mode": "fields"},
        {"mode": "fields", "fields": []},
        {"mode": "fields", "fields": STATUS},
        {"mode": "all", "extra": True},
    ],
)
def test_overrides_reject_invalid_or_contradictory_modes(overrides):
    draft = {STATUS: "Met"}
    with pytest.raises(DomainError) as error:
        prepare(draft, overrides=overrides)
    assert error.value.code == "invalid_override"
    assert draft == {STATUS: "Met"}


def test_overrides_reject_alias_even_when_draft_alias_normalized():
    alias = "OSPS-AC-01.01_status"
    with pytest.raises(DomainError) as error:
        prepare({alias: "Met"}, overrides=fields(alias), section="baseline-1")
    assert error.value.code == "invalid_override"


@pytest.mark.parametrize("status", [None, [], True, 1, "bad", "N/A"])
def test_invalid_status_omits_companion_without_validation_gate(status):
    result = prepare({STATUS: status, JUST: "standalone", "name": "new"})
    assert reports(result)[STATUS]["disposition"] == "invalid"
    assert reports(result)[JUST]["reason"] == "invalid_companion_status"
    assert result["outcome"] == "partial"
    assert params(result) == {"name": ["new"]}


def test_unknown_status_does_not_block_valid_justification():
    result = prepare({STATUS: "?", JUST: "standalone"}, {JUST: ""})
    assert result["outcome"] == "complete"
    assert reports(result)[JUST]["disposition"] == "encoded"
    assert params(result) == {STATUS: ["?"], JUST: ["standalone"]}
    assert result["warnings"][0]["fields"] == [STATUS]


def test_bad_justification_does_not_block_status_or_apply_evidence_validation():
    result = prepare({STATUS: "Met", JUST: None}, {STATUS: "?"})
    assert result["outcome"] == "partial"
    assert params(result) == {STATUS: ["Met"]}


@pytest.mark.parametrize(
    ("value", "saved"),
    [
        (" \tnew\r\n", "old"),
        (" \tnew\r\n", "new"),
        ("\x00new\x00", "new"),
        ("\u00a0new\u00a0", "new"),
        ("new", "\u00a0"),
        ("", ""),
    ],
)
def test_url_preserves_whitespace_control_characters_and_empty_values(value, saved):
    result = prepare({JUST: value}, {JUST: saved})
    assert result["outcome"] == "complete"
    assert reports(result)[JUST]["disposition"] == "encoded"
    assert params(result)[JUST] == [value]


def test_raw_unicode_reserved_and_empty_values_are_encoded_exactly_once():
    text = ' é +&=%20?/#\n"; alert(1); //'
    result = prepare(
        {JUST: text, "description": ""},
        {JUST: "old", "description": "old"},
        fields(JUST, "description"),
    )
    url = result["artifact"]["url"]
    assert params(result)[JUST] == [text]
    assert params(result)["description"] == [""]
    assert "%20" in url and "+" not in url
    assert result["artifact"]["encoded_size_bytes"] == len(url.encode())


def test_all_metadata_fields_available_at_all_levels():
    draft = {name: "new" for name in ("name", "description", "license", "implementation_languages")}
    for level in get_criteria()["levels"]:
        result = prepare(draft, section=level)
        assert result["outcome"] == "complete"
        assert set(params(result)) == set(draft)


def test_long_valid_values_are_neither_truncated_nor_advisory_gated():
    text = "x" * 50000
    result = prepare({JUST: text})
    assert params(result)[JUST] == [text]


def test_inputs_are_not_mutated_and_provenance_is_never_encoded():
    draft = {"id": 123, "repo_url": "https://example.com/repo", STATUS: "Met", "extra": [1]}
    original = deepcopy(draft)
    record = {"repo_url": "https://example.com/repo"}
    result = prepare(draft, record)
    assert draft == original
    assert params(result) == {STATUS: ["Met"]}
    assert result["identity"]["repo_check"] == "matched"
    assert [row["field"] for row in result["transfer"]] == sorted(draft)


def test_report_accounts_for_included_and_excluded_supplied_fields():
    draft = {
        "id": 123,
        "name": "same name",
        STATUS: "?",
        JUST: 12,
        "access_continuity_status": "Met",
        "extra": "opaque",
    }
    result = prepare(draft, {"name": "same name"}, fields("name", STATUS))
    assert result["outcome"] == "partial"
    assert params(result) == {
        "name": ["same name"],
        STATUS: ["?"],
        "overrides": [",".join(sorted(["name", STATUS]))],
    }
    assert {field: row["disposition"] for field, row in reports(result).items()} == {
        "id": "omitted",
        "name": "encoded",
        STATUS: "encoded",
        JUST: "invalid",
        "access_continuity_status": "outside_level",
        "extra": "unsupported",
    }
    assert result["overrides"] == fields(*sorted(["name", STATUS]))
    assert result["effective_overrides"] == sorted(["name", STATUS])


def test_identity_mismatch_stops_artifact():
    with pytest.raises(DomainError) as error:
        prepare({"id": 124, STATUS: "Met"})
    assert error.value.code == "project_mismatch"


def test_override_all_encodes_wildcard_and_only_reports_encoded_fields():
    draft = {STATUS: "?", JUST: "", "name": "same", "id": 123, "extra": "opaque"}
    result = prepare(draft, overrides={"mode": "all"})
    assert params(result) == {STATUS: ["?"], JUST: [""], "name": ["same"], "overrides": ["*"]}
    assert result["overrides"] == {"mode": "all"}
    assert result["effective_overrides"] == sorted([STATUS, JUST, "name"])
    assert not reports(result)["id"]["override"]
    assert not reports(result)["extra"]["override"]


@pytest.mark.parametrize("overrides", [None, {"mode": "none"}, {"mode": "all"}, fields(STATUS)])
def test_unknown_only_proposal_is_encoded_with_nonblocking_warning(overrides):
    result = prepare({STATUS: "?"}, overrides=overrides)
    assert result["outcome"] == "complete"
    assert params(result)[STATUS] == ["?"]
    assert "%3F" in result["artifact"]["url"]
    assert reports(result)[STATUS]["disposition"] == "encoded"
    assert result["warnings"][0]["code"] == "unknown_status_reset_unsupported"
    assert result["warnings"][0]["fields"] == [STATUS]


def test_choose_section_preserves_mixed_level_proposals_and_field_applicability():
    draft = {STATUS: "Met", "osps_br_04_01_status": "?", "name": "example"}
    result = prepare(draft, section="choose_section", overrides={"mode": "all"})
    assert result["section"] == "choose_section"
    assert result["schema_version"] == 2
    assert urlsplit(result["artifact"]["url"]).path == "/en/projects/123/choose/edit"
    assert params(result) == {
        **{field: [value] for field, value in draft.items()},
        "overrides": ["*"],
    }
    assert reports(result)[STATUS]["applicable_levels"] == ["passing"]
    assert reports(result)["osps_br_04_01_status"]["applicable_levels"] == ["baseline-2"]
    assert reports(result)["name"]["applicable_levels"] == get_criteria()["levels"]
    assert result["warnings"][0]["fields"] == ["osps_br_04_01_status"]


@pytest.mark.parametrize(
    ("criterion", "allowed"), [("dynamic_analysis", "gold"), ("report_tracker", "silver")]
)
def test_choose_section_preserves_shared_values_valid_at_any_applicable_level(criterion, allowed):
    status = f"{criterion}_status"
    justification = f"{criterion}_justification"
    draft = {status: "N/A", justification: "Supplied explanation"}
    result = prepare(draft, section="choose_section")
    assert result["outcome"] == "complete"
    assert params(result) == {field: [value] for field, value in draft.items()}
    status_report = reports(result)[status]
    assert status_report["applicable_levels"] == ["passing", allowed]
    assert status_report["restrictions"] == [{"level": "passing", "reason": "na_not_supported"}]
    assert reports(result)[justification]["restrictions"] == [
        {"level": "passing", "reason": "invalid_companion_status"}
    ]
    assert prepare(draft, section="passing")["artifact"] is None
    assert prepare(draft, section=allowed)["artifact"] is not None


def test_specific_section_reports_other_level_without_warning_for_unencoded_unknown():
    result = prepare({STATUS: "Met", "osps_br_04_01_status": "?"})
    assert params(result) == {STATUS: ["Met"]}
    excluded = reports(result)["osps_br_04_01_status"]
    assert excluded["disposition"] == "outside_level"
    assert excluded["applicable_levels"] == ["baseline-2"]
    assert result["warnings"] == []
