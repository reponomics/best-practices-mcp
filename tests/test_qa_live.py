"""The opt-in live QA script: role selection, and a full run against the fixture server."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SERVER = [sys.executable, str(ROOT / "tests" / "fixtures" / "read_server.py")]
SPEC = importlib.util.spec_from_file_location("qa_live", ROOT / "scripts" / "qa_live.py")
assert SPEC and SPEC.loader
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


def criterion(name: str) -> dict:
    return {
        "criterion_id": name,
        "status_field": f"{name}_status",
        "justification_field": f"{name}_justification",
    }


def saved(statuses: dict, justified: str = "") -> dict:
    answers = {f"{name}_status": status for name, status in statuses.items()}
    return answers | {f"{name}_justification": "Saved text." for name in justified.split()}


def names(assigned: dict) -> dict:
    return {use: chosen and chosen["criterion_id"] for use, chosen in assigned.items()}


def test_roles_take_distinct_criteria_that_meet_their_conditions() -> None:
    criteria = [criterion(name) for name in "abcdefgh"]
    statuses = dict.fromkeys("abcde", "Met") | {"f": "N/A", "g": "?", "h": "Unmet"}
    answers = saved(statuses, justified="a b c d f")
    roles, resets = qa.select_roles(answers, criteria)
    assert names(roles) == {"A": "a", "B": "b", "C": "g", "D": "c", "E": "d", "F": "f"}
    assert names(resets) == {"with a justification": "a", "without a justification": "e"}

    changes, overrides, added = qa.proposal(roles, answers, "QA")
    assert changes == {
        "a_status": "Unmet",
        "a_justification": "QA",
        "b_status": "Met",
        "b_justification": "QA",
        "g_status": "Unmet",
        "g_justification": "QA",
        "c_justification": "QA",
        "d_justification": "",
        "f_status": "N/A",
        "f_justification": "Saved text.",
    }
    assert (overrides, added) == (["a_justification", "b_status", "d_justification"], ["a_status"])


@pytest.mark.parametrize(
    ("statuses", "justified", "assigned"),
    [
        ({"a": "Met", "b": "Unmet"}, "a b", {"A": "a", "B": "b"}),
        ({"a": "?", "b": "?"}, "", {"C": "a"}),
        ({"a": "?", "b": "Met"}, "a", {}),
    ],
    ids=["completed", "not started", "no usable condition"],
)
def test_roles_without_a_matching_criterion_are_left_unassigned(statuses, justified, assigned):
    answers = saved(statuses, justified)
    roles, _ = qa.select_roles(answers, [criterion(name) for name in statuses])
    assert names(roles) == dict.fromkeys("ABCDEF") | assigned
    changes, _, _ = qa.proposal(roles, answers, "QA")
    assert bool(changes) == bool(assigned)


def results(report: dict) -> dict:
    return {check["check"]: check["result"] for check in report["checks"]}


def test_a_started_application_passes_every_check_and_exercises_every_role() -> None:
    report = asyncio.run(qa.qualify(FIXTURE_SERVER, 789, "passing"))
    assert set(results(report).values()) == {"passed"}
    assert all(report["roles"].values()) and all(report["resets"].values())
    assert [entry["name"] for entry in report["urls"]] == [
        "URL A",
        "URL B",
        "Chooser URL",
        "Reset URL, named overrides",
        "Reset URL, override all",
        "Reset URL, no override",
        "Control URL",
    ]
    text = qa.render(report)
    assert "# Live QA: project 789 (Fixture Gamma), passing" in text
    assert all(f"<{entry['url']}>" in text for entry in report["urls"])


def test_a_record_with_missing_statuses_fails_and_reports_unexercised_roles() -> None:
    report = asyncio.run(qa.qualify(FIXTURE_SERVER, 123, "passing"))
    outcome = results(report)
    assert outcome["get_project_answers returns a status for every criterion of the level"] == (
        "failed"
    )
    assert outcome["role C (blank pair)"] == "unexercised"
    assert report["roles"]["A"]["criterion_id"] == "description_good"
    assert "| C: blank pair | none | | |" in qa.render(report)


def test_an_unknown_project_ends_the_run_with_a_failed_check() -> None:
    report = asyncio.run(qa.qualify(FIXTURE_SERVER, 999, "passing"))
    assert results(report)["the run completed"] == "failed"
    assert not report["urls"]


@pytest.mark.parametrize(("result", "status"), [("passed", 0), ("failed", 1)])
def test_main_writes_the_evidence_and_exits_nonzero_on_failure(
    monkeypatch, tmp_path, capsys, result, status
):
    report = {
        "project": {"project_id": 1, "name": "Example"},
        "level": "gold",
        "server": "bestpractices-mcp 0",
        "protocol": "2026-07-28",
        "run_at": "2026-11-18T00:00:00+00:00",
        "roles": {},
        "resets": {},
        "checks": [{"check": "example", "result": result, "detail": ""}],
        "urls": [],
        "calls": [{"tool": "get_criteria", "arguments": {}}],
    }

    async def qualify(server, project_id, level):
        assert (server[1:], project_id, level) == (["-m", "best_practices_mcp"], 1, "gold")
        return report

    monkeypatch.setattr(qa, "qualify", qualify)
    arguments = ["--project-id", "1", "--level", "gold", "--output-dir", str(tmp_path / "qa")]
    monkeypatch.setattr(sys, "argv", ["qa_live.py", *arguments])
    if status:
        with pytest.raises(SystemExit) as exit_info:
            qa.main()
        assert exit_info.value.code == status
    else:
        qa.main()
    printed = capsys.readouterr().out
    assert printed == (tmp_path / "qa" / "report.md").read_text(encoding="utf-8")
    assert (
        json.loads((tmp_path / "qa" / "calls.json").read_text(encoding="utf-8"))
        == (report["calls"])
    )
