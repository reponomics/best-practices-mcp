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
from best_practices_mcp.criteria import criterion_definitions
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


def progress(data=None, level="passing", ids=None, project_id=123, **filters):
    """Read saved answers for a level from a synthetic record."""
    http = FakeHTTP(fixture() if data is None else data)
    client = BadgeAppClient(http)
    result = asyncio.run(client.get_project_answers(project_id, level, ids, **filters))
    validate_output("get_project_answers", result)
    return result, http


def status(data=None, project_id=123):
    http = FakeHTTP(fixture() if data is None else data)
    result = asyncio.run(BadgeAppClient(http).get_project_status(project_id))
    validate_output("get_project_status", result)
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
        asyncio.run(BadgeAppClient(FakeHTTP(None, error=error)).get_project_status(123))
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


def test_status_copies_level_figures_and_times_from_one_record_read():
    record = fixture() | {
        "updated_at": "2026-11-17T01:16:53.248Z",
        "achieved_passing_at": "2026-08-29T16:42:55.187Z",
        "lost_passing_at": None,
        "achieved_baseline_1_at": "2026-09-03T21:51:25.521Z",
        "lost_baseline_1_at": "2026-10-01T00:00:00.000Z",
    }
    result, http = status(record)
    assert http.calls == [("/projects/123.json", None)]
    assert result["schema_version"] == 1
    assert result["project"]["name"] == "Example Project"
    assert result["badge_level"] == "in_progress"
    assert result["updated_at"] == "2026-11-17T01:16:53.248Z"
    assert [item["level"] for item in result["levels"]] == [
        "passing",
        "silver",
        "gold",
        "baseline-1",
        "baseline-2",
        "baseline-3",
    ]
    assert [item["percentage"] for item in result["levels"]] == [42, 10.5, 0, 75, 25, 5]
    assert result["levels"][0] == {
        "level": "passing",
        "percentage": 42,
        "achieved_at": "2026-08-29T16:42:55.187Z",
        "lost_at": None,
    }
    assert result["levels"][3]["lost_at"] == "2026-10-01T00:00:00.000Z"
    assert result["levels"][1]["achieved_at"] is None
    assert not {"answers", "tiered_percentage", "catalog"} & set(result)
    assert result["observation"]["attribution"] == fixture()["project_entry_attribution"]
    assert result["observation"]["license"] == "CC-BY-3.0+"


def test_status_reports_missing_fields_as_null_without_inventing_values():
    result, _ = status({"id": 123})
    assert result["badge_level"] is None and result["updated_at"] is None
    assert result["levels"] == [
        {"level": level, "percentage": None, "achieved_at": None, "lost_at": None}
        for level in ("passing", "silver", "gold", "baseline-1", "baseline-2", "baseline-3")
    ]
    assert result["project"] == {
        "project_id": 123,
        "name": None,
        "repo_url": None,
        "homepage_url": None,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("badge_percentage_1", "12"),
        ("badge_percentage_baseline_2", True),
        ("badge_percentage_0", float("inf")),
        ("badge_level", 3),
        ("updated_at", 1731800000),
        ("achieved_gold_at", ["2026"]),
        ("lost_baseline_3_at", {"at": None}),
    ],
)
def test_status_rejects_fields_of_an_unexpected_type(field, value):
    with pytest.raises(DomainError) as caught:
        status(fixture() | {field: value})
    assert caught.value.code == "upstream_invalid_response"
    assert caught.value.details == {"field": field}


def test_status_is_for_the_requested_project_only():
    with pytest.raises(DomainError) as caught:
        status(fixture() | {"id": 456})
    assert caught.value.code == "project_mismatch"


def test_answers_carry_no_status_figures():
    result, http = progress()
    assert http.calls == [("/projects/123.json", None)]
    assert result["schema_version"] == 1 and result["level"] == "passing"
    assert not {"summaries", "summary_metadata", "criterion_ids", "levels"} & set(result)
    assert result["observation"]["attribution"] == fixture()["project_entry_attribution"]


def test_level_filter_preserves_actual_justification_and_missing_fields():
    result, _ = progress(level="passing", ids=["description_good", "contribution"])
    assert set(result["answers"]) == {
        "contribution_status",
        "description_good_status",
        "description_good_justification",
    }
    assert (
        result["answers"]["description_good_justification"]
        == fixture()["description_good_justification"]
    )
    assert "contribution_justification" not in result["answers"]
    assert result["answers"]["contribution_status"] == "?"
    assert result["level_criterion_count"] == 67


def test_missing_status_is_not_synthesized_and_missing_metadata_stays_null():
    result, _ = progress({"id": 123}, "passing", ["description_good"])
    assert result["answers"] == {}
    assert result["statuses_not_retrieved"] == ["description_good"]
    assert result["project"]["name"] is None


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
    assert result["answers"] == {
        "description_good_status": {"future": "value"},
        "description_good_justification": None,
    }


def complete_record(level: str, status: str = "?") -> dict:
    """A record shaped like BadgeApp's: every criterion of the level has a status."""
    fields = {f"{criterion_id}_status": status for criterion_id in level_ids(level)}
    return fixture() | fields


def level_ids(level: str) -> list[str]:
    return [criterion["criterion_id"] for criterion in criterion_definitions(level)]


def answered(result: dict) -> list[str]:
    """Criteria in a result, read from its status fields."""
    suffix = "_status"
    return [field.removesuffix(suffix) for field in result["answers"] if field.endswith(suffix)]


