# MCP schema compatibility

This document explains three choices in the tool schemas and says how they are checked. The server publishes JSON Schema 2020-12 input and output schemas through the official MCP Python SDK.

## Declared schemas and accepted input

A declared input schema describes the canonical form of the arguments. Results always conform to their declared output schema.

Argument validation accepts two forms that the schema does not declare, because models often produce them:

- A `null` value for an optional argument is treated as an omitted argument. `draft` is the exception.
- `project_id` and `page` accept a whole number that is written as a decimal string or as a number such as `123.0`.

## Arbitrary JSON values

Drafts and saved answers can hold any JSON value, including fields that the server does not know. The schema for such a value must not narrow it.

Pydantic's default schema for an unrestricted value is `{}`. That schema is legal, but some clients handle an untyped schema badly. The server therefore declares an `anyOf` with six branches: null, Boolean, number, string, array and object. The set of accepted values is the same. The limits on size and depth still apply.

The server does this with Pydantic's `WithJsonSchema` annotation on the `JsonValue` type. The [SDK documentation](https://github.com/modelcontextprotocol/python-sdk/blob/2118f14f8a19bc158d8a1cf90af58d85d187f849/docs/advanced/header-parameters.md#L25) shows the annotation. The six-branch declaration is this project's choice.

## Object-root results

Every result is an object, for success and for an error. The output schema is a union of the two, and it declares `type: object` at its root. Older MCP protocol versions require an object at the root of an output schema, and the [SDK](https://py.sdk.modelcontextprotocol.io/api/mcp_types/#mcp_types.Tool.output_schema) applies that requirement to clients that use them.

## Checks

- `make test-contract` checks the input and output schemas, the accepted JSON kinds and every result variant.
- The stdio tests check typed results, the equivalent text content and error signaling, for a current client and for a client that uses an older protocol version.
- The [Inspector CLI check](../testing/inspector-qa.md#repeatable-cli-checks) lists the tools with an independent client. It should report no schema errors or warnings.

A passing Inspector check does not show that every provider's subset of JSON Schema accepts the schemas.
