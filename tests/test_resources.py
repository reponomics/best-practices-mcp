"""Criteria and project documents offered as MCP resources."""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import pytest
from mcp import Client, MCPError, StdioServerParameters

from best_practices_mcp import resources
from best_practices_mcp.criteria import catalog_levels, criterion_definitions, level_summary
from best_practices_mcp.server import create_server

FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "read_server.py"
# The levels index, six levels, 39 level and category pairs, and the repository-file guide.
FIXED_RESOURCES = 47
TEMPLATES = [
    "criteria://{level}/{criterion_id}",
    "project://{project_id}/{level}",
    "project://{project_id}/{level}/{category}",
]


def test_every_level_and_category_is_a_listed_markdown_resource(tmp_path: Path) -> None:
    server = create_server(data_root=tmp_path)
    listed = {resource.uri: resource for resource in asyncio.run(server.list_resources())}
    expected = {"criteria://levels", "guide://repository-file"}
    for level in catalog_levels():
        expected.add(f"criteria://{level}")
        for category in level_summary(level)["categories"]:
            expected.add(f"criteria://{level}/{resources.category_slug(category)}")
    assert set(listed) == expected and len(listed) == FIXED_RESOURCES
    for resource in listed.values():
        assert resource.name and resource.title and resource.description
        assert resource.mime_type == "text/markdown"
        assert " " not in resource.uri and resource.uri == resource.uri.lower()
    assert listed["criteria://passing/change-control"].title == ("Passing criteria: Change Control")
    assert listed["criteria://baseline-2"].title == "Baseline level 2 criteria"
    templates = asyncio.run(server.list_resource_templates())
    assert [template.uri_template for template in templates] == TEMPLATES
    assert not list(tmp_path.iterdir())


def test_repository_file_guide_states_what_the_server_does_not_do() -> None:
    guide = resources.repository_file_guide()
    assert guide.startswith("# The repository `.bestpractices.json` file\n")
    for statement in (
        "this server does not read, write or send the repository one",
        "has to be committed and pushed",
        "They do not replace an answer that is already saved",
        "`.project.d/bestpractices.json`",
        "has not been tested end to end",
    ):
        assert statement in guide


def test_levels_document_links_every_category_resource() -> None:
    document = resources.levels_document()
    assert "## silver (55 criteria)" in document
    assert "- Change Control: `criteria://gold/change-control`" in document
    assert "- Access Control: `criteria://baseline-1/access-control`" in document


def test_level_document_groups_by_category_without_details() -> None:
    document = resources.level_document("passing")
    [build] = criterion_definitions("passing", ["build"])
    assert document.startswith("# Passing criteria\n\n67 criteria.")
    description = resources.markdown_text(build["description"], "passing")
    assert "## Quality\n\n### build (MUST)\n\n" + description in document
    assert build["details"] not in document
    assert "Draft fields" not in document
    assert len(document) * 2 < sum(
        len(resources.category_document("passing", category))
        for category in level_summary("passing")["categories"]
    )


@pytest.mark.parametrize(
    "level,criterion_id,rules",
    [
        (
            "passing",
            "build",
            "Met does not require a justification. N/A is allowed without a justification.",
        ),
        (
            "passing",
            "description_good",
            "Met does not require a justification. N/A is not allowed.",
        ),
        (
            "silver",
            "hardening",
            "Met requires a justification. N/A is allowed and requires a justification.",
        ),
        (
            "gold",
            "build_reproducible",
            "Met requires a justification that contains a URL. "
            "N/A is allowed and requires a justification.",
        ),
    ],
)
def test_criterion_document_states_fields_and_status_rules(level, criterion_id, rules) -> None:
    [criterion] = criterion_definitions(level, [criterion_id])
    document = resources.criterion_document(level, criterion_id)
    assert f"## {criterion_id} ({criterion['requirement']})" in document
    for text in (criterion["description"], criterion["details"]):
        assert resources.markdown_text(text, level) in document
    assert document.rstrip().endswith(
        f"Draft fields: `{criterion_id}_status`, `{criterion_id}_justification`. {rules}"
    )


def test_category_document_holds_only_that_category_in_full() -> None:
    document = resources.category_document("baseline-1", "Access Control")
    assert document.startswith("# Baseline level 1 criteria: Access Control\n\n4 criteria.")
    assert document.count("\n## osps_ac_") == 4 and "osps_br_" not in document
    # A criterion without details still lists its fields.
    assert "`interact_status`" in resources.category_document("passing", "Basics")


