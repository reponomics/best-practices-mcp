"""MCP tool composition; protocol and transport remain SDK-owned."""

from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import MCPError
from mcp.server import MCPServer
from mcp.server.caching import CacheHint
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, InputRequiredResult, Tool
from pydantic import ValidationError

from best_practices_mcp import __version__
from best_practices_mcp.artifacts import prepare_update_script, prepare_update_url
from best_practices_mcp.badgeapp import BadgeAppClient
from best_practices_mcp.badges import get_project_badge_status, get_project_badge_svg
from best_practices_mcp.contracts import validate_input
from best_practices_mcp.criteria import get_criteria
from best_practices_mcp.drafts import build_draft, check_identity, normalize_draft
from best_practices_mcp.errors import DomainError
from best_practices_mcp.http import BadgeAppHTTP
from best_practices_mcp.sdk_adapter import tool_definition, tool_result
from best_practices_mcp.storage import DraftStore, resolve_data_root
from best_practices_mcp.validation import validate_draft

READ_TOOLS = {
    "get_criteria": (
        "Read packaged official criteria and provenance offline, by level and criterion."
    ),
    "find_project": (
        "Find public BadgeApp project candidates by ID, repository/homepage URL, or text. "
        "Choose an entry explicitly; registration is outside this server."
    ),
    "get_project_progress": (
        "Read a selected BadgeApp project's saved progress and answers from its public project "
        "record. With no level, returns percentage summaries across all six supported levels. "
        "With a level, includes that level's progress and criterion answers; criterion_ids narrows "
        "the returned criteria. Includes source and observation provenance. Compact badge-family "
        "status and project-record update time are available through get_project_badge_status; "
        "SVG badges and README embedding are available through get_project_badge_svg."
    ),
    "get_project_badge_status": (
        "Return a compact public badge-status observation for one selected BadgeApp project "
        "from the OpenSSF Best Practices Badge API (https://www.bestpractices.dev). Includes "
        "project identity, effective badge family, reported badge level, family-specific progress, "
        "project-record update time and source/fetch metadata. The family defaults to Best "
        "Practices, which reports tiered progress; Baseline reports level-1 completion. Responses "
        "may be cached, and update time does not establish whether proposed answers were saved. "
        "All-level summaries, individual-level progress and saved criterion answers are available "
        "through get_project_progress; SVG badges and README embedding are available through "
        "get_project_badge_svg."
    ),
    "get_project_badge_svg": (
        "Retrieve an SVG badge and Markdown embed snippet for one selected BadgeApp project "
        "and explicit badge family from the OpenSSF Best Practices Badge API "
        "(https://www.bestpractices.dev). Returns the SVG text as a snapshot, its media type, "
        "dynamic image and project-page URLs, and source/fetch metadata. The dynamic URL lets "
        "README images reflect later badge changes. Does not render the SVG or edit files. "
        "Compact badge state, progress and update time are available through "
        "get_project_badge_status; detailed saved answers are available through "
        "get_project_progress."
    ),
}


DOCUMENT_TOOLS = {
    "build_draft": "Patch a caller-owned document without storage or network.",
    "validate_draft": "Check supplied answers mechanically against pinned criteria offline.",
    "prepare_update_url": (
        "Prepare a BadgeApp edit URL and included/excluded field report. "
        "Verify the target by public read. "
        "Supplied text is encoded without modification. BadgeApp documents trimming leading "
        "and trailing whitespace from URL-proposed justification text when applying it "
        "to the edit form. "
        "Does not open or save it."
    ),
    "prepare_update_script": (
        "Prepare a guarded form-fill script and included/excluded field report. "
        "Does not execute or save it."
    ),
}

STORAGE_TOOLS = {
    "read_draft": "Read a complete project-keyed local draft without creating files.",
    "update_draft": (
        "Patch a project-keyed local draft atomically, creating it if absent. "
        "No BadgeApp write. After an uncertain outcome, read the draft instead of retrying."
    ),
}

IMPLEMENTED_TOOLS = {**READ_TOOLS, **DOCUMENT_TOOLS, **STORAGE_TOOLS}


