"""Exercise installed entry points through the real MCP stdio transport."""

import asyncio
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters


def server_command() -> str:
    suffix = ".exe" if sys.platform == "win32" else ""
    return str(Path(sysconfig.get_path("scripts")) / f"bestpractices-mcp{suffix}")


def test_stdio_discovery_has_eleven_tools_without_creating_storage(tmp_path: Path) -> None:
    async def exercise() -> None:
        parameters = StdioServerParameters(
            command=server_command(),
            cwd=tmp_path,
            env={"BESTPRACTICES_DATA_DIR": str(tmp_path / "drafts")},
        )
        async with asyncio.timeout(10), Client(parameters, read_timeout_seconds=5) as client:
            assert client.server_info is not None
            assert client.server_info.name == "bestpractices-mcp"
            assert client.protocol_version == "2026-07-28"
            assert [tool.name for tool in (await client.list_tools()).tools] == [
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

    asyncio.run(exercise())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("argument", ["--help", "--version"])
def test_cli_metadata_exits_without_waiting_for_protocol(argument: str, tmp_path: Path) -> None:
    result = subprocess.run(
        [server_command(), argument],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    assert "bestpractices-mcp" in result.stdout
    assert result.stderr == ""
