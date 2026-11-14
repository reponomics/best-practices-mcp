"""Synthetic compact-badge fixtures, derived from upstream revision 31325acd.

Source: app/views/projects/{badge,baseline_badge}.json.jbuilder and the badge
value methods in app/models/project.rb. No production project data is retained.
HTTP content validation has separate transport tests; these test domain mapping.
"""

import asyncio
import copy
from types import SimpleNamespace

import pytest

from best_practices_mcp.badgeapp import ORIGIN
from best_practices_mcp.badges import get_project_badge_status, get_project_badge_svg
from best_practices_mcp.contracts import validate_output
from best_practices_mcp.errors import DomainError

FETCHED_AT = "2026-11-14T12:00:00+00:00"
UPDATED_AT = "2026-11-13T08:45:00.123Z"
RECORD = {
    "id": 123,
    "name": "Synthetic badge project",
    "badge_level": "silver",
    "tiered_percentage": 250.5,
    "updated_at": UPDATED_AT,
}
SVG = '<svg xmlns="http://www.w3.org/2000/svg"><text>Badge ✓</text></svg>\n'


class FakeHTTP:
    def __init__(self, data, error=None):
        self.data = data
        self.error = error
        self.calls = []

    def result(self, kind, path):
        self.calls.append((kind, path))
        if self.error:
            raise self.error
        return SimpleNamespace(
            data=copy.deepcopy(self.data),
            source_url=ORIGIN + path,
            fetched_at=FETCHED_AT,
            headers={},
        )

    async def get_json(self, path):
        return self.result("json", path)

    async def get_svg(self, path):
        return self.result("svg", path)


def status(record=None, **arguments):
    http = FakeHTTP(RECORD if record is None else record)
    result = asyncio.run(get_project_badge_status(http, project_id=123, **arguments))
    validate_output("get_project_badge_status", result)
    return result, http


def test_default_status_is_one_compact_request_with_unchanged_values():
    result, http = status()
    assert http.calls == [("json", "/projects/123/badge.json")]
    assert result["project"] == {"project_id": 123, "name": RECORD["name"]}
    assert result["family"] == "best_practices"
    assert result["badge_level"] == "silver"
    assert result["badge_state"] == "earned"
    assert result["progress"] == {"field": "tiered_percentage", "value": 250.5, "level": None}
    assert result["updated_at"] == UPDATED_AT
    assert result["updated_at_status"] == "valid"
    assert result["observation"] == {
        "source_url": ORIGIN + "/projects/123/badge.json",
        "fetched_at": FETCHED_AT,
        "service_attribution": "OpenSSF Best Practices badge contributors",
        "project_entry_attribution": None,
        "project_entry_license": None,
    }
    assert "answers" not in result and "accepted" not in result


@pytest.mark.parametrize("badge", ["baseline-1", "baseline-2", "baseline-3"])
def test_baseline_earned_badge_keeps_level_one_progress_meaning(badge):
    record = RECORD | {"badge_level": badge, "badge_percentage": 100}
    result, http = status(record, family="baseline")
    assert http.calls == [("json", "/projects/123/baseline.json")]
    assert result["family"] == "baseline"
    assert result["badge_state"] == "earned"
    assert result["progress"] == {
        "field": "badge_percentage",
        "value": 100,
        "level": "baseline-1",
    }
    assert "tiered_percentage" not in result


@pytest.mark.parametrize(
    "family,value,expected",
    [
        ("best_practices", "in_progress", "in_progress"),
        ("best_practices", "passing", "earned"),
        ("best_practices", "gold", "earned"),
        ("best_practices", "platinum", "unrecognized"),
        ("best_practices", "baseline-1", "unrecognized"),
        ("best_practices", None, "unknown"),
        ("baseline", "baseline-pct-0", "in_progress"),
        ("baseline", "baseline-pct-65", "in_progress"),
        ("baseline", "baseline-pct-99", "in_progress"),
        ("baseline", "baseline-pct-100", "unrecognized"),
        ("baseline", "baseline-pct-01", "unrecognized"),
        ("baseline", "baseline-pct--1", "unrecognized"),
        ("baseline", "in_progress", "unrecognized"),
        ("baseline", "baseline-4", "unrecognized"),
        ("baseline", None, "unknown"),
    ],
)
def test_badge_state_is_family_specific_and_preserves_unrecognized_values(family, value, expected):
    result, _ = status(RECORD | {"badge_level": value}, family=family)
    assert result["badge_level"] == value
    assert result["badge_state"] == expected


