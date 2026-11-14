"""Reference-host behavior through public MCP results and real stdio subprocesses."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("reference_host", ROOT / "examples" / "host.py")
assert SPEC and SPEC.loader
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)


def result(payload: dict, *, error: bool = False, text_only: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        structured_content=None if text_only else payload,
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        is_error=error,
    )


def project(project_id: int = 123) -> dict:
    return {"project_id": project_id, "name": "Fixture", "repo_url": None, "homepage_url": None}


def search(candidates=(123,), *, page=1, next_page=None, complete=True) -> dict:
    return {
        "schema_version": 1,
        "page": page,
        "candidates": [{"project": project(value), "match_basis": "text"} for value in candidates],
        "next_page": next_page,
        "pagination_complete": complete,
    }


def progress(project_id=123) -> dict:
    return {
        "schema_version": 1,
        "project": project(project_id),
        "observation": {"fetched_at": "now"},
    }


class FakeClient:
    def __init__(self, respond):
        self.respond = respond
        self.calls = []

    async def call_tool(self, name, arguments, read_timeout_seconds):
        assert read_timeout_seconds > 30
        self.calls.append((name, arguments))
        return self.respond(name, arguments)


def make_host(client, answers):
    iterator = iter(answers)
    output = []
    return host.ReadHost(client, lambda _: next(iterator), output.append), output


def test_single_candidate_is_never_automatically_selected() -> None:
    client = FakeClient(lambda *_: result(search()))
    app, output = make_host(client, ["single", "c"])
    asyncio.run(app.find())
    assert app.project_id is None
    assert client.calls == [("find_project", {"query": "single", "page": 1})]
    assert not any("Selected registered" in line for line in output)


def test_remembered_id_is_verified_only_after_explicit_choice() -> None:
    client = FakeClient(
        lambda name, _: result(search()) if name == "find_project" else result(progress())
    )
    app, output = make_host(client, ["123", "123"])
    asyncio.run(app.find())
    assert app.project_id == 123
    assert client.calls[-1] == ("get_project_progress", {"project_id": 123})
    assert "Selected registered project 123." in output


def test_wrong_id_from_verification_does_not_become_selection() -> None:
    client = FakeClient(lambda *_: result(progress(456)))
    app, _ = make_host(client, [])
    with pytest.raises(host.HostError, match="different project"):
        asyncio.run(app.verify_selection(123))
    assert app.project_id is None


def test_registration_handoff_repeats_lookup_without_any_write() -> None:
    pages = iter([search(()), search()])
    client = FakeClient(
        lambda name, _: result(next(pages)) if name == "find_project" else result(progress())
    )
    app, output = make_host(client, ["missing", "r", "123"])
    asyncio.run(app.find())
    assert [name for name, _ in client.calls] == [
        "find_project",
        "find_project",
        "get_project_progress",
    ]
    assert any(host.REGISTRATION_URL in line for line in output)
    assert any("No draft or form work has begun" in line for line in output)


@pytest.mark.parametrize("next_page, expected", [(None, 2), (5, 5)])
def test_pagination_is_an_explicit_host_action(next_page, expected) -> None:
    client = FakeClient(
        lambda _, args: result(
            search(page=1, next_page=next_page, complete=False)
            if args["page"] == 1
            else search((), page=args["page"])
        )
    )
    app, output = make_host(client, ["pages", "n", "c"])
    asyncio.run(app.find())
    assert [args["page"] for _, args in client.calls] == [1, expected]
    assert app.project_id is None
    assert any("No further matches on this page" in line for line in output)
    assert not any(host.REGISTRATION_URL in line for line in output)
    assert not any("No registered project matched" in line for line in output)


def test_exhausted_later_page_allows_a_new_search() -> None:
    client = FakeClient(
        lambda _, args: result(
            search(page=1, complete=False) if args["page"] == 1 else search((), page=2)
        )
    )
    app, output = make_host(client, ["pages", "n", "s", "single", "c"])
    asyncio.run(app.find())
    assert client.calls == [
        ("find_project", {"query": "pages", "page": 1}),
        ("find_project", {"query": "pages", "page": 2}),
        ("find_project", {"query": "single", "page": 1}),
    ]
    assert not any(host.REGISTRATION_URL in line for line in output)
    assert app.project_id is None


def test_general_criteria_need_level_but_not_project_selection() -> None:
    client = FakeClient(
        lambda _, args: result(
            {"schema_version": 1, "criteria": [], "catalog": {"revision": "pin"}}
            if args
            else {"schema_version": 1, "levels": ["passing"]}
        )
    )
    app, output = make_host(client, ["passing", "description_good"])
    asyncio.run(app.choose_level())
    asyncio.run(app.criteria())
    assert app.project_id is None
    assert client.calls[-1] == (
        "get_criteria",
        {"level": "passing", "criterion_ids": ["description_good"]},
    )
    assert any("Official packaged criteria" in line for line in output)


def test_error_code_recovery_and_cooldown_are_visible_without_selection() -> None:
    failure = {
        "schema_version": 1,
        "error": {
            "code": "rate_limited",
            "message": "Try later.",
            "recovery": "Wait before retrying.",
            "retry_after_seconds": 90,
        },
    }
    client = FakeClient(lambda *_: result(failure, error=True))
    app, output = make_host(client, [])
    assert asyncio.run(app.verify_selection(123)) is False
    assert app.project_id is None
    assert "rate_limited: Try later." in output
    assert "Recovery: Wait before retrying." in output
    assert "Retry after at least 90 seconds." in output


def test_text_result_fallback_and_incompatible_envelopes() -> None:
    assert host.payload_from_result(result(progress(), text_only=True)) == progress()
    with pytest.raises(host.HostError, match="schema_version"):
        host.payload_from_result(result({"schema_version": 2}))
    with pytest.raises(host.HostError, match="incompatible"):
        host.payload_from_result(result({"schema_version": True}))


def test_missing_capability_or_schema_is_actionable() -> None:
    class MissingClient:
        async def list_tools(self):
            return SimpleNamespace(tools=[])

    with pytest.raises(host.HostError, match="Missing required read tools"):
        asyncio.run(host.discover(MissingClient()))


def test_configuration_has_no_shell_and_only_passes_storage_override(tmp_path: Path) -> None:
    command = shlex.join([sys.executable, "/path with spaces/server.py"])
    args = host.parser().parse_args(["--server-command", command, "--data-dir", str(tmp_path)])
    parameters = host.server_parameters(args)
    assert parameters.command == sys.executable
    assert parameters.args == ["/path with spaces/server.py"]
    assert parameters.env == {"BESTPRACTICES_DATA_DIR": str(tmp_path)}
    with pytest.raises(host.HostError, match="absolute"):
        host.server_parameters(host.parser().parse_args(["--data-dir", "relative"]))


def run_host(
    tmp_path: Path, transcript: str, *arguments: str, fixture: bool = True, env: dict | None = None
):
    command = [sys.executable, str(ROOT / "examples" / "host.py")]
    if fixture:
        server = shlex.join([sys.executable, str(ROOT / "tests" / "fixtures" / "read_server.py")])
        command += ["--server-command", server]
    command += ["--data-dir", str(tmp_path / "untouched"), *arguments]
    return subprocess.run(
        command,
        cwd=tmp_path,
        input=transcript,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=45,
    )


def test_real_server_discovery_is_noninteractive_and_creates_no_storage(tmp_path: Path) -> None:
    completed = run_host(tmp_path, "", "--discover", fixture=False)
    assert completed.returncode == 0, completed.stderr
    data = json.loads(completed.stdout)
    assert data["tools"] == sorted(
        host.READ_TOOLS | host.BADGE_TOOLS | host.DOCUMENT_TOOLS | host.STORAGE_TOOLS
    )
    assert data["protocol_version"] == "2026-07-28"
    assert not (tmp_path / "untouched").exists()


def test_real_mcp_host_read_workflow_and_switch_project(tmp_path: Path) -> None:
    transcript = (
        "progress\nfind\nambiguous\n456\nlevel\npassing\ncriteria\ndescription_good\n"
        "progress\nrefresh\nfind\n123\n123\nquit\n"
    )
    completed = run_host(tmp_path, transcript)
    assert completed.returncode == 0, completed.stderr
    output = completed.stdout
    assert "Find and explicitly select a registered project first." in output
    assert "HTTP Request:" not in completed.stderr
    assert "Selected registered project 456." in output
    assert "Selected registered project 123." in output
    assert "Official packaged criteria" in output
    assert "description_good" in output
    assert '"attribution"' in output and '"fetched_at"' in output
    assert '"Unmet"' in output
    assert not (tmp_path / "untouched").exists()


def test_real_mcp_host_registration_and_uncertain_pagination(tmp_path: Path) -> None:
    completed = run_host(tmp_path, "find\nmissing\ns\npages\nn\nc\nquit\n")
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.count(host.REGISTRATION_URL) == 1
    assert "No further matches on this page" in completed.stdout
    assert "More pages may exist" in completed.stdout
    assert "Selected registered project" not in completed.stdout
    assert not (tmp_path / "untouched").exists()


def test_plain_text_sdk_tool_error_remains_actionable() -> None:
    plain_error = SimpleNamespace(
        structured_content=None,
        content=[SimpleNamespace(type="text", text="Input validation failed: invalid level")],
        is_error=True,
    )
    client = FakeClient(lambda *_: plain_error)
    app, output = make_host(client, [])
    assert asyncio.run(app.call("get_criteria", {"level": "wrong"})) is None
    assert "tool_error: Input validation failed: invalid level" in output
    assert "Recovery: Inspect the request and retry." in output


def build_response(name, arguments):
    assert name == "build_draft"
    document = dict(arguments["draft"])
    for key, value in arguments["changes"].items():
        if value is None:
            document.pop(key, None)
        else:
            document[key] = value
    return result({"schema_version": 1, "draft": document, "issues": []})


def test_application_work_requires_confirmed_project() -> None:
    client = FakeClient(build_response)
    app, output = make_host(client, [])
    asyncio.run(app.new_document())
    asyncio.run(app.import_document())
    asyncio.run(app.prepare_url())
    assert client.calls == []
    assert len(output) == 3


def test_empty_document_is_explicit_and_validation_is_optional() -> None:
    client = FakeClient(lambda *_: result({"schema_version": 1, "artifact": None}))
    app, output = make_host(client, ["", ""])
    app.project_id, app.level, app.document = 123, "passing", {}
    asyncio.run(app.prepare_url())
    assert client.calls == [
        (
            "prepare_update_url",
            {"project_id": 123, "level": "passing", "draft": {}, "override_fields": []},
        )
    ]
    assert any("No artifact generated" in line for line in output)


def test_edit_remove_and_failed_mutation_preserve_document_contract() -> None:
    client = FakeClient(build_response)
    app, _ = make_host(client, ["name", "  Café Ω  ", "unfamiliar"])
    app.project_id = 123
    app.document = {"unfamiliar": {"keep": [None, True]}}
    app.artifacts["url"] = "old"
    asyncio.run(app.edit_document())
    assert app.document["name"] == "  Café Ω  "
    assert app.artifacts == {}
    asyncio.run(app.remove_fields())
    assert app.document == {"name": "  Café Ω  "}
    app.artifacts["url"] = "still current"
    client.respond = lambda *_: result({"schema_version": 1, "error": {}}, error=True)
    asyncio.run(app.replace_document(app.document, {"name": "not applied"}))
    assert app.document == {"name": "  Café Ω  "}
    assert app.artifacts == {"url": "still current"}


def test_scope_and_overrides_are_explicit_without_mutating_original() -> None:
    client = FakeClient(lambda *_: result({"schema_version": 1, "artifact": None}))
    app, _ = make_host(client, ["name", "name"])
    original = {"id": 123, "repo_url": "https://example.org/repo", "name": "New", "license": "MIT"}
    app.project_id, app.level, app.document = 123, "passing", original
    asyncio.run(app.prepare_url())
    arguments = client.calls[-1][1]
    assert arguments["draft"] == {key: original[key] for key in ("id", "repo_url", "name")}
    assert arguments["override_fields"] == ["name"]
    assert app.document is original and app.document["license"] == "MIT"


@pytest.mark.parametrize(
    "outcome",
    ["partial", "complete", "no_supplied_transferable_answers", "no_transferable_changes"],
)
def test_artifact_outcomes_and_stale_artifacts_are_visible(outcome) -> None:
    artifact = (
        {"url": "https://www.bestpractices.dev/example"}
        if outcome in {"complete", "partial"}
        else None
    )
    payload = {
        "schema_version": 1,
        "outcome": outcome,
        "artifact": artifact,
        "transfer": [
            {
                "field": "unknown",
                "disposition": "unsupported",
                "reason": "unknown_field",
                "override": False,
            }
        ],
        "no_artifact_reason": "reason",
    }
    client = FakeClient(lambda *_: result(payload))
    app, output = make_host(client, ["", ""])
    app.project_id, app.level, app.document = 123, "passing", {}
    app.artifacts["url"] = "stale"
    asyncio.run(app.prepare_url())
    assert any(outcome in line and "unsupported" in line for line in output)
    assert app.artifacts == ({"url": artifact["url"]} if artifact else {})


def test_import_rejects_oversize_duplicate_nonfinite_and_invalid_utf8(tmp_path) -> None:
    path = tmp_path / "input.json"
    for content in [b"x" * (host.MAX_IMPORT_BYTES + 1), b'{"x":1,"x":2}', b'{"x":NaN}', b'"\xff"']:
        path.write_bytes(content)
        with pytest.raises((ValueError, UnicodeError)):
            host.load_document(path)


def test_import_failure_leaves_existing_document_and_valid_import_calls_server(tmp_path) -> None:
    path = tmp_path / "document.json"
    path.write_text('{"name":"Café Ω"}', encoding="utf-8")
    client = FakeClient(build_response)
    app, output = make_host(client, [str(tmp_path / "absent"), str(path)])
    app.project_id, app.document = 123, {"name": "Old"}
    asyncio.run(app.import_document())
    assert app.document == {"name": "Old"}
    assert any("Import failed" in line for line in output)
    asyncio.run(app.import_document())
    assert app.document == {"name": "Café Ω"}
    assert client.calls == [("build_draft", {"draft": {"name": "Café Ω"}, "changes": {}})]


@pytest.mark.parametrize("kind", ["url", "script", "document"])
def test_exports_preserve_utf8_and_long_artifacts_exactly(tmp_path, kind) -> None:
    path = tmp_path / kind
    value = "Ω café 🍀\r\n" * 5000
    app, output = make_host(FakeClient(build_response), [kind, str(path), kind, str(path)])
    app.project_id, app.document = 123, {"name": value}
    app.artifacts[kind] = value
    asyncio.run(app.export_file())
    if kind == "document":
        assert json.loads(path.read_bytes()) == app.document
        assert "Ω".encode() in path.read_bytes()
    else:
        assert path.read_bytes() == value.encode("utf-8")
    first = path.read_bytes()
    asyncio.run(app.export_file())
    assert path.read_bytes() == first
    assert any("Export failed" in line for line in output)


def test_project_switch_discards_host_document_and_artifacts() -> None:
    app, _ = make_host(FakeClient(lambda *_: result(progress(456))), [])
    app.project_id, app.document = 123, {"id": 123}
    app.artifacts["script"] = "old script"
    asyncio.run(app.verify_selection(456))
    assert app.document is None and app.artifacts == {}


def test_stored_mode_starts_without_creating_a_draft(tmp_path) -> None:
    completed = run_host(tmp_path, "quit\n", "--mode", "stored")
    assert completed.returncode == 0, completed.stderr
    assert "Stored mode: project-keyed server files" in completed.stdout
    assert not (tmp_path / "untouched").exists()


def test_real_document_roundtrip_ignores_malformed_stored_file(tmp_path) -> None:
    stored = tmp_path / "untouched" / "projects" / "123" / ".bestpractices.json"
    stored.parent.mkdir(parents=True)
    stored.write_text("not valid JSON", encoding="utf-8")
    document = tmp_path / "source.json"
    document.write_text(
        json.dumps({"name": "Café Ω", "description_good_status": "Met"}), encoding="utf-8"
    )
    output = tmp_path / "export.json"
    transcript = (
        f"find\n123\n123\nlevel\npassing\nimport\n{document}\nvalidate\n"
        f"export\ndocument\n{output}\nnew\nurl\n\n\nquit\n"
    )
    completed = run_host(tmp_path, transcript)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_bytes()) == json.loads(document.read_bytes())
    assert '"kind": "explicit"' in completed.stdout
    assert '"outcome": "no_supplied_transferable_answers"' in completed.stdout
    assert stored.read_text(encoding="utf-8") == "not valid JSON"


def proposal_results(output: str) -> list[dict]:
    marker = "Proposal only: inspect included and excluded fields; nothing has been applied.\n"
    return [json.JSONDecoder().raw_decode(section)[0] for section in output.split(marker)[1:]]


def test_real_generation_without_validation_exports_exact_artifacts(tmp_path) -> None:
    explanation = "https://example.org/new — café Ω 🍀 " + "Ω" * 1000
    source = tmp_path / "document.json"
    source.write_text(json.dumps({"description_good_justification": explanation}), encoding="utf-8")
    url, override, script = [tmp_path / name for name in ("url.txt", "override.txt", "script.js")]
    transcript = (
        f"find\n123\n123\nlevel\npassing\nimport\n{source}\nurl\n\n\n"
        f"export\nurl\n{url}\nurl\n\ndescription_good_justification\n"
        f"export\nurl\n{override}\nscript\n\nexport\nscript\n{script}\nquit\n"
    )
    completed = run_host(tmp_path, transcript)
    assert completed.returncode == 0, completed.stderr
    proposals = proposal_results(completed.stdout)
    assert len(proposals) == 3
    assert proposals[0]["requested_overrides"] == []
    assert proposals[1]["requested_overrides"] == ["description_good_justification"]
    for path, payload, key in zip((url, override, script), proposals, ("url", "url", "javascript")):
        assert path.read_bytes() == payload["artifact"][key].encode("utf-8")
    assert explanation in unquote(override.read_text(encoding="utf-8"))
    assert not (tmp_path / "untouched").exists()
    assert "The report describes artifact contents." in completed.stdout
    assert "Review actual field values in BadgeApp before saving." in completed.stdout


@pytest.mark.parametrize("invalid", [b'{"name":"\\ud800"}', b'{"extra":[1e999]}'])
def test_real_session_survives_non_serializable_json_import(tmp_path, invalid) -> None:
    source = tmp_path / "invalid.json"
    source.write_bytes(invalid)
    preserved, updated = [tmp_path / name for name in ("preserved.json", "updated.json")]
    transcript = (
        f"find\n123\n123\nnew\nedit\nname\nOriginal\nimport\n{source}\n"
        f"export\ndocument\n{preserved}\nedit\nname\nUpdated\n"
        f"export\ndocument\n{updated}\nquit\n"
    )
    completed = run_host(tmp_path, transcript)
    assert completed.returncode == 0, completed.stderr
    assert "Import failed; document unchanged:" in completed.stdout
    assert json.loads(preserved.read_bytes()) == {"name": "Original"}
    assert json.loads(updated.read_bytes()) == {"name": "Updated"}
    assert not (tmp_path / "untouched").exists()


def test_stored_first_edit_is_a_small_patch_without_prior_read() -> None:
    client = FakeClient(lambda *_: result({"schema_version": 1, "location": "/synthetic/draft"}))
    app, output = make_host(client, ["name", "Stored name"])
    app.mode, app.project_id = "stored", 123
    asyncio.run(app.edit_document())
    assert client.calls == [
        ("update_draft", {"project_id": 123, "changes": {"name": "Stored name"}})
    ]
    assert app.document is None
    assert any("Stored draft updated" in line for line in output)


def test_stored_empty_initialize_and_remove_do_not_read_first() -> None:
    client = FakeClient(lambda *_: result({"schema_version": 1, "location": "/synthetic/draft"}))
    app, _ = make_host(client, ["unfamiliar"])
    app.mode, app.project_id = "stored", 123
    asyncio.run(app.initialize_stored())
    asyncio.run(app.remove_fields())
    assert client.calls == [
        ("update_draft", {"project_id": 123, "changes": {}}),
        ("update_draft", {"project_id": 123, "changes": {"unfamiliar": None}}),
    ]


def test_stored_validation_and_whole_artifacts_omit_draft() -> None:
    client = FakeClient(lambda *_: result({"schema_version": 1, "artifact": None}))
    app, _ = make_host(client, ["", "", ""])
    app.mode, app.project_id, app.level = "stored", 123, "passing"
    asyncio.run(app.validate_document())
    asyncio.run(app.prepare_url())
    asyncio.run(app.prepare_script())
    assert client.calls == [
        ("validate_draft", {"project_id": 123, "level": "passing"}),
        ("prepare_update_url", {"project_id": 123, "level": "passing", "override_fields": []}),
        ("prepare_update_script", {"project_id": 123, "level": "passing"}),
    ]


def test_stored_subset_reads_one_complete_snapshot_then_sends_explicit_document() -> None:
    original = {"id": 123, "repo_url": "https://example.org/repo", "name": "New", "license": "MIT"}
    client = FakeClient(
        lambda name, _: result(
            {"schema_version": 1, "draft": original, "location": "/synthetic/draft"}
            if name == "read_draft"
            else {"schema_version": 1, "artifact": None}
        )
    )
    app, _ = make_host(client, ["name", "name"])
    app.mode, app.project_id, app.level = "stored", 123, "passing"
    asyncio.run(app.prepare_url())
    assert client.calls == [
        ("read_draft", {"project_id": 123}),
        (
            "prepare_update_url",
            {
                "project_id": 123,
                "level": "passing",
                "draft": {key: original[key] for key in ("id", "repo_url", "name")},
                "override_fields": ["name"],
            },
        ),
    ]
    assert app.document is None and original["license"] == "MIT"


def test_stored_export_reads_complete_document_without_interpreting_unknown_values(
    tmp_path,
) -> None:
    document = {"name": "Café", "unfamiliar": {"nested": [True, None, 42]}}
    client = FakeClient(
        lambda *_: result({"schema_version": 1, "draft": document, "location": "/synthetic/draft"})
    )
    target = tmp_path / "export.json"
    app, _ = make_host(client, ["document", str(target)])
    app.mode, app.project_id = "stored", 123
    asyncio.run(app.export_file())
    assert client.calls == [("read_draft", {"project_id": 123})]
    assert json.loads(target.read_bytes()) == document


@pytest.mark.parametrize(
    "failure", [TimeoutError(), ConnectionError("lost"), host.MCPError(code=-32603, message="lost")]
)
def test_uncertain_write_is_not_retried_and_suggests_read(failure) -> None:
    def respond(*_):
        raise failure

    client = FakeClient(respond)
    app, output = make_host(client, [])
    app.mode, app.project_id = "stored", 123
    app.artifacts["url"] = "stale"
    asyncio.run(app.patch_document({"name": "Maybe applied"}))
    assert len(client.calls) == 1
    assert app.artifacts == {}
    assert any("Write outcome uncertain; no retry was attempted" in line for line in output)
    assert any("Use read to inspect" in line for line in output)
    assert not any("Stored draft updated" in line for line in output)


def test_stored_known_rejection_preserves_successful_state() -> None:
    client = FakeClient(
        lambda *_: result({"schema_version": 1, "error": {"code": "invalid_field"}}, error=True)
    )
    app, output = make_host(client, [])
    app.mode, app.project_id = "stored", 123
    app.artifacts["url"] = "previous successful artifact"
    asyncio.run(app.patch_document({"description_good_status": "invalid"}))
    assert app.artifacts == {"url": "previous successful artifact"}
    assert not any("Stored draft updated" in line for line in output)


@pytest.mark.parametrize(
    "response",
    [
        result({"schema_version": 1, "error": {"code": "internal_error"}}, error=True),
        result({"schema_version": 1, "error": {"code": "unknown_future_error"}}, error=True),
        result({"schema_version": 1, "error": []}, error=True),
        result({"schema_version": 1, "error": {"code": []}}, error=True),
        result({"schema_version": 2}, error=True),
        result({"schema_version": 2}),
        SimpleNamespace(
            structured_content=None,
            content=[SimpleNamespace(type="text", text="Server execution failed")],
            is_error=True,
        ),
    ],
)
def test_uncertain_update_error_results_clear_artifacts_and_keep_read_available(response) -> None:
    client = FakeClient(lambda *_: response)
    app, output = make_host(client, [])
    app.mode, app.project_id = "stored", 123
    app.artifacts["url"] = "stale URL"
    app.artifacts["script"] = "stale script"
    asyncio.run(app.patch_document({"name": "Possibly committed"}))
    assert len(client.calls) == 1
    assert app.artifacts == {}
    assert any("Write outcome uncertain; no retry was attempted" in line for line in output)
    assert any("Use read to inspect" in line for line in output)
    assert not any("Inspect the request and retry" in line for line in output)
    assert not any("Stored draft updated" in line for line in output)
    client.respond = lambda *_: result(
        {
            "schema_version": 1,
            "draft": {"name": "Possibly committed"},
            "location": "/synthetic/draft",
        }
    )
    asyncio.run(app.show_document())
    assert client.calls[-1] == ("read_draft", {"project_id": 123})


def test_real_stored_workflow_restart_isolation_and_rejected_patch(tmp_path) -> None:
    before, rejected, resumed, other, returned = [
        tmp_path / name
        for name in ("before.json", "rejected.json", "resumed.json", "other.json", "returned.json")
    ]
    first = run_host(
        tmp_path,
        "find\n123\n123\nedit\nname\nFirst stored draft\nlevel\npassing\n"
        "edit\ndescription_good_status\nMet\n"
        f"export\ndocument\n{before}\nedit\ndescription_good_status\ninvalid\n"
        f"export\ndocument\n{rejected}\nurl\n\n\nscript\n\nvalidate\nquit\n",
        "--mode",
        "stored",
    )
    assert first.returncode == 0, first.stderr
    expected = {"name": "First stored draft", "description_good_status": "Met"}
    assert json.loads(before.read_bytes()) == json.loads(rejected.read_bytes()) == expected
    assert "invalid_field" in first.stdout
    assert '"created": true' in first.stdout
    assert all(item["draft_source"]["kind"] == "stored" for item in proposal_results(first.stdout))
    second = run_host(
        tmp_path,
        f"find\n123\n123\nread\nexport\ndocument\n{resumed}\n"
        "find\nambiguous\n456\nread\nedit\nname\nSecond project\n"
        f"export\ndocument\n{other}\nfind\n123\n123\nexport\ndocument\n{returned}\nquit\n",
        "--mode",
        "stored",
    )
    assert second.returncode == 0, second.stderr
    assert "draft_not_found" in second.stdout
    assert json.loads(resumed.read_bytes()) == json.loads(returned.read_bytes()) == expected
    assert json.loads(other.read_bytes()) == {"name": "Second project"}


def test_real_stored_subset_is_explicit_and_does_not_change_file(tmp_path) -> None:
    exported = tmp_path / "full.json"
    completed = run_host(
        tmp_path,
        "find\n123\n123\nedit\nname\nSelected\nedit\nlicense\nMIT\nlevel\npassing\n"
        f"url\nname\nname\nexport\ndocument\n{exported}\nquit\n",
        "--mode",
        "stored",
    )
    assert completed.returncode == 0, completed.stderr
    proposal = proposal_results(completed.stdout)[0]
    assert proposal["draft_source"]["kind"] == "explicit"
    assert {row["field"] for row in proposal["transfer"]} == {"name"}
    assert json.loads(exported.read_bytes()) == {"name": "Selected", "license": "MIT"}


def test_piped_host_preserves_unicode_despite_legacy_stream_encoding(tmp_path):
    completed = run_host(
        tmp_path,
        "find\n123\n123\nnew\nedit\nname\nCafé Ω ✨\nshow\nquit\n",
        env={**os.environ, "PYTHONIOENCODING": "ascii"},
    )
    assert completed.returncode == 0, completed.stderr
    assert "Café Ω ✨" in completed.stdout
    assert "UnicodeEncodeError" not in completed.stderr
