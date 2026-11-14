"""Probe an installed package from an isolated directory; used by fresh-package QA."""

import asyncio
import importlib.metadata
import json
import platform
import subprocess
import sys
import sysconfig
from pathlib import Path

from mcp import Client, StdioServerParameters

TOOLS = [
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


def executable() -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return Path(sysconfig.get_path("scripts")) / f"bestpractices-mcp{suffix}"


async def call(client, name: str, arguments: dict, error: str | None = None) -> dict:
    result = await client.call_tool(name, arguments)
    payload = result.structured_content
    assert json.loads(result.content[0].text) == payload
    assert result.is_error == (error is not None)
    if error:
        assert payload["error"]["code"] == error
    return payload


async def catalog_and_storage(params: StdioServerParameters) -> None:
    async with Client(params) as client:
        listing = (await client.list_tools()).tools
        assert [tool.name for tool in listing] == TOOLS
        assert client.protocol_version == "2026-07-28"
        mutation = next(tool for tool in listing if tool.name == "update_draft")
        assert mutation.annotations.read_only_hint is False
        index = await call(client, "get_criteria", {})
        assert len(index["levels"]) == 6
        for level in index["levels"]:
            assert (await call(client, "get_criteria", {"level": level}))["criteria"]
        await call(client, "read_draft", {"project_id": 123}, "draft_not_found")
        draft = {"name": "Fresh install ✨", "description_good_justification": "Synthetic text"}
        created = await call(client, "update_draft", {"project_id": 123, "changes": draft})
        assert created["created"] is True
        await call(
            client, "update_draft", {"project_id": 123, "changes": {"name": 3}}, "invalid_field"
        )
        assert (await call(client, "read_draft", {"project_id": 123}))["draft"] == draft
        result = await call(client, "validate_draft", {"project_id": 123, "level": "passing"})
        assert result["draft_source"]["kind"] == "stored"
    async with Client(params) as client:
        assert (await call(client, "read_draft", {"project_id": 123}))["draft"] == draft


async def synthetic_public_workflow(workspace: Path, env: dict) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-I", str(workspace / "read_server.py")],
        cwd=str(workspace),
        env=env,
    )
    async with Client(params) as client:
        found = await call(client, "find_project", {"query": "123"})
        assert found["candidates"][0]["project"]["project_id"] == 123
        progress = await call(client, "get_project_progress", {"project_id": 123})
        assert progress["project"]["project_id"] == 123
        for tool in ("prepare_update_url", "prepare_update_script"):
            result = await call(client, tool, {"project_id": 123, "level": "passing"})
            assert result["draft_source"]["kind"] == "stored" and result["artifact"]
            explicit = await call(
                client, tool, {"project_id": 123, "level": "passing", "draft": {}}
            )
            assert explicit["draft_source"]["kind"] == "explicit"


async def exercise(workspace: Path) -> None:
    env = {"BESTPRACTICES_DATA_DIR": str(workspace / "drafts")}
    params = StdioServerParameters(command=str(executable()), cwd=str(workspace), env=env)
    async with asyncio.timeout(60):
        await catalog_and_storage(params)
        await synthetic_public_workflow(workspace, env)


def main() -> None:
    import best_practices_mcp

    assert sys.prefix != sys.base_prefix
    assert Path(best_practices_mcp.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    workspace = Path.cwd()
    asyncio.run(exercise(workspace))
    discovery = subprocess.run(
        [sys.executable, "-I", str(workspace / "host.py"), "--discover"],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )
    assert json.loads(discovery.stdout)["tools"] == TOOLS
    print(
        json.dumps(
            {
                "status": "passed",
                "python": platform.python_version(),
                "os": platform.system(),
                "tools": len(TOOLS),
                "catalog_levels": 6,
                "installed_entry_point": "passed",
                "stored_restart": "passed",
                "synthetic_public_artifacts": "passed",
                "reference_host_discovery": "passed",
                "installed_in_fresh_venv": True,
                "dependencies": {
                    dist.metadata["Name"]: dist.version
                    for dist in importlib.metadata.distributions()
                },
            }
        )
    )


if __name__ == "__main__":
    main()