@pytest.mark.parametrize("family", ["best_practices", "baseline"])
def test_absent_fields_remain_unknown_without_synthesized_progress_or_time(family):
    result, _ = status({"id": 123}, family=family)
    assert result["project"]["name"] is None
    assert result["badge_level"] is None
    assert result["badge_state"] == "unknown"
    assert result["progress"]["value"] is None
    assert result["updated_at"] is None
    assert result["updated_at_status"] == "missing"
    assert result["observation"]["fetched_at"] == FETCHED_AT


@pytest.mark.parametrize("value", [-5, 301, 1.75, None])
@pytest.mark.parametrize(
    "family,field", [("best_practices", "tiered_percentage"), ("baseline", "badge_percentage")]
)
def test_upstream_progress_is_not_clamped_or_reinterpreted(value, family, field):
    result, _ = status(RECORD | {field: value}, family=family)
    assert result["progress"]["value"] == value


@pytest.mark.parametrize("value", [True, "75", [], {}, float("nan"), float("inf")])
@pytest.mark.parametrize(
    "family,field", [("best_practices", "tiered_percentage"), ("baseline", "badge_percentage")]
)
def test_invalid_progress_is_explicit_failure(value, family, field):
    with pytest.raises(DomainError) as caught:
        status(RECORD | {field: value}, family=family)
    assert caught.value.code == "upstream_invalid_response"
    assert caught.value.details == {"field": field}


@pytest.mark.parametrize(
    "value,expected",
    [
        (UPDATED_AT, "valid"),
        ("2026-11-13T08:45:00-05:00", "valid"),
        ("2026-11-13t08:45:00z", "valid"),
        (None, "missing"),
        ("", "invalid"),
        ("yesterday", "invalid"),
        ("2026-11-13", "invalid"),
        ("2026-11-13T08:45:00", "invalid"),
        ("2026-11-13 08:45:00Z", "invalid"),
        ("2026-02-30T08:45:00Z", "invalid"),
        ("2026-11-13T25:45:00Z", "invalid"),
        ("2026-11-13T08:45:00+00:60", "invalid"),
    ],
)
def test_timestamp_is_preserved_and_validated_separately_from_fetch_time(value, expected):
    result, _ = status(RECORD | {"updated_at": value})
    assert result["updated_at"] == value
    assert result["updated_at_status"] == expected
    assert result["observation"]["fetched_at"] == FETCHED_AT


@pytest.mark.parametrize("field", ["name", "badge_level", "updated_at"])
@pytest.mark.parametrize("value", [False, 123, {}, []])
def test_invalid_text_fields_are_not_coerced(field, value):
    with pytest.raises(DomainError) as caught:
        status(RECORD | {field: value})
    assert caught.value.code == "upstream_invalid_response"
    assert caught.value.details == {"field": field}


@pytest.mark.parametrize("data", [[], "record", {"id": True}, {"id": 0}, {}])
def test_invalid_record_identity_is_rejected(data):
    with pytest.raises(DomainError) as caught:
        status(data)
    assert caught.value.code == "upstream_invalid_response"


def test_mismatched_record_is_not_a_status_for_the_requested_project():
    with pytest.raises(DomainError) as caught:
        status(RECORD | {"id": 456})
    assert caught.value.code == "project_mismatch"


