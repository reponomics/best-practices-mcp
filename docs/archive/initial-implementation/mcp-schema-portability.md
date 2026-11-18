# Schema portability investigation and decisions

This historical record summarizes the M2 investigation on November 9, 2026 and the M5 discovery correction. The [maintained schema documentation](../../reference/schema-compatibility.md) defines the implemented pattern and current verification commands. Detailed comparative execution output is archived privately.

## Finding

Pydantic's original `JsonValue` schema was `{}`, a legal JSON Schema accepting any JSON value. Inspector warned that some clients mishandle this representation. This did not establish an MCP violation, and its suggested object-only replacement would have narrowed the server's deliberately arbitrary saved values and error details incorrectly.

A minimal locally authored control using the official SDK and Pydantic reproduced the warning. The two inspected official reference servers did not produce it. That comparison established a possible SDK/Pydantic path to the warning, not its prevalence across servers or a failure in those reference servers. Discovery checks did not invoke their data tools.

## Decision and SDK support

The existing runtime `JsonValue` validator was retained with Pydantic's public `WithJsonSchema` annotation. Explicit `anyOf` branches cover null, Boolean, number, string, array and object, with arbitrary JSON children. The declaration preserves the accepted JSON value set and existing bounds; no SDK patch or custom schema generator was introduced.

The [pinned SDK guide](https://github.com/modelcontextprotocol/python-sdk/blob/2118f14f8a19bc158d8a1cf90af58d85d187f849/docs/advanced/header-parameters.md#L25) and its [executable documentation test](https://github.com/modelcontextprotocol/python-sdk/blob/2118f14f8a19bc158d8a1cf90af58d85d187f849/tests/docs_src/test_header_parameters.py#L133) support the annotation mechanism. No exact six-kind recipe was found in that SDK's documentation; this declaration is a project choice following the supported mechanism. The header-parameter feature itself was not adopted.

Independent review verified runtime/schema agreement for scalar and nested JSON, both schema modes and all result variants. Inspector warnings were eliminated without changing tool behavior or dropping accepted kinds. No external-client failure was reproduced at that stage; independent-host qualification remained necessary.

## M5 legacy discovery correction

The actual Codex desktop host later failed discovery. A raw `2025-11-25` reproducer showed that the SDK required `outputSchema.type: object` at the root. Every success/error branch was already an object, so adding that root declaration preserved the accepted contract while satisfying the older SDK path. This was separate from the nested arbitrary-JSON declaration.

Modern and legacy stdio tests covered discovery, success, structured errors and text/JSON parity. Independent review reproduced failure without the declaration and successful calls with it, followed by actual desktop qualification. The baseline remained MCP 2026-07-28 and the nine-tool scope was unchanged. The [M5 milestone summary](milestones/M5.md) summarizes the resulting qualification.

References: [MCP JSON Schema requirements](https://modelcontextprotocol.io/specification/2026-07-28/basic#json-schema-usage), [JSON Schema basics](https://json-schema.org/understanding-json-schema/basics), [Inspector smoke-testing guidance](https://github.com/modelcontextprotocol/inspector/blob/main/docs/cli-smoke-testing.md), [Pydantic schema annotation](https://pydantic.dev/docs/validation/latest/concepts/json_schema/#withjsonschema-annotation), and [SDK object-root compatibility](https://py.sdk.modelcontextprotocol.io/api/mcp_types/#mcp_types.Tool.output_schema).
