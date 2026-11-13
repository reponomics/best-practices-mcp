"""Public-read mapping against synthetic records shaped by pinned upstream sources."""

import asyncio
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlencode

import pytest

from best_practices_mcp.badgeapp import ORIGIN, BadgeAppClient
from best_practices_mcp.contracts import validate_output
from best_practices_mcp.documents import DOCUMENT_LIMIT_BYTES
from best_practices_mcp.errors import DomainError

FIXTURES = Path(__file__).parent / "fixtures" / "api"
STAMP = "2026-11-09T12:00:00+00:00"


class FakeHTTP:
    def __init__(self, data, *, headers=None, error=None):
        self.data = data
        self.headers = headers or {}
        self.error = error
        self.calls = []

    async def get_json(self, path, params=None):
        self.calls.append((path, params))
        if self.error:
            raise self.error
        query = "?" + urlencode(sorted(params.items()), quote_via=quote) if params else ""
        return SimpleNamespace(
            data=copy.deepcopy(self.data),
            source_url=ORIGIN + path + query,
            fetched_at=STAMP,
            headers=self.headers,
        )


def fixture(name="project"):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def find(data, query="example", page=1, **kwargs):
    http = FakeHTTP(data, **kwargs)
    result = asyncio.run(BadgeAppClient(http).find_project(query, page))
    validate_output("find_project", result)
    return result, http


def progress(data=None, level=None, ids=None, project_id=123):
    http = FakeHTTP(fixture() if data is None else data)
    result = asyncio.run(BadgeAppClient(http).get_project_progress(project_id, level, ids))
    validate_output("get_project_progress", result)
    return result, http


def test_numeric_discovery_normalizes_identifier_and_preserves_observation():
    result, http = find(fixture(), " 00123 ")
    assert http.calls == [("/projects/123.json", None)]
    assert result["query"] == "123"
    assert result["query_kind"] == "id"
    assert result["candidates"][0]["match_basis"] == "id"
    assert result["observation"] == {
        "source_url": ORIGIN + "/projects/123.json",
        "fetched_at": STAMP,
    }
    assert result["next_page"] is None
    assert result["pagination_complete"] is True


def test_numeric_404_is_normal_empty_but_progress_404_is_error():
    error = DomainError(
        "project_not_found",
        "Missing.",
        details={"source_url": ORIGIN + "/projects/123.json", "fetched_at": STAMP},
    )
    result, _ = find(None, "123", error=error)
    assert result["candidates"] == []
    assert result["pagination_complete"] is True
    assert result["observation"]["fetched_at"] == STAMP
    with pytest.raises(DomainError) as caught:
        asyncio.run(BadgeAppClient(FakeHTTP(None, error=error)).get_project_progress(123))
    assert caught.value.code == "project_not_found"


def test_other_http_failures_remain_failures():
    error = DomainError("rate_limited", "Wait.", retry_after_seconds=30)
    with pytest.raises(DomainError) as caught:
        find(None, "123", error=error)
    assert caught.value is error


def test_text_search_preserves_order_ambiguity_and_pagination_uncertainty():
    records = fixture("search")
    result, http = find(records, " Example Project ", page=2)
    assert http.calls == [("/projects.json", {"q": "Example Project", "page": 2})]
    assert [row["project"]["project_id"] for row in result["candidates"]] == [123, 456]
    assert all(row["match_basis"] == "text" for row in result["candidates"])
    assert result["next_page"] is None and result["pagination_complete"] is False
    assert "page=2&q=Example%20Project" in result["observation"]["source_url"]


def test_non_github_url_query_only_ever_calls_official_search_endpoint():
    query = "https://codeberg.org/example/project"
    result, http = find(fixture("search"), query)
    assert http.calls == [("/projects.json", {"url": query, "page": 1})]
    assert [row["match_basis"] for row in result["candidates"]] == ["repo_url", "url_query"]
    assert len(result["candidates"]) == 2