class BestPracticesServer(MCPServer):
    """Adapt generated contracts through public SDK handler extension points."""

    def __init__(self, *args, storage: DraftStore, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = storage

    async def list_tools(self) -> list[Tool]:
        definitions = [
            tool_definition(name, description) for name, description in IMPLEMENTED_TOOLS.items()
        ]
        return sorted([*definitions, *await super().list_tools()], key=lambda tool: tool.name)

    async def call_tool(
        self, name: str, arguments: dict, context: Context | None = None
    ) -> CallToolResult | InputRequiredResult:
        if name in IMPLEMENTED_TOOLS:
            return await self._execute_tool(name, arguments, context)
        if name not in {tool.name for tool in await super().list_tools()}:
            raise MCPError(code=-32602, message="Unknown tool")
        return await super().call_tool(name, arguments, context)

    async def _execute_tool(
        self, name: str, arguments: dict, context: Context | None
    ) -> CallToolResult:
        try:
            values = validate_input(name, arguments).model_dump()
        except ValidationError as error:
            # Match SDK argument-validation behavior, without echoing input values.
            fields = sorted({str(item["loc"][0]) for item in error.errors() if item["loc"]})
            raise ToolError(
                f"Invalid arguments for {name}; check fields: {', '.join(fields)}."
            ) from None
        try:
            payload = await self._payload(name, values, context)
            return tool_result(name, payload)
        except DomainError as error:
            return tool_result(name, error.to_payload())
        except Exception:
            error = DomainError(
                "internal_error",
                "The tool operation could not be completed.",
                recovery=(
                    "The update outcome may be uncertain. Use read_draft to inspect the project "
                    "before deciding on another patch; do not automatically retry."
                    if name == "update_draft"
                    else "Retry the operation; report the tool name if the error persists."
                ),
            )
            return tool_result(name, error.to_payload())

    async def _payload(self, name: str, values: dict, context: Context | None) -> dict:
        if name == "get_criteria":
            return get_criteria(**values)
        if name == "build_draft":
            return build_draft(**values)
        if name == "read_draft":
            return await self.storage.read(**values)
        if name == "update_draft":
            return await self.storage.update(**values)
        if name in DOCUMENT_TOOLS:
            return await self._document_payload(name, values, context)
        return await self._read_payload(name, values, context)

    async def _read_payload(self, name: str, values: dict, context: Context | None) -> dict:
        if context is None:
            raise RuntimeError("Network tools require the running server lifespan.")
        client = context.request_context.lifespan_context
        if name == "get_project_badge_status":
            return await get_project_badge_status(client.http, **values)
        if name == "get_project_badge_svg":
            return await get_project_badge_svg(client.http, **values)
        if name == "find_project":
            return await client.find_project(**values)
        return await client.get_project_progress(**values)

    async def _document_payload(self, name: str, values: dict, context: Context | None) -> dict:
        source = {"kind": "explicit", "location": None}
        if "draft" not in values:
            stored = await self.storage.read(values["project_id"])
            values["draft"] = stored["draft"]
            source = {"kind": "stored", "location": stored["location"]}
        values["draft"] = normalize_draft(values["draft"])
        check_identity(values["project_id"], values["draft"])
        if name == "validate_draft":
            result = validate_draft(**values)
        else:
            result = await self._artifact_payload(name, values, context)
        result["draft_source"] = source
        if source["kind"] == "stored":
            result["identity"]["association"] = "storage_key"
        return result

    async def _artifact_payload(self, name: str, values: dict, context: Context | None) -> dict:
        if context is None:
            raise RuntimeError("Network tools require the running server lifespan.")
        client = context.request_context.lifespan_context
        record, observation = await client.get_project_snapshot(values["project_id"])
        generator = prepare_update_url if name == "prepare_update_url" else prepare_update_script
        return generator(**values, record=record, observation=observation)


def create_server(
    *, http_factory: Callable[[], BadgeAppHTTP] = BadgeAppHTTP, data_root: Path | None = None
) -> MCPServer:
    """Build all eleven tools; factory/root injection supports isolated offline tests."""
    storage = DraftStore(resolve_data_root() if data_root is None else data_root)

    @asynccontextmanager
    async def lifespan(_server: MCPServer):
        async with http_factory() as http:
            yield BadgeAppClient(http)

    return BestPracticesServer(
        "bestpractices-mcp",
        storage=storage,
        version=__version__,
        log_level="WARNING",
        lifespan=lifespan,
        cache_hints={
            "server/discover": CacheHint(ttl_ms=0, scope="public"),
            "tools/list": CacheHint(ttl_ms=0, scope="public"),
        },
        instructions=(
            "BadgeApp reads, caller-owned document tools and optional project-keyed local drafts. "
            "Resolve and explicitly select an existing project before "
            "application work. Catalog wording is pinned, "
            "not necessarily current on the live site. "
            "Generated artifacts require host/owner review and do not save website changes. "
            "Explicit draft inputs bypass storage. Omitted drafts read the selected project file. "
            "Only update_draft creates or writes local storage. Avoid concurrent external or "
            "cross-process writers; after an uncertain update, read before deciding what to do."
        ),
    )
