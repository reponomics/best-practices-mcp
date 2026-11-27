"""Keep test subprocesses independent of a calling Git hook's repository."""

import json
import subprocess

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolate_git_environment():
    # Git's documented list includes worktree, index, object and config overrides.
    # https://git-scm.com/docs/githooks#_description
    variables = subprocess.check_output(
        ["git", "rev-parse", "--local-env-vars"], text=True, timeout=10
    ).splitlines()
    with pytest.MonkeyPatch.context() as environment:
        for name in variables:
            environment.delenv(name, raising=False)
        yield


# Made-up criteria as (level, criterion_id, category), in an order that is neither sorted
# nor grouped by category, so a result that reorders or regroups them is detectable.
ARBITRARY_CRITERIA = (
    ("passing", "quartz", "Stone"),
    ("passing", "amber", "Resin"),
    ("passing", "zinc", "Metal"),
    ("passing", "basalt", "Stone"),
    ("passing", "onyx", "Metal"),
    ("silver", "yew", "Wood"),
    ("silver", "ash", "Wood"),
)


@pytest.fixture
def arbitrary_catalog(tmp_path, monkeypatch):
    """Package a made-up catalog in place of the real one, and return its criteria.

    Tests of result order use it so that they state what the server does with whatever
    order the catalog has, independently of the criteria upstream publishes.
    """
    from best_practices_mcp import criteria as criteria_module

    records: list[dict[str, object]] = [
        {
            "criterion_id": criterion_id,
            "level": level,
            "description": f"Describes {criterion_id}.",
            "details": None,
            "category": category,
            "requirement": "MUST",
            "status_field": f"{criterion_id}_status",
            "justification_field": f"{criterion_id}_justification",
            "aliases": [],
            "na_allowed": False,
            "na_justification_required": False,
            "met_justification_required": False,
            "met_url_required": False,
        }
        for level, criterion_id, category in ARBITRARY_CRITERIA
    ]
    data = tmp_path / "packaged" / "data"
    data.mkdir(parents=True)
    catalog = {"format_version": 2, "levels": ["passing", "silver"], "criteria": records}
    (data / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    source = {
        "repository": "https://example.test/criteria",
        "revision": "0" * 40,
        "generated_at": "2000-01-01T00:00:00Z",
    }
    (data / "provenance.json").write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(criteria_module, "files", lambda package: tmp_path / "packaged")
    criteria_module._catalog.cache_clear()
    yield ARBITRARY_CRITERIA
    criteria_module._catalog.cache_clear()
