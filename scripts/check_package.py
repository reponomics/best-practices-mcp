"""Build and inspect an installed wheel offline, outside the source checkout.

Uses the active venv's dependencies; fresh installation is checked separately.
"""

import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PROBE = """
import asyncio, json, socket, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
async def main():
    def deny_network(*args, **kwargs):
        raise AssertionError("Package smoke test attempted network access")
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    with socket.socket() as probe:
        try:
            probe.connect(("192.0.2.1", 443))
        except AssertionError as error:
            assert str(error) == "Package smoke test attempted network access"
        else:
            raise AssertionError("External connect was permitted")
    import best_practices_mcp
    from best_practices_mcp.criteria import get_criteria, provenance, field_aliases
    from best_practices_mcp.contracts import validate_output
    from best_practices_mcp.server import create_server
    assert Path(best_practices_mcp.__file__).is_relative_to(Path(sys.argv[1]))
    index = get_criteria()
    assert len(index["levels"]) == 6
    for level in index["levels"]:
        result = get_criteria(level)
        validate_output("get_criteria", result)
        assert result["criteria"]
    assert provenance()["revision"] == "868e1677339a3fdb48851b0c2ae8862c553115eb"
    assert field_aliases()
    server = create_server()
    tool_names = [tool.name for tool in await server.list_tools()]
    assert tool_names == ["build_draft", "find_project", "get_criteria",
                          "get_project_badge_status", "get_project_badge_svg",
                          "get_project_progress",
                          "prepare_update_script", "prepare_update_url", "read_draft",
                          "update_draft", "validate_draft"]
    result = await server.call_tool("get_criteria", {"level": "passing"})
    assert result.structured_content["criteria"]
    print(json.dumps({"installed_catalog": "passed", "levels": index["levels"],
                      "network": "disabled", "live_tools": tool_names}))
# Windows needs an internal loopback socketpair to construct the event loop.
# All application imports/calls run afterward with every connection denied.
asyncio.run(main())
"""


def run(command: list[str], cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
    if result.returncode:
        # Avoid disclosing local path-heavy build logs in committed QA evidence.
        raise RuntimeError(f"Packaging stage {command[2:4]} failed (exit {result.returncode}).")
    return result.stdout


def check_archives(dist: Path) -> Path:
    wheel = next(dist.glob("*.whl"))
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "best_practices_mcp/data/catalog.json" in names
        assert "best_practices_mcp/data/provenance.json" in names
        assert any("LICENSE" in name for name in names)
        assert not any(name.startswith("vendor/") for name in names)
        assert not any(
            "node_modules" in name or name.endswith("package-lock.json") for name in names
        )
    with tarfile.open(next(dist.glob("*.tar.gz"))) as archive:
        names = archive.getnames()
        for suffix in (
            "/vendor/badgeapp/source.json",
            "/vendor/badgeapp/LICENSE",
            "/scripts/generate_catalog.py",
            "/scripts/verification_support.py",
            "/tests/test_contracts.py",
            "/tests/fixtures/forms/run_script.mjs",
            "/tests/fixtures/forms/passing.html",
            "/vendor/badgeapp/docs/automation-approach.md",
            "/package.json",
            "/package-lock.json",
            "/.nvmrc",
            "/uv.lock",
            "/.tool-versions",
            "/.github/release-please-config.json",
            "/.github/.release-please-manifest.json",
            "/examples/host.py",
        ):
            assert any(name.endswith(suffix) for name in names), suffix
        assert not any("/docs/live-qa/" in name for name in names)
        assert not any(name.endswith((".rb", ".erb", ".jbuilder")) for name in names)
    return wheel


def main() -> None:
    env = {**os.environ, "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
    with tempfile.TemporaryDirectory(prefix="bestpractices-package-") as directory:
        workspace = Path(directory)
        env["BESTPRACTICES_DATA_DIR"] = str(workspace / "untouched-drafts")
        dist = workspace / "dist"
        run([sys.executable, "-m", "build", "--no-isolation", "--outdir", str(dist)], ROOT, env)
        wheel = check_archives(dist)
        installed = workspace / "installed"
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--target",
                str(installed),
                str(wheel),
            ],
            workspace,
            env,
        )
        output = run([sys.executable, "-I", "-c", PROBE, str(installed)], workspace, env)
        summary = json.loads(output)
        print("Offline sdist/wheel build and isolated target install: PASS")
        print(
            f"Installed offline catalog: {len(summary['levels'])} levels; "
            f"live MCP tools: {len(summary['live_tools'])}"
        )
        print("Active venv supplies dependencies; use check-fresh-package for fresh installation.")


if __name__ == "__main__":
    main()