def test_status_filter_selects_criteria_by_saved_status():
    record = complete_record("passing") | {
        "description_good_status": "Met",
        "interact_status": "Unmet",
        "build_status": "N/A",
    }
    met, _ = progress(record, "passing", statuses=["Met"])
    assert list(met["answers"]) == ["description_good_status", "description_good_justification"]
    remaining, _ = progress(record, "passing", statuses=["Unmet", "?"])
    assert len(answered(remaining)) == 65
    assert not {"description_good", "build"} & set(answered(remaining))
    assert remaining["answers"]["interact_status"] == "Unmet"
    assert remaining["answers"]["contribution_status"] == "?"
    assert remaining["level_criterion_count"] == 67
    assert remaining["statuses_not_retrieved"] == []
    none, _ = progress(record, "passing", statuses=[])
    assert none["answers"] == {}


def test_status_filter_combines_with_criterion_ids():
    ids = ["contribution", "description_good", "interact"]
    record = complete_record("passing") | {"description_good_status": "Met"}
    result, _ = progress(record, "passing", ids, statuses=["?"])
    assert set(answered(result)) == {"contribution", "interact"}


def test_answers_and_missing_statuses_keep_the_catalogs_order(arbitrary_catalog):
    in_catalog = [identifier for level, identifier, _ in arbitrary_catalog if level == "passing"]
    saved, absent = in_catalog[1::2], in_catalog[0::2]
    record = fixture() | {f"{identifier}_status": "Met" for identifier in sorted(saved)}
    result, _ = progress(record, "passing")
    assert answered(result) == saved
    assert result["statuses_not_retrieved"] == absent
    named, _ = progress(record, "passing", sorted(in_catalog, reverse=True))
    assert answered(named) == saved


def test_a_status_missing_from_the_record_is_reported_and_never_matched():
    # The fixture record carries statuses for two passing criteria only.
    unfiltered, _ = progress(level="passing")
    retrieved = {"contribution", "description_good"}
    missing = [identifier for identifier in level_ids("passing") if identifier not in retrieved]
    assert unfiltered["statuses_not_retrieved"] == missing
    assert set(unfiltered["answers"]) == {
        "contribution_status",
        "description_good_status",
        "description_good_justification",
    }
    every = ["Met", "Unmet", "N/A", "?"]
    filtered, _ = progress(level="passing", statuses=every)
    assert set(answered(filtered)) == retrieved
    assert filtered["statuses_not_retrieved"] == missing
    selected, _ = progress(level="passing", ids=["interact", "contribution"], statuses=["?"])
    assert answered(selected) == ["contribution"]
    assert selected["statuses_not_retrieved"] == ["interact"]


@pytest.mark.parametrize("value", ["met", "absent", None, 1, {"future": "value"}])
def test_unrecognized_saved_statuses_match_no_status_filter(value):
    record = fixture() | {"description_good_status": value}
    every = ["Met", "Unmet", "N/A", "?"]
    filtered, _ = progress(record, "passing", ["description_good"], statuses=every)
    assert filtered["answers"] == {}
    assert filtered["statuses_not_retrieved"] == []
    unfiltered, _ = progress(record, "passing", ["description_good"])
    assert unfiltered["answers"]["description_good_status"] == value


def test_justifications_can_be_left_out():
    result, _ = progress(level="passing", include_justifications=False)
    assert result["answers"] == {"contribution_status": "?", "description_good_status": "Met"}
    baseline, _ = progress(level="baseline-1", ids=["osps_ac_01_01"], include_justifications=False)
    assert baseline["answers"] == {"osps_ac_01_01_status": "Met"}


def test_status_filter_requires_a_level_before_network():
    http = FakeHTTP(fixture())
    with pytest.raises(DomainError) as caught:
        asyncio.run(BadgeAppClient(http).get_project_answers(123, None, statuses=["Met"]))
    assert caught.value.code == "invalid_level"
    assert http.calls == []


def test_explicit_empty_filter_selects_no_saved_answers():
    result, _ = progress(level="passing", ids=[])
    assert result["answers"] == {} and result["statuses_not_retrieved"] == []


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
        asyncio.run(BadgeAppClient(http).get_project_answers(123, level, ids))
    assert http.calls == []


@pytest.mark.parametrize("project_id", [True, "123", 1.5, 0, -1])
def test_invalid_progress_id_is_local_error(project_id):
    http = FakeHTTP(fixture())
    with pytest.raises(DomainError):
        asyncio.run(BadgeAppClient(http).get_project_status(project_id))
    with pytest.raises(DomainError):
        asyncio.run(BadgeAppClient(http).get_project_answers(project_id, "passing"))
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
        ("project_entry_license", 3),
    ],
)
@pytest.mark.parametrize("read", [progress, status])
def test_invalid_public_metadata_is_an_upstream_error(read, field, value):
    record = fixture()
    record[field] = value
    with pytest.raises(DomainError) as caught:
        read(record)
    assert caught.value.code == "upstream_invalid_response"


def test_oversized_selected_answers_fail_with_filter_recovery():
    record = fixture()
    record["description_good_justification"] = "a" * DOCUMENT_LIMIT_BYTES
    with pytest.raises(DomainError) as caught:
        progress(record, "passing", ["description_good"])
    assert caught.value.code == "response_too_large"
    assert "criterion" in caught.value.recovery


def test_excessively_nested_public_answers_are_upstream_errors():
    value: object = "answer"
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
    result, _ = status(record)
    assert result["levels"][0]["percentage"] == 10**400


def test_repeated_reads_make_fresh_requests_and_do_not_mutate_source():
    record = fixture()
    http = FakeHTTP(record)
    client = BadgeAppClient(http)
    first = asyncio.run(client.get_project_answers(123, "passing", ["description_good"]))
    first["answers"]["description_good_status"] = "Unmet"
    second = asyncio.run(client.get_project_answers(123, "passing", ["description_good"]))
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