def test_homepage_match_and_conservative_url_comparison():
    records = fixture("search")
    records[0]["homepage_url"] = "HTTPS://EXAMPLE.ORG:443/project"
    result, _ = find(records, "https://example.org/project")
    assert result["candidates"][0]["match_basis"] == "homepage_url"
    assert result["candidates"][1]["match_basis"] == "url_query"


def test_url_matching_preserves_nondefault_ports():
    query = "https://example.org:8443/project"
    records = [
        {"id": 123, "repo_url": "HTTPS://EXAMPLE.ORG:8443/project"},
        {"id": 456, "repo_url": "https://example.org/project"},
        {"id": 789, "repo_url": "https://example.org:9443/project"},
    ]
    result, http = find(records, query)
    assert [row["match_basis"] for row in result["candidates"]] == [
        "repo_url",
        "url_query",
        "url_query",
    ]
    assert http.calls == [("/projects.json", {"url": query, "page": 1})]


def test_excessive_numeric_identifiers_and_next_pages_are_bounded():
    previous_limit = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(640)
        digits = "9" * 641
        http = FakeHTTP([])
        with pytest.raises(DomainError) as caught:
            asyncio.run(BadgeAppClient(http).find_project(digits))
        assert caught.value.code == "invalid_query"
        assert http.calls == []

        header = f'</projects.json?page={digits}&q=example>; rel="next"'
        result, _ = find(fixture("search"), headers={"link": header})
        assert result["next_page"] is None
        assert result["pagination_complete"] is False
        assert len(result["candidates"]) == 2
    finally:
        sys.set_int_max_str_digits(previous_limit)


@pytest.mark.parametrize(
    "query,page",
    [
        ("", 1),
        (" \n", 1),
        ("123", 2),
        ("http:bad", 1),
        ("https://user:password@example.org/a", 1),
        ("https://example.org:bad/a", 1),
        ("https://example.org/with space", 1),
        (True, 1),
        ("query", False),
        ("query", 0),
        ("\ud800", 1),
    ],
)
def test_invalid_query_does_not_fetch(query, page):
    http = FakeHTTP([])
    with pytest.raises(DomainError):
        asyncio.run(BadgeAppClient(http).find_project(query, page))
    assert http.calls == []


@pytest.mark.parametrize("query", ["0", "-1", "１２３"])
def test_non_positive_or_non_ascii_identifier_text_remains_text(query):
    result, _ = find([], query)
    assert result["query_kind"] == "text"


def test_empty_page_is_complete_without_inventing_a_total():
    result, _ = find([], page=3)
    assert result["pagination_complete"] is True
    assert result["next_page"] is None
    assert "total" not in result


def test_valid_same_query_next_link_exposes_only_page_number():
    header = (
        '</projects.json?page=2&q=example>; rel="next", '
        '</projects.json?page=9&q=example>; rel="last"'
    )
    result, _ = find(fixture("search"), headers={"link": header})
    assert result["next_page"] == 2
    assert result["pagination_complete"] is False


@pytest.mark.parametrize(
    "link",
    [
        "https://evil.example/projects.json?page=2&q=example",
        "http://www.bestpractices.dev/projects.json?page=2&q=example",
        "/projects.json?page=2&q=other",
        "/projects.json?page=2&q=example&as=badge",
        "/projects.json?page=2&page=3&q=example",
        "/projects.json?page=1&q=example",
        "/projects.json?page=-2&q=example",
        "/projects.json?page=2&q=example#fragment",
        "/projects/123.json?page=2&q=example",
        "/en/projects.json?page=2&q=example",
        "http://[invalid/",
    ],
)
def test_untrusted_or_different_next_links_leave_pagination_uncertain(link):
    result, _ = find(fixture("search"), headers={"link": f'<{link}>; rel="next"'})
    assert result["next_page"] is None
    assert result["pagination_complete"] is False


def test_ambiguous_multiple_next_links_are_not_chosen():
    header = (
        '</projects.json?page=2&q=example>; rel="next", '
        '</projects.json?page=3&q=example>; rel="next"'
    )
    result, _ = find(fixture("search"), headers={"link": header})
    assert result["next_page"] is None


