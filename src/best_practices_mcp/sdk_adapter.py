"""SDK model adaptation for contracts; this module registers no tools."""

import json

from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from best_practices_mcp import __version__
from best_practices_mcp.contracts import input_schema, output_schema, validate_output
from best_practices_mcp.documents import RESPONSE_LIMIT_BYTES
from best_practices_mcp.errors import DomainError
from best_practices_mcp.models import ErrorResult

NETWORK_TOOLS = frozenset(
    {
        "find_project",
        "get_project_progress",
        "get_project_badge_status",
        "get_project_badge_svg",
        "prepare_update_url",
        "prepare_update_script",
    }
)
BADGE_TITLES = {
    "get_project_badge_status": "Get project badge status",
    "get_project_badge_svg": "Get project badge SVG",
}


def tool_definition(name: str, description: str) -> Tool:
    """Build an SDK tool definition from its schemas and capability annotations."""
    mutation = name == "update_draft"
    return Tool(
        name=name,
        title=BADGE_TITLES.get(name),
        description=description,
        input_schema=input_schema(name),
        output_schema=output_schema(name),
        annotations=ToolAnnotations(
            read_only_hint=not mutation,
            destructive_hint=mutation,
            # Badge reads have no additional side effects; their observations may change.
            # Preserve existing annotations on the previously published tools.
            idempotent_hint=name not in NETWORK_TOOLS or name in BADGE_TITLES,
            open_world_hint=name in NETWORK_TOOLS,
        ),
    )


def result_bytes(result: CallToolResult) -> bytes:
    """Size the actual SDK result representation, excluding JSON-RPC framing."""
    return result.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8")


def tool_result(name: str, payload: dict) -> CallToolResult:
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
                if name in BADGE_TITLES
                else "Request fewer criteria or reduce the document size."
            ),
        )
    return result
