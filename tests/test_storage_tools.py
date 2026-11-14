"""Public paths: actual MCP storage, explicit precedence and snapshot provenance."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from mcp import Client, StdioServerParameters

from best_practices_mcp.contracts import output_schema
from best_practices_mcp.server import IMPLEMENTED_TOOLS, create_server

FIXTURE = Path(__file__).parent / "fixtures/read_server.py"


async def call(client, name, **arguments):
    result = await client.call_tool(name, arguments)
    payload = result.structured_content
    Draft202012Validator(output_schema(name)).validate(payload)
    assert json.loads(result.content[0].text) == payload
    return result


def test_stored_workflow_restart_explicit_precedence_and_stable_discovery(tmp_path):
    root = tmp_path / "drafts"
    path = root / "projects/123/.bestpractices.json"
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(FIXTURE.resolve())],
        env={"BESTPRACTICES_DATA_DIR": str(root)},
    )

    async def exercise():
        async with asyncio.timeout(30):
            async with Client(params) as client:
                listed = (await client.list_tools()).tools
                assert len(listed) == 11
                assert [t.name for t in listed] == sorted(IMPLEMENTED_TOOLS)
                mutation = next(t for t in listed if t.name == "update_draft")
                assert not mutation.annotations.read_only_hint
                assert mutation.annotations.destructive_hint
                assert mutation.annotations.idempotent_hint
                assert not mutation.annotations.open_world_hint
                missing = await call(client, "read_draft", project_id=123)
                assert missing.structured_content["error"]["code"] == "draft_not_found"
                assert not root.exists()
                first = await call(client, "update_draft", project_id=123, changes={})
                assert first.structured_content["created"] is True
                await call(
                    client,
                    "update_draft",
                    project_id=123,
                    changes={"description_good_justification": "Stored ✨ proposal"},
                )
                read = (await call(client, "read_draft", project_id=123)).structured_content
                assert read["draft"] == {"description_good_justification": "Stored ✨ proposal"}
                assert read["identity"]["association"] == "storage_key"
                assert read["location"] == str(path.resolve())
                for name in ("validate_draft", "prepare_update_url", "prepare_update_script"):
                    result = await call(client, name, project_id=123, level="passing")
                    assert not result.is_error
                    assert result.structured_content["draft_source"] == {
                        "kind": "stored",
                        "location": str(path.resolve()),
                    }
                    assert result.structured_content["identity"]["association"] == "storage_key"
                    empty = await call(client, name, project_id=123, level="passing", draft={})
                    assert not empty.is_error
                    assert empty.structured_content["draft_source"] == {
                        "kind": "explicit",
                        "location": None,
                    }
                    if name != "validate_draft":
                        assert (
                            empty.structured_content["outcome"]
                            == "no_supplied_transferable_answers"
                        )
                await call(client, "update_draft", project_id=456, changes={"name": "Other"})
                invalid = await call(client, "update_draft", project_id=123, changes={"name": 3})
                assert invalid.structured_content["error"]["code"] == "invalid_field"
                assert (await client.list_tools()).tools == listed
            async with Client(params) as client:
                resumed = (await call(client, "read_draft", project_id=123)).structured_content
                assert resumed["draft"] == read["draft"]
                assert (await call(client, "read_draft", project_id=456)).structured_content[
                    "draft"
                ] == {"name": "Other"}
                # Explicit input bypasses malformed stored bytes, not merely a missing file.
                path.write_text('{"name":')
                for name in ("validate_draft", "prepare_update_url", "prepare_update_script"):
                    result = await call(client, name, project_id=123, level="passing", draft={})
                    assert not result.is_error
                    stored = await call(client, name, project_id=123, level="passing")
                    assert stored.structured_content["error"]["code"] == "invalid_document"
                null = await client.call_tool(
                    "validate_draft", {"project_id": 123, "level": "passing", "draft": None}
                )
                assert null.is_error
                assert path.read_text(encoding="utf-8") == '{"name":'

    asyncio.run(exercise())


def test_offline_storage_validation_and_identity_before_network(tmp_path):
    def deny_http():
        raise AssertionError("HTTP accessed")

    server = create_server(data_root=tmp_path, http_factory=deny_http)

    async def exercise():
        assert not (
            await server.call_tool(
                "update_draft", {"project_id": 123, "changes": {"description_good_status": "N/A"}}
            )
        ).is_error
        result = await server.call_tool("validate_draft", {"project_id": 123, "level": "passing"})
        assert not result.is_error and result.structured_content["findings"]
        path = tmp_path / "projects/123/.bestpractices.json"
        path.write_text('{"id":456,"name":"wrong source"}')
        for name, arguments in (
            ("read_draft", {"project_id": 123}),
            ("update_draft", {"project_id": 123, "changes": {"id": None}}),
            ("prepare_update_url", {"project_id": 123, "level": "passing"}),
            ("prepare_update_script", {"project_id": 123, "level": "passing"}),
        ):
            result = await server.call_tool(name, arguments)
            assert result.structured_content["error"]["code"] == "project_mismatch"
        assert json.loads(path.read_text(encoding="utf-8"))["id"] == 456

    asyncio.run(exercise())


def test_generator_uses_one_stored_snapshot_during_concurrent_update(tmp_path):
    async def exercise():
        server = create_server(data_root=tmp_path)
        started, release = asyncio.Event(), asyncio.Event()

        class PublicRead:
            async def get_project_snapshot(self, project_id):
                started.set()
                await release.wait()
                return {"id": project_id, "repo_url": "https://example.org/repo"}, {
                    "project_id": project_id,
                    "source_url": "https://www.bestpractices.dev/projects/123.json",
                    "fetched_at": "2026-11-09T00:00:00Z",
                    "attribution": None,
                    "license": None,
                }

        context = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=PublicRead()))
        await server.storage.update(123, {"name": "First snapshot"})
        pending = asyncio.create_task(
            server.call_tool("prepare_update_url", {"project_id": 123, "level": "passing"}, context)
        )
        await asyncio.wait_for(started.wait(), 5)
        await server.storage.update(123, {"name": "Later snapshot"})
        release.set()
        result = await pending
        assert not result.is_error
        assert "First%20snapshot" in result.structured_content["artifact"]["url"]
        assert "Later" not in result.structured_content["artifact"]["url"]
        assert (await server.storage.read(123))["draft"]["name"] == "Later snapshot"

    asyncio.run(exercise())


@pytest.mark.parametrize("config", ["", "relative/path", "~/.drafts", "file"])
def test_invalid_storage_configuration_is_startup_error_without_protocol_output(tmp_path, config):
    if config == "file":
        root = tmp_path / "file"
        root.write_text("untouched")
        config = str(root)
    result = subprocess.run(
        [sys.executable, "-m", "best_practices_mcp"],
        env={**os.environ, "BESTPRACTICES_DATA_DIR": config},
        cwd=tmp_path,
        input="",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "directory" in result.stderr
    assert "Traceback" not in result.stderr


def test_unexpected_post_commit_error_requires_read_before_retry(tmp_path, monkeypatch):
    server = create_server(data_root=tmp_path)
    original = server.storage.update

    async def commit_then_fail(project_id, changes):
        await original(project_id, changes)
        raise RuntimeError("response interrupted after commit")

    monkeypatch.setattr(server.storage, "update", commit_then_fail)

    async def exercise():
        result = await server.call_tool(
            "update_draft", {"project_id": 123, "changes": {"name": "Committed"}}
        )
        assert result.is_error
        error = result.structured_content["error"]
        assert error["code"] == "internal_error"
        assert "read_draft" in error["recovery"]
        assert "do not automatically retry" in error["recovery"]
        assert (await server.storage.read(123))["draft"]["name"] == "Committed"

    asyncio.run(exercise())