def test_progress_summaries_and_attribution_come_from_upstream():
    result, http = progress()
    assert http.calls == [("/projects/123.json", None)]
    assert result["answers"] == {} and result["criteria"] == []
    assert [item["upstream_percentage"] for item in result["summaries"]] == [42, 10.5, 0, 75, 25, 5]
    assert result["summary_metadata"] == {
        "badge_level": "in_progress",
        "tiered_percentage": 42,
        "baseline_tiered_percentage": 75,
    }
    assert result["observation"]["attribution"] == fixture()["project_entry_attribution"]
    assert result["observation"]["license"] == "CC-BY-3.0+"


def test_level_filter_preserves_actual_justification_and_missing_fields():
    result, _ = progress(level="passing", ids=["description_good", "contribution"])
    assert list(result["answers"]) == [
        "contribution_status",
        "description_good_status",
        "description_good_justification",
    ]
    assert (
        result["answers"]["description_good_justification"]
        == fixture()["description_good_justification"]
    )
    assert "contribution_justification" not in result["answers"]
    contribution = result["criteria"][0]
    assert contribution["status"] == "?" and contribution["status_present"] is True
    assert contribution["justification"] is None and contribution["justification_present"] is False


def test_missing_status_is_not_synthesized_and_missing_metadata_stays_null():
    result, _ = progress({"id": 123}, "passing", ["description_good"])
    assert result["answers"] == {}
    assert result["criteria"] == [
        {
            "criterion_id": "description_good",
            "status_present": False,
            "status": None,
            "justification_present": False,
            "justification": None,
        }
    ]
    assert all(item["upstream_percentage"] is None for item in result["summaries"])
    assert result["project"] == {
        "project_id": 123,
        "name": None,
        "repo_url": None,
        "homepage_url": None,
    }
    assert result["summary_metadata"] == {}


def test_baseline_status_and_justification_aliases_are_both_normalized():
    result, _ = progress(level="baseline-1", ids=["osps_ac_01_01"])
    assert result["answers"] == {
        "osps_ac_01_01_status": "Met",
        "osps_ac_01_01_justification": fixture()["OSPS-AC-01.01_justification"],
    }


def test_equal_alias_values_collapse_but_conflicts_fail():
    record = fixture()
    record["osps_ac_01_01_status"] = "Met"
    result, _ = progress(record, "baseline-1", ["osps_ac_01_01"])
    assert result["answers"]["osps_ac_01_01_status"] == "Met"
    record["osps_ac_01_01_status"] = "Unmet"
    with pytest.raises(DomainError) as caught:
        progress(record, "baseline-1", ["osps_ac_01_01"])
    assert caught.value.code == "upstream_invalid_response"


def test_unexpected_saved_field_values_are_returned_without_guessing():
    record = fixture()
    record["description_good_status"] = {"future": "value"}
    record["description_good_justification"] = None
    result, _ = progress(record, "passing", ["description_good"])
    assert result["answers"]["description_good_status"] == {"future": "value"}
    assert result["criteria"][0]["justification_present"] is True
    assert result["criteria"][0]["justification"] is None


def test_explicit_empty_filter_selects_no_saved_answers():
    result, _ = progress(level="passing", ids=[])
    assert result["answers"] == {} and result["criteria"] == []


@pytest.mark.parametrize(
    "level,ids",
    [
        (None, []),
        ("unknown", None),
        ("passing", ["not_known"]),
        ("passing", ["description_good", "description_good"]),
    ],
)
def test_invalid_catalog_scope_is_rejected_before_network(level, ids):
    http = FakeHTTP(fixture())
    with pytest.raises(DomainError):
        asyncio.run(BadgeAppClient(http).get_project_progress(123, level, ids))
    assert http.calls == []


@pytest.mark.parametrize("project_id", [True, "123", 1.5, 0, -1])
def test_invalid_progress_id_is_local_error(project_id):
    http = FakeHTTP(fixture())
    with pytest.raises(DomainError):
        asyncio.run(BadgeAppClient(http).get_project_progress(project_id))
    assert http.calls == []


