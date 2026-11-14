# MCP schema compatibility

The server uses the official Python MCP SDK and publishes JSON Schema 2020-12 input/output schemas. Runtime validation and declared schemas must describe the same accepted values. Inspector portability warnings are useful compatibility feedback, but are not by themselves proof of an MCP specification violation.

## Arbitrary JSON values

The shared `JsonValue` type deliberately preserves all valid JSON kinds, including unfamiliar nested document fields and unexpected saved progress values. Pydantic's unrestricted `{}` schema is legal, but Inspector can warn that some clients mishandle untyped schemas. Replacing it with an object-only declaration would incorrectly narrow this contract.

The implementation retains Pydantic's runtime `JsonValue` validator and uses its public `WithJsonSchema` annotation to declare `anyOf` branches for null, Boolean, number, string, array and object. Arrays and objects permit arbitrary JSON children; number includes integer. This changes the schema representation without changing the accepted JSON value set. Existing byte/depth bounds and non-finite/invalid-Unicode rejection remain in force.

The [pinned SDK documentation](https://github.com/modelcontextprotocol/python-sdk/blob/2118f14f8a19bc158d8a1cf90af58d85d187f849/docs/advanced/header-parameters.md#L25) demonstrates `WithJsonSchema`, and its [documentation test](https://github.com/modelcontextprotocol/python-sdk/blob/2118f14f8a19bc158d8a1cf90af58d85d187f849/tests/docs_src/test_header_parameters.py#L133) exercises the annotation through tool registration. That supports the mechanism; the exact six-kind declaration is this project's design choice, not a quoted SDK recipe. See also [Pydantic's annotation guidance](https://pydantic.dev/docs/validation/latest/concepts/json_schema/#withjsonschema-annotation).

## Object-root results

All success/error result branches are objects. Declaring `type: object` at the union root preserves that contract and satisfies the SDK's object-root requirement for older protocol versions through `2025-11-25`. The baseline remains `2026-07-28`; this declaration does not add a separate legacy application protocol. Modern and legacy stdio regressions check discovery, success and structured errors. The [SDK Tool documentation](https://py.sdk.modelcontextprotocol.io/api/mcp_types/#mcp_types.Tool.output_schema) describes the version-dependent requirement.

## Verification

`make test-contract` verifies input and serialization schemas, accepted JSON kinds, nested collections and all tool result variants. Real stdio tests verify typed results, equivalent text fallback and error signaling. Independent-host qualification checks the installed server rather than relying solely on an SDK example.

For an optional Inspector check after setup, run:

```sh
npx -y @modelcontextprotocol/inspector@2.14.0 --cli \
  ./venv/bin/bestpractices-mcp --protocol-era modern \
  --method tools/list --strict --format json
```

Expected discovery is eleven tools with no schema errors or warnings. Inspector may download its npm package; server discovery itself is offline. A successful check does not guarantee acceptance by every provider-specific schema subset. Inspector's [smoke-testing guidance](https://github.com/modelcontextprotocol/inspector/blob/main/docs/cli-smoke-testing.md) distinguishes portability lint from full conformance testing.
