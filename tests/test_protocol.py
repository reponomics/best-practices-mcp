"""MCP wire obligations, independently of the SDK client handshake logic."""

import asyncio
import json
import os
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "conformance-probe", "version": "1"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


async def exchange(
    tmp_path: Path, requests: list[dict], script: Path | None = None
) -> tuple[list[dict], bytes]:
    arguments = [str(script)] if script else ["-m", "best_practices_mcp"]
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        *arguments,
        cwd=tmp_path,
        env={**os.environ, "BESTPRACTICES_DATA_DIR": str(tmp_path / "untouched")},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    replies = []
    try:
        for request in requests:
            process.stdin.write((json.dumps(request) + "\n").encode())
            await process.stdin.drain()
            if "id" not in request:
                continue
            line = await asyncio.wait_for(process.stdout.readline(), timeout=5)
            replies.append(json.loads(line))
        process.stdin.close()
        await asyncio.wait_for(process.wait(), timeout=5)
        diagnostics = await process.stderr.read()
        assert process.returncode == 0
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    return replies, diagnostics


def request(number: int, method: str, **params) -> dict:
    return {"jsonrpc": "2.0", "id": number, "method": method, "params": {"_meta": META, **params}}


def test_modern_discovery_without_initialize_and_stable_lists(tmp_path: Path) -> None:
    requests = [request(1, "server/discover"), request(2, "tools/list"), request(3, "tools/list")]
    replies, diagnostics = asyncio.run(exchange(tmp_path, requests))
    assert diagnostics == b""
    for number, reply in enumerate(replies, 1):
        assert reply["id"] == number
        result = reply["result"]
        assert result["resultType"] == "complete"
        assert result["ttlMs"] == 0
        assert result["cacheScope"] == "public"
        assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "bestpractices-mcp"
    assert replies[1]["result"]["tools"] == replies[2]["result"]["tools"]
    assert [tool["name"] for tool in replies[1]["result"]["tools"]] == [
        "build_draft",
        "find_project",
        "get_criteria",
        "get_project_badge_status",
        "get_project_badge_svg",
        "get_project_progress",
        "prepare_update_script",
        "prepare_update_url",
        "read_draft",
        "update_draft",
        "validate_draft",
    ]
    assert not list(tmp_path.iterdir())


def test_unsupported_version_and_unknown_tool_are_protocol_errors(tmp_path: Path) -> None:
    unsupported = request(1, "tools/list")
    unsupported["params"]["_meta"] = {
        **META,
        "io.modelcontextprotocol/protocolVersion": "2099-01-01",
    }
    calls = [unsupported, request(2, "tools/call", name="not_a_planned_tool", arguments={})]
    replies, diagnostics = asyncio.run(exchange(tmp_path, calls))
    assert diagnostics == b""
    assert replies[0]["error"]["code"] == -32022
    assert replies[1]["error"]["code"] == -32602
    assert not list(tmp_path.iterdir())


def test_legacy_discovery_and_object_results_remain_usable(tmp_path: Path) -> None:
    """SDK legacy serialization must accept the same object-only output unions."""
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "legacy-conformance-probe", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_criteria",
                "arguments": {"level": "passing", "criterion_ids": ["description_good"]},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "read_draft", "arguments": {"project_id": 123}},
        },
    ]
    replies, diagnostics = asyncio.run(exchange(tmp_path, requests))
    assert diagnostics == b""
    assert [reply["id"] for reply in replies] == [1, 2, 3, 4]
    assert replies[0]["result"]["protocolVersion"] == "2025-11-25"
    tools = {tool["name"]: tool for tool in replies[1]["result"]["tools"]}
    assert len(tools) == 11
    for tool in tools.values():
        assert tool["outputSchema"]["type"] == "object"
        assert len(tool["outputSchema"]["anyOf"]) == 2
        Draft202012Validator.check_schema(tool["outputSchema"])
    for name, reply in zip(("get_criteria", "read_draft"), replies[2:], strict=True):
        result = reply["result"]
        payload = result["structuredContent"]
        Draft202012Validator(tools[name]["outputSchema"]).validate(payload)
        assert json.loads(result["content"][0]["text"]) == payload
    assert replies[2]["result"]["isError"] is False
    assert replies[2]["result"]["structuredContent"]["criteria"][0]["criterion_id"] == (
        "description_good"
    )
    failure = replies[3]["result"]
    assert failure["isError"] is True
    assert failure["structuredContent"]["error"]["code"] == "draft_not_found"
    assert failure["structuredContent"]["error"]["recovery"]
    assert not list(tmp_path.iterdir())


def test_known_domain_failure_remains_a_structured_tool_result(tmp_path: Path) -> None:
    script = tmp_path / "fixture_server.py"
    script.write_text(
        "from best_practices_mcp.server import create_server\n"
        "from best_practices_mcp.sdk_adapter import tool_result\n"
        "from best_practices_mcp.errors import DomainError\n"
        "server = create_server()\n"
        "@server.tool(structured_output=False)\n"
        "def known_failure():\n"
        "    error = DomainError('invalid_level', 'Choose a level.')\n"
        "    return tool_result('get_criteria', error.to_payload())\n"
        "server.run(transport='stdio')\n"
    )
    calls = [request(1, "tools/call", name="known_failure", arguments={})]
    replies, diagnostics = asyncio.run(exchange(tmp_path, calls, script))
    assert diagnostics == b""
    result = replies[0]["result"]
    assert result["resultType"] == "complete"
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "invalid_level"
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
