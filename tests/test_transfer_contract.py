"""Proposal routes, field reporting and exact payloads across observed records."""

from urllib.parse import parse_qs, urlsplit

import pytest

from best_practices_mcp.proposals import prepare_update_url

STATUS = "description_good_status"
JUST = "description_good_justification"
OBSERVATION = {
    "project_id": 123,
    "source_url": "https://www.bestpractices.dev/projects/123.json",
    "fetched_at": "2026-11-09T00:00:00Z",
    "attribution": None,
    "license": None,
}


@pytest.mark.parametrize("field", [JUST, "description"], ids=["justification", "metadata"])
@pytest.mark.parametrize("value", ["new text", "", " \tnew text\r\n", "\x00new text\x00"])
@pytest.mark.parametrize("forced", [False, True])
def test_standalone_values_are_identical_across_observed_records(field, value, forced):
    draft = {field: value}
    overrides = {"mode": "fields", "fields": [field]} if forced else {"mode": "none"}
    records = [{}, {field: None}, {field: ""}, {field: value}, {field: "other"}, {field: [1]}]
    results = [
        prepare_update_url(123, "passing", draft, record, OBSERVATION, overrides)
        for record in records
    ]
    assert all(result == results[0] for result in results)
    result = results[0]
    query = parse_qs(urlsplit(result["artifact"]["url"]).query, keep_blank_values=True)
    assert query == {field: [value], **({"overrides": [field]} if forced else {})}
    assert result["outcome"] == "complete"
    assert [row["field"] for row in result["transfer"]] == [field]
    assert result["transfer"][0]["disposition"] == "encoded"
    assert result["overrides"] == overrides
    assert result["effective_overrides"] == ([field] if forced else [])


@pytest.mark.parametrize("overrides", [[], [STATUS], [JUST], [STATUS, JUST]])
def test_status_and_justification_payloads_preserve_exact_explicit_override_scope(overrides):
    draft = {STATUS: "Met", JUST: "new wording"}
    records = [
        {},
        {STATUS: None, JUST: None},
        draft,
        {STATUS: "Met", JUST: "old wording"},
        {STATUS: "Unmet", JUST: "new wording"},
        {STATUS: "Unmet", JUST: ""},
        {STATUS: True, JUST: {"unexpected": "value"}},
    ]
    results = [
        prepare_update_url(
            123,
            "passing",
            draft,
            record,
            OBSERVATION,
            {"mode": "fields", "fields": overrides} if overrides else {"mode": "none"},
        )
        for record in records
    ]
    assert all(result == results[0] for result in results)
    result = results[0]
    query = parse_qs(urlsplit(result["artifact"]["url"]).query)
    assert query == {
        STATUS: ["Met"],
        JUST: ["new wording"],
        **({"overrides": [",".join(sorted(overrides))]} if overrides else {}),
    }
    rows = {row["field"]: row for row in result["transfer"]}
    assert set(rows) == set(draft)
    assert all(row["disposition"] == "encoded" for row in rows.values())
    assert {field for field, row in rows.items() if row["override"]} == set(overrides)
    assert result["overrides"] == (
        {"mode": "fields", "fields": sorted(overrides)} if overrides else {"mode": "none"}
    )
    assert result["effective_overrides"] == sorted(overrides)


@pytest.mark.parametrize(
    "level", ["passing", "silver", "gold", "baseline-1", "baseline-2", "baseline-3"]
)
def test_documented_edit_route_and_raw_url_values(level):
    text = "  café & source=https://example.org/a?b=1#fragment\n"
    result = prepare_update_url(
        123, level, {"description": text}, {"description": text}, OBSERVATION
    )
    artifact = result["artifact"]
    url = urlsplit(artifact["url"])
    assert (url.scheme, url.netloc, url.path) == (
        "https",
        "www.bestpractices.dev",
        f"/en/projects/123/{level}/edit",
    )
    assert parse_qs(url.query) == {"description": [text]}
    assert url.fragment == ""
    assert artifact["encoded_size_bytes"] == len(artifact["url"].encode("utf-8"))