def test_endpoint_does_not_claim_record_attribution_from_unrecognized_extra_fields():
    result, _ = status(
        RECORD | {"project_entry_attribution": "unexpected", "project_entry_license": "MIT"}
    )
    assert result["observation"]["project_entry_attribution"] is None
    assert result["observation"]["project_entry_license"] is None
    assert any("does not supply project-entry" in caveat for caveat in result["caveats"])


def test_changed_time_or_progress_is_not_reported_as_submission_acceptance():
    before, _ = status()
    after_time, _ = status(RECORD | {"updated_at": "2026-11-14T01:00:00Z"})
    after_progress, _ = status(RECORD | {"tiered_percentage": 275})
    for result in (before, after_time, after_progress):
        assert "accepted" not in result
        assert "changes" not in result
        assert result["caveats"] == before["caveats"]
    assert before["progress"] == after_time["progress"]
    assert before["updated_at"] == after_progress["updated_at"]


@pytest.mark.parametrize(
    "family,suffix,section,label",
    [
        ("best_practices", "badge", "passing", "OpenSSF Best Practices"),
        ("baseline", "baseline", "baseline-1", "OpenSSF Baseline"),
    ],
)
def test_svg_artifact_is_exact_and_markdown_uses_dynamic_family_urls(
    family, suffix, section, label
):
    http = FakeHTTP(SVG)
    result = asyncio.run(get_project_badge_svg(http, 123, family))
    validate_output("get_project_badge_svg", result)
    assert http.calls == [("svg", f"/projects/123/{suffix}.svg")]
    assert result["family"] == family
    assert result["image_url"] == f"{ORIGIN}/projects/123/{suffix}.svg"
    assert result["project_url"] == f"{ORIGIN}/en/projects/123/{section}"
    assert result["artifact"] == {
        "svg": SVG,
        "media_type": "image/svg+xml",
        "suggested_filename": f"bestpractices-123-{suffix}.svg",
        "encoded_size_bytes": len(SVG.encode("utf-8")),
    }
    assert result["markdown"] == (
        f"[![{label} — project 123]({result['image_url']})]({result['project_url']})"
    )
    assert "badge_static" not in result["markdown"]
    assert result["observation"]["source_url"] == result["image_url"]
    assert result["observation"]["fetched_at"] == FETCHED_AT
    assert "updated_at" not in result


@pytest.mark.parametrize("data", [None, b"svg", "\ud800"])
def test_svg_artifact_rejects_nontext_or_unencodable_adapter_data(data):
    with pytest.raises(DomainError) as caught:
        asyncio.run(get_project_badge_svg(FakeHTTP(data), 123, "baseline"))
    assert caught.value.code == "upstream_invalid_response"


@pytest.mark.parametrize("operation", [get_project_badge_status, get_project_badge_svg])
@pytest.mark.parametrize("project_id", [True, 0, -1, "123", None])
def test_invalid_ids_never_request_network(operation, project_id):
    http = FakeHTTP(RECORD)
    with pytest.raises(DomainError) as caught:
        asyncio.run(operation(http, project_id, "best_practices"))
    assert caught.value.code == "invalid_field"
    assert http.calls == []


@pytest.mark.parametrize("operation", [get_project_badge_status, get_project_badge_svg])
@pytest.mark.parametrize("family", ["passing", "baseline-1", "", None, [], True])
def test_invalid_families_never_request_network(operation, family):
    http = FakeHTTP(RECORD)
    with pytest.raises(DomainError) as caught:
        asyncio.run(operation(http, 123, family))
    assert caught.value.code == "invalid_field"
    assert http.calls == []


@pytest.mark.parametrize("operation", [get_project_badge_status, get_project_badge_svg])
@pytest.mark.parametrize("code", ["project_not_found", "rate_limited", "upstream_unavailable"])
def test_transport_failures_propagate_without_fallback_requests(operation, code):
    failure = DomainError(code, "Synthetic failure.")
    http = FakeHTTP(None, failure)
    with pytest.raises(DomainError) as caught:
        asyncio.run(operation(http, 123, "baseline"))
    assert caught.value is failure
    assert len(http.calls) == 1