@pytest.mark.parametrize(
    "data", [[], {"id": "123"}, {"id": True}, {"name": "Missing ID"}, {"id": 0}]
)
def test_malformed_single_project_is_an_upstream_error(data):
    with pytest.raises(DomainError) as caught:
        progress(data)
    assert caught.value.code == "upstream_invalid_response"


def test_project_id_mismatch_is_never_silently_accepted():
    with pytest.raises(DomainError) as caught:
        progress({"id": 456})
    assert caught.value.code == "project_mismatch"
    with pytest.raises(DomainError) as caught:
        find({"id": 456}, "123")
    assert caught.value.code == "project_mismatch"


@pytest.mark.parametrize("data", [{"projects": []}, [None], [{"id": "123"}]])
def test_malformed_search_shape_is_not_an_empty_success(data):
    with pytest.raises(DomainError) as caught:
        find(data)
    assert caught.value.code == "upstream_invalid_response"


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", 42),
        ("badge_percentage_0", True),
        ("badge_percentage_0", float("nan")),
        ("project_entry_license", 3),
    ],
)
def test_invalid_public_metadata_is_an_upstream_error(field, value):
    record = fixture()
    record[field] = value
    with pytest.raises(DomainError) as caught:
        progress(record)
    assert caught.value.code == "upstream_invalid_response"


def test_oversized_selected_answers_fail_with_filter_recovery():
    record = fixture()
    record["description_good_justification"] = "a" * DOCUMENT_LIMIT_BYTES
    with pytest.raises(DomainError) as caught:
        progress(record, "passing", ["description_good"])
    assert caught.value.code == "response_too_large"
    assert "criterion" in caught.value.recovery


def test_excessively_nested_public_answers_are_upstream_errors():
    value = "answer"
    for _ in range(65):
        value = [value]
    record = {"id": 123, "description_good_justification": value}
    with pytest.raises(DomainError) as caught:
        progress(record, "passing", ["description_good"])
    assert caught.value.code == "upstream_invalid_response"
    assert caught.value.__cause__.code == "invalid_document"


def test_large_json_integer_percentage_is_preserved_without_float_conversion():
    record = fixture()
    record["badge_percentage_0"] = 10**400
    result, _ = progress(record)
    assert result["summaries"][0]["upstream_percentage"] == 10**400


def test_repeated_reads_make_fresh_requests_and_do_not_mutate_source():
    record = fixture()
    http = FakeHTTP(record)
    client = BadgeAppClient(http)
    first = asyncio.run(client.get_project_progress(123, "passing", ["description_good"]))
    first["answers"]["description_good_status"] = "Unmet"
    second = asyncio.run(client.get_project_progress(123, "passing", ["description_good"]))
    assert second["answers"]["description_good_status"] == "Met"
    assert len(http.calls) == 2
    assert record == fixture()


def test_project_snapshot_preserves_missing_answers():
    record = {"id": 123, "description_good_status": "Met", "OSPS-AC-01.01_status": "Unmet"}
    http = FakeHTTP(record)
    snapshot, observation = asyncio.run(BadgeAppClient(http).get_project_snapshot(123))
    assert "description_good_justification" not in snapshot
    assert snapshot["OSPS-AC-01.01_status"] == "Unmet"
    assert "build_status" not in snapshot
    assert observation["fetched_at"] == STAMP
    assert http.calls == [("/projects/123.json", None)]
    result, _ = progress(record, "passing")
    assert "description_good_justification" not in result["answers"]


def test_project_snapshot_preserves_present_answer_values():
    http = FakeHTTP({"id": 123, "description_good_justification": {"unfamiliar": True}})
    snapshot, _ = asyncio.run(BadgeAppClient(http).get_project_snapshot(123))
    assert snapshot["description_good_justification"] == {"unfamiliar": True}


def test_project_snapshot_does_not_interpret_conflicting_answer_aliases():
    record = {"id": 123, "OSPS-AC-01.01_status": "Met", "osps_ac_01_01_status": "Unmet"}
    snapshot, _ = asyncio.run(BadgeAppClient(FakeHTTP(record)).get_project_snapshot(123))
    assert snapshot == record
