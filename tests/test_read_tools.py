"""Exercise production read handlers and advertised contracts over real MCP stdio."""

import asyncio
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from mcp import Client, StdioServerParameters

from best_practices_mcp.contracts import input_schema, output_schema
from best_practices_mcp.server import IMPLEMENTED_TOOLS

FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "read_server.py"


def test_read_workflow_wire_results_and_catalog_schemas(tmp_path: Path) -> None:
    async def exercise():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(FIXTURE_SERVER.resolve())],
            cwd=tmp_path,
            env={"BESTPRACTICES_DATA_DIR": str(tmp_path / "drafts")},
        )
        async with asyncio.timeout(15), Client(parameters, read_timeout_seconds=5) as client:
            listed = (await client.list_tools()).tools
            assert [tool.name for tool in listed] == sorted(IMPLEMENTED_TOOLS)
            for tool in listed:
                assert tool.input_schema == input_schema(tool.name)
                assert tool.output_schema == output_schema(tool.name)
                assert tool.annotations.read_only_hint is (tool.name != "update_draft")
                assert tool.title and tool.description
                for argument, schema in tool.input_schema["properties"].items():
                    assert schema.get("description"), (tool.name, argument)
            # The draft format is discoverable from the listing alone.
            listing = json.dumps([tool.input_schema for tool in listed])
            assert all(word in listing for word in ('\\"Unmet\\"', "implementation_languages"))
            # Before the rate-limited search below starts a shared cooldown.
            await assert_filtered_reads(client)
            calls = [
                ("get_criteria", {}),
                ("find_project", {"query": "ambiguous"}),
                ("get_project_answers", {"project_id": 123, "level": "passing"}),
                ("get_criteria", {"level": "passing", "criterion_ids": ["unknown"]}),
                ("get_project_status", {"project_id": 999}),
                ("find_project", {"query": "rate-limited"}),
            ]
            results = []
            for name, arguments in calls:
                result = await client.call_tool(name, arguments)
                payload = result.structured_content
                Draft202012Validator(output_schema(name)).validate(payload)
                assert json.loads(result.content[0].text) == payload
                results.append(result)
            assert len(results[0].structured_content["levels"]) == 6
            assert len(results[1].structured_content["candidates"]) == 2
            assert results[2].structured_content["answers"]["description_good_status"] == "Met"
            assert results[2].structured_content["observation"]["license"] == "CC-BY-3.0+"
            assert [r.structured_content["error"]["code"] for r in results[3:]] == [
                "invalid_criterion",
                "project_not_found",
                "rate_limited",
            ]
            assert all(r.is_error for r in results[3:])
            await assert_argument_errors(client)
            assert [t.name for t in (await client.list_tools()).tools] == sorted(IMPLEMENTED_TOOLS)

    asyncio.run(exercise())
    assert not list(tmp_path.iterdir())


async def call(client, name: str, arguments: dict) -> dict:
    result = await client.call_tool(name, arguments)
    Draft202012Validator(output_schema(name)).validate(result.structured_content)
    assert json.loads(result.content[0].text) == result.structured_content
    assert result.is_error == ("error" in result.structured_content)
    return result.structured_content


