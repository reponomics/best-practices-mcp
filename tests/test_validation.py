"""Required advisory-validation contract from docs/specification.md §4.

The human-readable predicate cases exercise the agreed minimum length, exact
comment prefix, and URL-pattern rules independently of upstream implementation.
"""

import json
from pathlib import Path

import pytest

from best_practices_mcp.contracts import validate_output
from best_practices_mcp.criteria import get_criteria
from best_practices_mcp.errors import DomainError
from best_practices_mcp.validation import contains_url, usable_justification, validate_draft

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/documents/advisory-predicates.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", FIXTURE["cases"])
def test_agreed_advisory_predicates(case: dict) -> None:
    assert usable_justification(case["text"]) == case["usable"]
    assert contains_url(case["text"]) == case["url"]


def test_empty_document_does_not_imply_whole_application_checked() -> None:
    result = validate_draft(8, "passing", {})
    validate_output("validate_draft", result)
    assert result["findings"] == result["checked_criteria"] == result["skipped_criteria"] == []
    assert result["draft_source"] == {"kind": "explicit", "location": None}


@pytest.mark.parametrize(
    "status,reason",
    [
        (None, "status_absent"),
        ("?", "status_unknown"),
        (False, "status_invalid"),
        ("bad", "status_invalid"),
    ],
)
def test_represented_shape_checks_and_conditional_skips_overlap(
    status: object, reason: str
) -> None:
    draft = {"contribution_justification": "https://a.b"}
    if status is not None:
        draft["contribution_status"] = status
    result = validate_draft(8, "passing", draft)
    validate_output("validate_draft", result)
    assert result["checked_criteria"] == ["contribution"]
    assert result["skipped_criteria"][0]["reason"] == reason
    assert not any(f["code"].startswith("missing") for f in result["findings"])


def test_other_level_invalid_values_are_not_selected_level_findings() -> None:
    result = validate_draft(
        8,
        "passing",
        {
            "osps_ac_01_01_status": {},
            "osps_ac_01_01_justification": 5,
            "extra": [None],
            "name": False,
        },
    )
    assert result["checked_criteria"] == []
    assert result["skipped_criteria"] == [
        {
            "criterion_id": "osps_ac_01_01",
            "reason": "other_level",
            "checks": ["field_shape", "conditional_requirements"],
        }
    ]
    assert [(f["field"], f["code"], f["criterion_id"]) for f in result["findings"]] == [
        ("extra", "unknown_field", None),
        ("name", "invalid_type", None),
    ]


def test_all_catalog_flags_apply_at_their_own_levels() -> None:
    for level in get_criteria()["levels"]:
        for criterion in get_criteria(level)["criteria"]:
            for status in ("Met", "Unmet", "N/A"):
                result = validate_draft(8, level, {criterion["status_field"]: status})
                codes = {finding["code"] for finding in result["findings"]}
                assert ("na_not_allowed" in codes) == (
                    status == "N/A" and not criterion["na_allowed"]
                )
                assert ("missing_required_justification" in codes) == (
                    (
                        status == "Met"
                        and criterion["met_justification_required"]
                        and not criterion["met_url_required"]
                    )
                    or (status == "N/A" and criterion["na_justification_required"])
                )
                assert ("missing_required_url" in codes) == (
                    status == "Met" and criterion["met_url_required"]
                )


@pytest.mark.parametrize(
    "level,criterion_id",
    [("gold", "build_reproducible"), ("silver", "external_dependencies")],
)
@pytest.mark.parametrize(
    "justification,expected_codes",
    [
        (None, ["missing_required_url"]),
        ("", ["missing_required_url"]),
        ("A reproducible build explanation", ["missing_required_url"]),
        ("// https://example.org/rebuild", ["missing_required_url"]),
        ("https://example.org/rebuild", []),
    ],
)
def test_entailed_justification_keeps_specific_url_finding(
    level, criterion_id, justification, expected_codes
):
    criterion = get_criteria(level, [criterion_id])["criteria"][0]
    assert criterion["met_justification_required"] and criterion["met_url_required"]
    draft = {criterion["status_field"]: "Met"}
    if justification is not None:
        draft[criterion["justification_field"]] = justification
    result = validate_draft(8, level, draft)
    validate_output("validate_draft", result)
    assert [finding["code"] for finding in result["findings"]] == expected_codes


def test_required_wrong_type_has_shape_and_missing_evidence_findings() -> None:
    result = validate_draft(
        8, "passing", {"contribution_status": "Met", "contribution_justification": []}
    )
    assert {f["code"] for f in result["findings"]} == {"invalid_type", "missing_required_url"}
    validate_output("validate_draft", result)


def test_minimum_length_is_unstripped_and_comment_prefix_is_exact() -> None:
    result = validate_draft(
        8, "passing", {"static_analysis_status": "Met", "static_analysis_justification": "     "}
    )
    assert result["findings"] == []
    result = validate_draft(
        8,
        "passing",
        {"static_analysis_status": "Met", "static_analysis_justification": "// valid explanation"},
    )
    assert result["findings"][0]["code"] == "missing_required_justification"


def test_alias_normalization_and_preserved_unknown_field_diagnostics() -> None:
    result = validate_draft(
        8,
        "baseline-1",
        {"OSPS-AC-01.01_status": "Unmet", "extra": "secret", "id": 8, "repo_url": "not a URL"},
    )
    assert result["checked_criteria"] == ["osps_ac_01_01"]
    assert len(result["findings"]) == 1
    assert result["identity"] == {
        "association": "document_provenance",
        "id_check": "matched",
        "repo_check": "not_checked",
    }
    assert "secret" not in str(result)


@pytest.mark.parametrize(
    "draft,code",
    [
        ({"id": 9}, "project_mismatch"),
        ({"id": "8"}, "project_identity_unresolved"),
        ({"OSPS-AC-01.01_status": "Met", "osps_ac_01_01_status": "Unmet"}, "invalid_document"),
    ],
)
def test_unreadable_or_mismatched_input_prevents_validation(draft: dict, code: str) -> None:
    with pytest.raises(DomainError) as error:
        validate_draft(8, "passing", draft)
    assert error.value.code == code


@pytest.mark.parametrize("level", [None, "unknown"])
def test_invalid_level_remains_operational_error(level) -> None:
    with pytest.raises(DomainError) as error:
        validate_draft(8, level, {})
    assert error.value.code == "invalid_level"
