"""Exercise badge contracts and inert SVG transfer through the real MCP boundary."""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from mcp import Client, StdioServerParameters

from best_practices_mcp import sdk_adapter
from best_practices_mcp.contracts import output_schema
from best_practices_mcp.errors import DomainError
from best_practices_mcp.sdk_adapter import result_bytes, tool_result

FIXTURE_SERVER = Path(__file__).parent / "fixtures/read_server.py"
EXAMPLES = json.loads(
    (Path(__file__).parent / "fixtures/contracts/examples.json").read_text(encoding="utf-8")
)


async def assert_svg_artifact(client, family):
    image = await client.call_tool("get_project_badge_svg", {"project_id": 123, "family": family})
    payload = image.structured_content
    assert not image.is_error
    Draft202012Validator(output_schema("get_project_badge_svg")).validate(payload)
    assert json.loads(image.content[0].text) == payload
    assert len(image.content) == 1 and image.content[0].type == "text"
    suffix = "badge" if family == "best_practices" else "baseline"
    expected_svg = f'<svg xmlns="http://www.w3.org/2000/svg"><text>{suffix} 雪</text></svg>\n'
    assert payload["artifact"]["svg"] == expected_svg
    assert payload["artifact"]["encoded_size_bytes"] == len(expected_svg.encode())
    assert payload["image_url"].endswith(f"/{suffix}.svg")
    assert payload["image_url"] in payload["markdown"]


def test_badge_svg_over_stdio_preserves_payloads_and_leaves_storage_untouched(tmp_path: Path):
    async def exercise():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(FIXTURE_SERVER.resolve())],
            cwd=tmp_path,
            env={"BESTPRACTICES_DATA_DIR": str(tmp_path / "drafts")},
        )
        async with asyncio.timeout(15), Client(parameters, read_timeout_seconds=5) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert "get_project_badge_status" not in tools
            tool = tools["get_project_badge_svg"]
            assert tool.title
            assert tool.annotations.read_only_hint
            assert tool.annotations.idempotent_hint
            assert tool.annotations.open_world_hint
            assert not tool.annotations.destructive_hint
            for family in ("best_practices", "baseline"):
                await assert_svg_artifact(client, family)
            arguments = {"project_id": 999, "family": "baseline"}
            missing = await client.call_tool("get_project_badge_svg", arguments)
            assert missing.is_error
            assert missing.structured_content["error"]["code"] == "project_not_found"
            invalid = await client.call_tool(
                "get_project_badge_svg", arguments | {"project_id": True}
            )
            assert invalid.is_error
            assert "input_value" not in invalid.content[0].text
            omitted = await client.call_tool("get_project_badge_svg", {"project_id": 123})
            assert omitted.is_error

    asyncio.run(exercise())
    assert not list(tmp_path.iterdir())


def test_svg_complete_result_budget_includes_both_channels_and_json_escaping(monkeypatch):
    payload = EXAMPLES["get_project_badge_svg"]["success"]
    result = tool_result("get_project_badge_svg", payload)
    size = len(result_bytes(result))
    assert size > 2 * payload["artifact"]["encoded_size_bytes"]
    monkeypatch.setattr(sdk_adapter, "RESPONSE_LIMIT_BYTES", size)
    assert len(result_bytes(tool_result("get_project_badge_svg", payload))) == size
    monkeypatch.setattr(sdk_adapter, "RESPONSE_LIMIT_BYTES", size - 1)
    with pytest.raises(DomainError) as error:
        tool_result("get_project_badge_svg", payload)
    assert error.value.code == "response_too_large"
    assert "BadgeApp's project page" in error.value.recovery