async def assert_filtered_reads(client) -> None:
    index = await call(client, "get_criteria", {"level": "passing", "category": "Basics"})
    assert index["schema_version"] == 2 and index["detail"] == "index"
    assert {"criterion_id": "description_good", "category": "Basics", "requirement": "MUST"} in (
        index["criteria"]
    )
    full = await call(client, "get_criteria", {"level": "passing", "criterion_ids": ["interact"]})
    assert full["detail"] == "full" and full["criteria"][0]["status_field"] == "interact_status"
    unknown = await call(client, "get_criteria", {"level": "passing", "category": "basics"})
    assert unknown["error"]["code"] == "invalid_category"
    assert "Basics" in unknown["error"]["details"]["allowed"]
    # A numeric string and null optional arguments are accepted at the tool boundary.
    status = await call(client, "get_project_status", {"project_id": 123})
    assert status["badge_level"] == "passing"
    assert status["updated_at"] == "2026-11-13T12:34:56.000Z"
    assert status["levels"][0] == {
        "level": "passing",
        "percentage": 100,
        "achieved_at": "2026-10-01T09:00:00.000Z",
        "lost_at": None,
    }
    assert [entry["percentage"] for entry in status["levels"][1:]] == [12, None, None, None, None]
    assert "answers" not in status
    saved = await call(
        client,
        "get_project_answers",
        {
            "project_id": "123",
            "level": "passing",
            "criterion_ids": None,
            "statuses": ["Met"],
            "include_justifications": False,
        },
    )
    assert saved["schema_version"] == 1
    assert saved["answers"] == {"description_good_status": "Met"}
    assert saved["level_criterion_count"] == 67
    # The synthetic record omits most statuses, which BadgeApp itself never does.
    assert len(saved["statuses_not_retrieved"]) == 66
    rejected = await call(
        client,
        "get_project_answers",
        {"project_id": 123, "level": "passing", "statuses": ["absent"]},
    )
    assert rejected["error"]["details"]["issues"][0]["allowed"] == ["Met", "Unmet", "N/A", "?"]
    unscoped = await call(client, "get_project_answers", {"project_id": 123})
    assert unscoped["error"]["details"]["issues"] == [{"field": "level", "problem": "is required"}]


async def assert_argument_errors(client) -> None:
    rejected = await call(
        client,
        "get_project_answers",
        {"project_id": True, "level": "bronze", "statuses": ["Met"], "format": "short"},
    )
    assert rejected == {
        "schema_version": 1,
        "error": {
            "code": "invalid_arguments",
            "message": "Invalid arguments for get_project_answers.",
            "details": {
                "issues": [
                    {"field": "format", "problem": "is not an argument of this tool"},
                    {
                        "field": "level",
                        "problem": "is not an allowed value",
                        "allowed": [
                            "passing",
                            "silver",
                            "gold",
                            "baseline-1",
                            "baseline-2",
                            "baseline-3",
                        ],
                    },
                    {"field": "project_id", "problem": "must be an integer"},
                ]
            },
            "recovery": "Correct the listed arguments and call again.",
            "retry_after_seconds": None,
        },
    }
    dependent = await call(client, "get_criteria", {"criterion_ids": ["interact"]})
    assert dependent["error"]["details"]["issues"] == [
        {"field": "criterion_ids", "problem": "requires level"}
    ]


def test_offline_catalog_and_invalid_inputs_need_no_network(tmp_path: Path) -> None:
    script = tmp_path / "network_forbidden.py"
    script.write_text(
        "import asyncio, socket\n"
        "async def main():\n"
        "    def deny(*args, **kwargs): raise RuntimeError('network forbidden')\n"
        "    socket.create_connection = deny\n"
        "    socket.socket.connect = deny\n"
        "    socket.socket.connect_ex = deny\n"
        "    with socket.socket() as probe:\n"
        "        try: probe.connect(('192.0.2.1', 443))\n"
        "        except RuntimeError as error: assert str(error) == 'network forbidden'\n"
        "        else: raise AssertionError('external connect was permitted')\n"
        "    from best_practices_mcp.server import create_server\n"
        "    await create_server().run_stdio_async()\n"
        # Windows ProactorEventLoop needs its internal socketpair during creation.
        # Create that loop first, then deny every connect throughout application use.
        "asyncio.run(main())\n",
        encoding="utf-8",
    )

    async def exercise():
        async with (
            asyncio.timeout(10),
            Client(
                StdioServerParameters(command=sys.executable, args=[str(script)]),
                read_timeout_seconds=5,
            ) as client,
        ):
            result = await client.call_tool("get_criteria", {"level": "silver"})
            assert not result.is_error
            assert result.structured_content["criteria"]
            invalid = await client.call_tool("find_project", {"query": None})
            assert invalid.is_error
            assert invalid.structured_content["error"]["details"]["issues"] == [
                {"field": "query", "problem": "is required"}
            ]

    asyncio.run(exercise())