def test_project_document_pairs_each_criterion_with_its_saved_answer() -> None:
    criteria = criterion_definitions(
        "passing", ["build", "contribution", "description_good", "interact"]
    )
    progress = {
        "project": {"project_id": 123, "name": None},
        "level": "passing",
        "answers": {
            "description_good_status": "Met",
            "description_good_justification": "First line.\n# Not a heading",
            "contribution_status": "?",
            "contribution_justification": "   ",
            "build_status": {"future": "value"},
            "build_justification": None,
        },
        "observation": {"source_url": "https://example.test/123.json", "fetched_at": "T"},
    }
    document = resources.project_document(progress, criteria, "Basics")
    assert document.startswith("# Unnamed project (project 123): Passing, Basics\n")
    assert (
        "4 criteria: 1 Met, 1 unanswered (?), 1 not retrieved, "
        '1 unrecognized value `{"future": "value"}`.'
    ) in document
    assert "## contribution (MUST): unanswered (?)" in document
    assert "read from https://example.test/123.json at T." in document
    assert "## description_good (MUST): Met" in document
    assert "Saved justification:\n\n> First line.\n> # Not a heading\n" in document
    assert "## interact (MUST): not retrieved" in document
    assert document.count("This is a retrieval failure, not an answer") == 1
    assert document.count("No justification saved.") == 3


def test_every_criterion_text_converts_to_markdown_without_leftover_html() -> None:
    converted = 0
    for level in catalog_levels():
        for criterion in criterion_definitions(level):
            for text in filter(None, (criterion["description"], criterion["details"])):
                document = resources.markdown_text(text, level)
                assert not re.search(r"</?[a-zA-Z]+[ >]|href=|&[a-z]+;", document), (
                    level,
                    criterion["criterion_id"],
                )
                converted += text != document
    assert converted


def test_markdown_conversion_keeps_wording_and_structure() -> None:
    convert = resources.markdown_text
    assert convert('See <a href="https://example.org/a">the\n guide</a>.', "gold") == (
        "See [the guide](https://example.org/a)."
    )
    assert convert('as in <a href="#signed_releases">signed_releases</a>.', "silver") == (
        "as in signed_releases (`criteria://silver/signed_releases`)."
    )
    assert convert("<em>must</em> <i>not</i> <strong>or</strong> <tt>a &gt; b</tt>", "gold") == (
        "*must* *not* **or** `a > b`"
    )
    assert convert('<a href="https://example.org"><tt>id: [x]</tt></a>', "gold") == (
        "[`id: [x]`](https://example.org)"
    )
    numbered = "Either:\n<ol>\n<li> one;</li>\n<li> two\n  lines.</li>\n</ol>\nThen."
    assert convert(numbered, "gold") == "Either:\n\n1. one;\n2. two lines.\n\nThen."
    assert convert("Know: <ul> <li>first <li>second </ul>", "gold") == "Know:\n\n- first\n- second"
    assert convert("One. <br><br> Two.", "gold") == "One.\n\nTwo."
    assert convert("Plain *allowlist* text.", "gold") == "Plain *allowlist* text."


def test_page_anchors_point_at_criteria_of_the_same_level() -> None:
    document = resources.criterion_document("silver", "version_tags_signed")
    assert "signed_releases (`criteria://silver/signed_releases`)" in document
    assert criterion_definitions("silver", ["signed_releases"])


async def read(client, uri: str) -> str:
    result = await client.read_resource(uri)
    [content] = result.contents
    assert content.mime_type == "text/markdown"
    return content.text


def test_resources_over_stdio_read_catalog_and_project_documents(tmp_path: Path) -> None:
    async def exercise():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(FIXTURE_SERVER.resolve())],
            cwd=tmp_path,
            env={"BESTPRACTICES_DATA_DIR": str(tmp_path / "drafts")},
        )
        async with asyncio.timeout(15), Client(parameters, read_timeout_seconds=5) as client:
            assert len((await client.list_resources()).resources) == FIXED_RESOURCES
            guide = await read(client, "guide://repository-file")
            assert guide == resources.repository_file_guide()
            listed = (await client.list_resource_templates()).resource_templates
            assert [template.uri_template for template in listed] == TEMPLATES
            assert await read(client, "criteria://levels") == resources.levels_document()
            assert await read(client, "criteria://gold") == resources.level_document("gold")
            assert await read(client, "criteria://silver/security") == (
                resources.category_document("silver", "Security")
            )
            assert await read(client, "criteria://silver/dco") == (
                resources.criterion_document("silver", "dco")
            )
            assert await read(client, "criteria://baseline-1/OSPS-AC-01.01") == (
                resources.criterion_document("baseline-1", "osps_ac_01_01")
            )
            category = await read(client, "project://123/passing/basics")
            assert category.startswith("# Fixture Alpha (project 123): Passing, Basics\n")
            assert "13 criteria: 1 Met, 12 not retrieved." in category
            assert "> https://example.org/alpha explains the project." in category
            level = await read(client, "project://456/passing")
            assert "67 criteria: 1 Unmet, 66 not retrieved." in level
            assert "## description_good (MUST): Unmet" in level
            failures = {
                "criteria://silver/unknown": "does not define the requested criterion",
                "criteria://baseline-1/OSPS-BR-02.01": "OSPS-BR-02.01 is a criterion of baseline-2",
                "criteria://bronze/dco": "supported badge levels",
                "criteria://unknown": "Unknown resource",
                "project://abc/passing": "numeric project ID",
                "project://999/passing": "did not find the requested public project",
                "project://123/passing/unknown": "Allowed: analysis, basics, change-control",
            }
            for uri, message in failures.items():
                with pytest.raises(MCPError, match=message):
                    await client.read_resource(uri)

    asyncio.run(exercise())
    assert not list(tmp_path.iterdir())


