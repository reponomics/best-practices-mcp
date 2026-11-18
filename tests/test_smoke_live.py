"""The opt-in smoke command reports domain failures after clean MCP shutdown."""

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "smoke_live", Path(__file__).resolve().parents[1] / "scripts" / "smoke_live.py"
)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


@pytest.mark.parametrize("failure", ["upstream_invalid_response", "empty", None])
def test_smoke_closes_client_before_reporting_domain_failure(monkeypatch, failure):
    exits = []
    calls = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *error):
            exits.append(error)

        async def call_tool(self, name, arguments):
            calls.append(name)
            if failure == "upstream_invalid_response":
                return SimpleNamespace(
                    is_error=True, structured_content={"error": {"code": failure}}
                )
            data = (
                {"candidates": [] if failure == "empty" else [{"project_id": 1}]}
                if name == "find_project"
                else {"project": {"project_id": 1}, "observation": {}, "levels": []}
            )
            return SimpleNamespace(is_error=False, structured_content=data)

    monkeypatch.setattr(smoke, "Client", Client)
    if failure:
        with pytest.raises(RuntimeError):
            asyncio.run(smoke.check(1))
        assert calls == ["find_project"]
    else:
        assert asyncio.run(smoke.check(1))["result"] == "passed"
        assert calls == ["find_project", "get_project_status"]
    assert exits == [(None, None, None)]
