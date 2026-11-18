"""Opt-in live compatibility check: two paced public GETs through actual MCP tools."""

import argparse
import asyncio
import json
import sys

from mcp import Client, StdioServerParameters


def require_success(result) -> dict:
    data = result.structured_content
    if result.is_error:
        code = (
            data.get("error", {}).get("code", "tool_error")
            if isinstance(data, dict)
            else "tool_error"
        )
        raise RuntimeError(f"Public read failed: {code}.")
    if not isinstance(data, dict):
        raise RuntimeError("Public read returned no structured result.")
    return data


async def check(project_id: int) -> dict:
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "best_practices_mcp"])
    failure = None
    async with asyncio.timeout(80), Client(parameters, read_timeout_seconds=40) as client:
        # Raise expected tool failures after the SDK context closes to avoid task-group wrapping.
        try:
            found = require_success(
                await client.call_tool("find_project", {"query": str(project_id)})
            )
            if not found["candidates"]:
                raise RuntimeError("Project lookup returned no registered entry.")
            data = require_success(
                await client.call_tool("get_project_status", {"project_id": project_id})
            )
        except RuntimeError as error:
            failure = error
    if failure is not None:
        raise failure
    return {
        "result": "passed",
        "project_id": data["project"]["project_id"],
        "observation": data["observation"],
        "levels_reported": len(data["levels"]),
        "note": "Public GET observation only; no deployed-source revision or save claim.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=int, required=True)
    args = parser.parse_args()
    if args.project_id <= 0:
        parser.error("project-id must be positive")
    try:
        result = asyncio.run(check(args.project_id))
    except (RuntimeError, TimeoutError) as error:
        print(f"Live smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print("Live smoke failed: MCP connection could not complete.", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
