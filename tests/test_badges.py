"""Badge SVG artifacts and embedding links, from synthetic SVG text.

HTTP content validation has separate transport tests; these test domain mapping.
"""

import asyncio
import copy
from types import SimpleNamespace

import pytest

from best_practices_mcp.badgeapp import ORIGIN
from best_practices_mcp.badges import get_project_badge_svg
from best_practices_mcp.contracts import validate_output
from best_practices_mcp.errors import DomainError

FETCHED_AT = "2026-11-14T12:00:00+00:00"
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

    async def get_svg(self, path):
        return self.result("svg", path)


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


@pytest.mark.parametrize("project_id", [True, 0, -1, "123", None])
def test_invalid_ids_never_request_network(project_id):
    http = FakeHTTP(SVG)
    with pytest.raises(DomainError) as caught:
        asyncio.run(get_project_badge_svg(http, project_id, "best_practices"))
    assert caught.value.code == "invalid_field"
    assert http.calls == []


@pytest.mark.parametrize("family", ["passing", "baseline-1", "", None, [], True])
def test_invalid_families_never_request_network(family):
    http = FakeHTTP(SVG)
    with pytest.raises(DomainError) as caught:
        asyncio.run(get_project_badge_svg(http, 123, family))
    assert caught.value.code == "invalid_field"
    assert http.calls == []


@pytest.mark.parametrize("code", ["project_not_found", "rate_limited", "upstream_unavailable"])
def test_transport_failures_propagate_without_fallback_requests(code):
    failure = DomainError(code, "Synthetic failure.")
    http = FakeHTTP(None, failure)
    with pytest.raises(DomainError) as caught:
        asyncio.run(get_project_badge_svg(http, 123, "baseline"))
    assert caught.value is failure
    assert len(http.calls) == 1