def test_projects_with_a_stored_draft_are_listed_by_level(tmp_path: Path) -> None:
    server = create_server(data_root=tmp_path)

    async def listed() -> list[str]:
        listing = await server.list_resources()
        return [resource.uri for resource in listing if resource.uri.startswith("project://")]

    assert asyncio.run(listed()) == []
    for project_id in (456, 123):
        asyncio.run(server.call_tool("update_draft", {"project_id": project_id, "changes": {}}))
    projects = tmp_path / "projects"
    # Not canonical project directories, or no draft file: none of these is listed.
    for name in ("0123", "abc", "789"):
        (projects / name).mkdir()
    (projects / "0123" / ".bestpractices.json").write_text("{}", encoding="utf-8")
    (projects / "999").write_text("not a directory", encoding="utf-8")
    assert asyncio.run(listed()) == [
        f"project://{project_id}/{level}" for project_id in (123, 456) for level in catalog_levels()
    ]
    [gold] = [r for r in asyncio.run(server.list_resources()) if r.uri == "project://456/gold"]
    assert gold.name == "456/gold" and gold.mime_type == "text/markdown"
    assert gold.title == "Project 456 saved answers: Gold"


def test_unusable_storage_lists_no_projects(tmp_path: Path) -> None:
    server = create_server(data_root=tmp_path)
    (tmp_path / "projects").write_text("not a directory", encoding="utf-8")
    assert len(asyncio.run(server.list_resources())) == FIXED_RESOURCES


class RecordingContext:
    """Stands in for the request context to count list-change announcements."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.session = self

    async def notify_resources_changed(self) -> None:
        self.calls.append("listen")

    async def send_resource_list_changed(self) -> None:
        self.calls.append("notification")


def test_only_a_first_draft_announces_a_resource_list_change(tmp_path: Path) -> None:
    server = create_server(data_root=tmp_path)
    context = RecordingContext()

    def update(project_id: int, changes: dict) -> None:
        arguments = {"project_id": project_id, "changes": changes}
        result = asyncio.run(server.call_tool("update_draft", arguments, context))
        assert not result.is_error

    update(123, {})
    assert context.calls == ["listen", "notification"]
    update(123, {"name": "Changed"})
    assert context.calls == ["listen", "notification"]
    update(456, {})
    assert context.calls == ["listen", "notification"] * 2


MODERN = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "resource-probe", "version": "1"},
    "io.modelcontextprotocol/clientCapabilities": {},
}
LIST_CHANGED = "notifications/resources/list_changed"


async def wire(tmp_path: Path, requests: list[dict], response: int) -> list[dict]:
    """Send raw JSON-RPC messages; read until a list change and `response` have both arrived."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "best_practices_mcp",
        env={**os.environ, "BESTPRACTICES_DATA_DIR": str(tmp_path / "drafts")},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        limit=2**24,
    )
    replies: list[dict] = []
    try:
        for request in requests:
            process.stdin.write((json.dumps(request) + "\n").encode())
        await process.stdin.drain()
        wanted = {("id", response), ("method", LIST_CHANGED)}
        while not all(any(reply.get(key) == value for reply in replies) for key, value in wanted):
            replies.append(json.loads(await asyncio.wait_for(process.stdout.readline(), 5)))
    finally:
        process.kill()
        await process.wait()
    return replies


def create_draft(number: int, meta: dict | None = None) -> dict:
    params = {"name": "update_draft", "arguments": {"project_id": 123, "changes": {}}}
    if meta is not None:
        params["_meta"] = meta
    return {"jsonrpc": "2.0", "id": number, "method": "tools/call", "params": params}


def test_first_draft_reaches_a_subscriptions_listen_stream(tmp_path: Path) -> None:
    listen = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "subscriptions/listen",
        "params": {"_meta": MODERN, "notifications": {"resourcesListChanged": True}},
    }
    replies = asyncio.run(wire(tmp_path, [listen, create_draft(2, MODERN)], response=2))
    [change] = [reply for reply in replies if reply.get("method") == LIST_CHANGED]
    assert change["params"]["_meta"]["io.modelcontextprotocol/subscriptionId"] == 1
    [created] = [reply for reply in replies if reply.get("id") == 2]
    assert created["result"]["structuredContent"]["created"] is True


def test_first_draft_notifies_clients_of_the_earlier_protocol(tmp_path: Path) -> None:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "legacy-resource-probe", "version": "1"},
        },
    }
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    replies = asyncio.run(wire(tmp_path, [initialize, initialized, create_draft(2)], response=2))
    assert replies[0]["result"]["capabilities"]["resources"]["listChanged"] is True
    assert [reply.get("method") for reply in replies].count(LIST_CHANGED) == 1
