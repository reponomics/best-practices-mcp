"""SDK model adaptation for contracts; this module registers no tools."""

import json
from typing import Any

from mcp.server.mcpserver import Context
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from best_practices_mcp import __version__
from best_practices_mcp.badgeapp import BadgeAppClient
from best_practices_mcp.contracts import input_schema, output_schema, validate_output
from best_practices_mcp.documents import RESPONSE_LIMIT_BYTES
from best_practices_mcp.errors import DomainError
from best_practices_mcp.models import ErrorResult

# A request context of this server: its lifespan value is the BadgeApp client.
ServerContext = Context[BadgeAppClient, Any]

NETWORK_TOOLS = frozenset(
    {
        "find_project",
        "get_project_status",
        "get_project_answers",
        "get_project_badge_svg",
        "prepare_update_url",
    }
)
# Network reads that add no side effects when repeated, though their observations may change.
REPEATABLE_READS = frozenset({"get_project_status", "get_project_badge_svg"})
TITLES = {
    "get_criteria": "Get badge criteria",
    "find_project": "Find BadgeApp project",
    "get_project_status": "Get project status",
    "get_project_answers": "Get saved answers",
    "get_project_badge_svg": "Get badge SVG and README Markdown",
    "build_draft": "Build draft document",
    "read_draft": "Read stored draft",
    "update_draft": "Update stored draft",
    "validate_draft": "Validate draft",
    "prepare_update_url": "Prepare BadgeApp edit URL",
}


def tool_definition(name: str, description: str) -> Tool:
    """Build an SDK tool definition from its schemas and capability annotations."""
    mutation = name == "update_draft"
    return Tool(
        name=name,
        title=TITLES[name],
        description=description,
        input_schema=input_schema(name),
        output_schema=output_schema(name),
        annotations=ToolAnnotations(
            read_only_hint=not mutation,
            destructive_hint=mutation,
            # Preserve existing annotations on the previously published tools.
            idempotent_hint=name not in NETWORK_TOOLS or name in REPEATABLE_READS,
            open_world_hint=name in NETWORK_TOOLS,
        ),
    )


def result_bytes(result: CallToolResult) -> bytes:
    """Size the actual SDK result representation, excluding JSON-RPC framing."""
    return result.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8")


def tool_result(name: str, payload: dict[str, Any]) -> CallToolResult:
    """Validate both result variants and produce matching JSON/text channels."""
    validated = validate_output(name, payload)
    structured = validated.model_dump(mode="json")
    result = CallToolResult(
        content=[TextContent(type="text", text=json.dumps(structured, ensure_ascii=False))],
        structured_content=structured,
        is_error=isinstance(validated, ErrorResult),
        # Explicit SDK metadata prevents the transport adding unbudgeted identity bytes.
        _meta={
            "io.modelcontextprotocol/serverInfo": {
                "name": "bestpractices-mcp",
                "version": __version__,
            }
        },
    )
    if len(result_bytes(result)) > RESPONSE_LIMIT_BYTES:
        raise DomainError(
            "response_too_large",
            "The complete tool result exceeds the server response budget.",
            details={"limit_bytes": RESPONSE_LIMIT_BYTES},
            recovery=(
                "View the badge on BadgeApp's project page or report the oversized badge response."
                if name == "get_project_badge_svg"
                else "Request fewer criteria, index detail, or a smaller document."
            ),
        )
    return result
