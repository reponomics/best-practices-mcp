# Architecture and MCP implementation guidance

Historical initial-implementation record. This preserves planning and review context, including the implementation status at its original checkpoints. Use the [maintained documentation](../../README.md) for current behavior. Detailed execution reports and earlier versions are archived privately; milestone summaries retain substantive findings and outcomes.

Reviewed 2026-11-09. This document records the structure chosen for this project; the [specification](badgeapp-mcp-spec.md) defines product behavior. M1 adds contracts, an offline catalog, document parsing/normalization, SDK adaptation, and owner-QA tooling. M2 registers the three public-read tools and adds the terminal host read workflow. M3 adds pure document patching/validation, URL/script generation, and host document mode.

## Runtime choice

Use the official `mcp` package, pinned to `2.3.0` for the scaffold, with the SDK's `MCPServer` and local stdio transport. The project baseline is Python 3.11+. The SDK owns discovery, request metadata, typed protocol envelopes, and transport lifecycle. No additional MCP framework or manually implemented JSON-RPC layer is needed. Current SDK documentation uses `MCPServer`; older examples using `mcp.server.fastmcp.FastMCP` are not the API baseline for this project. [Official SDK](https://github.com/modelcontextprotocol/python-sdk), [running a server](https://py.sdk.modelcontextprotocol.io/run/)

Use a normal installable package with a `src/` layout and an installed console entry point. This makes tests exercise installed code and helps expose missing package data when building wheels. Development uses `venv`, pip, and the annotated Makefile. [PyPA layout guidance](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)

## MCP 2026-07-28 conformance baseline

Rechecked against the official latest specification on 2026-11-09; its latest URL resolves to [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28). The SDK, rather than application handlers, owns these protocol obligations. G1 must verify them at the stdio wire boundary, and G5 must verify interoperability with the independent host:

- Support `server/discover` and modern requests without an initialize/initialized handshake; each request declares its protocol version and client capabilities in `_meta`. Supply client/server identity through the SDK. Reject unsupported versions with the protocol-defined error. SDK legacy compatibility is not the v1 design baseline.
- Ordinary result envelopes carry `resultType: "complete"`. Application `schema_version: 1` is a domain payload version, not a substitute for the MCP protocol version or resultType.
- Keep tools/list deterministic and independent of connection history or project files. Persistent project drafts are explicit application data addressed by project_id, not protocol session state.
- Discovery and tool-list results carry `ttlMs` and `cacheScope`. Configure the pinned SDK with `CacheHint(ttl_ms=0, scope="public")`; its wire output uses cacheScope. These hints do not cache tools/call results.
- Publish JSON Schema 2020-12 input/output schemas. Because this design returns structured domain errors, each output schema includes both the success and error variants. Test schema conformance for both, plus equivalent JSON text fallback and the appropriate isError flag.
- Keep standard JSON-RPC protocol errors distinct from tool execution errors; SDK argument validation can itself return a tool error. Preserve protocol-clean stdout and stderr diagnostics.

The nine-tool scope needs no MRTR input requests, subscriptions, tasks extension, resources, prompts, sampling, or HTTP transport. Their absence is compatible with the selected capability set; do not add them merely to use newer protocol features. See [versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning), [key changes](https://modelcontextprotocol.io/specification/2026-07-28/changelog), [tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), and [caching](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching).

## Current implementation

```text
pyproject.toml                 Packaging, dependency pins, development configuration
Makefile                       Setup, check, test, format, build, run, example
src/best_practices_mcp/
  __init__.py                  Package identity/version
  __main__.py                  CLI and stdio startup
  server.py                    Seven-tool composition, lifespan and SDK adaptation
  models.py, contracts.py       Nine strict tool schemas and typed result variants
  documents.py, errors.py       Bounded JSON/alias normalization and domain errors
  criteria.py, data/            Offline six-level catalog and provenance/license
  sdk_adapter.py               Typed SDK tool descriptions/results
  http.py, badgeapp.py           Shared bounded GET transport and public-record mapping
examples/host.py               Independent terminal MCP client read/document workflow
examples/m1_catalog.py         Offline core demonstration for owner verification
scripts/                      Reproducible catalog, offline package and HTML QA tools
vendor/badgeapp/               Pinned development inputs and upstream oracle sources
tests/test_stdio.py            Real subprocess protocol smoke tests
docs/                         Specification, decisions, implementation plan, QA reports
```

Seven implemented tools are advertised. Discovery stays deterministic regardless of project data or local files; only read_draft and update_draft remain absent until M4.

## Grow by responsibility

Add these modules as their features are implemented, rather than creating empty abstractions now:

| Responsibility                       | Planned module                         | Boundary                                                                                                                      |
| ------------------------------------ | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Tool registration and SDK adaptation | `server.py`, then `tools.py` if useful | Typed inputs/outputs, effect annotations, domain-error translation; delegate application logic.                               |
| Public contract models               | `models.py`                            | Shared input/result models; distinguish absent `draft` from explicit `{}` and reject `null`.                                  |
| Catalog access                       | `criteria.py`, packaged `data/`        | Generated, revisioned, level-qualified catalog; runtime lookup remains offline.                                               |
| Public BadgeApp reads                | `http.py`, `badgeapp.py`               | Shared async HTTP client, finite timeouts, GET retry policy, pacing, observation provenance.                                  |
| Pure document operations             | `drafts.py`                            | Field normalization, patches, structural checks, preservation of unrelated fields; no filesystem or SDK dependency.           |
| Mechanical checks                    | `validation.py`                        | Selected-level catalog flags and text checks only; no network access and no generation gate.                                  |
| Artifact construction                | `proposals.py`, `scripts.py`           | Document plus observed project state to exact artifacts and transfer reports; no browser operations.                          |
| Local persistence                    | `storage.py`                           | Project paths, one process-local guard per project, read/patch/check/atomic replace; no cross-process lock or revision token. |

Keep business rules callable without an MCP host. The MCP layer composes the catalog, API adapter, and optional file store. M2 uses the SDK server lifespan to create and close one HTTP client and shared request limiter for all public reads. Do not add a dependency-injection framework or a session/project registry. [SDK lifespan](https://py.sdk.modelcontextprotocol.io/handlers/lifespan/)

Badge Buddy code may inform the implementation, but should be adapted with attribution and upstream compatibility fixtures rather than imported from a sibling checkout. In particular, the plugin's registry and synchronization lifecycle are outside this design.

## Tool contracts

The maintained [design decision on human review and saving](../../reference/design.md#prepare-changes-leave-the-final-save-to-the-human) explains why the bounded tool surface excludes direct authenticated API saves despite upstream documenting REST writes. Draft persistence is local, and generated artifacts prepare a form for human review without submitting it.

Use typed parameters and explicit result models so the SDK can generate input/output schemas. Return artifacts as structured data and let the host decide how to display or open them. Preserve the SDK-supported text representation where necessary for host compatibility, without manually duplicating wire envelopes. Keep protocol/schema errors distinct from application errors and normal results containing validation findings. [Structured output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/), [MCP tool results](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#tool-result)

For intentionally arbitrary JSON, reuse `models.JsonValue`: Pydantic runtime JsonValue plus the public WithJsonSchema annotation, with explicit single-type `anyOf` branches and unchanged collection/value preservation. The MCP SDK documents and tests this annotation mechanism, although our exact six-kind schema is a project choice. Prefer concrete types for known fields. The [investigation](mcp-schema-portability.md#decision-and-sdk-support) records the source evidence; the [plan's schema checks](badgeapp-mcp-implementation-plan.md#schema-design-and-compatibility-checks) require model/schema agreement, reviewed Inspector findings and independent-host qualification. Schema overrides are declarations to verify, not replacements for runtime validation.

Advertise the same stable nine-tool surface once implemented, independently of local project files. Describe actual effects: `update_draft` writes a local file, generators read public data and return artifacts, and validation is local. Read-only hints describe server effects, not what a host might later do with a returned script. All project-specific calls contain their own project target; no active-project session is introduced.

Only `update_draft` creates storage. A per-project in-memory mutex protects that single read/patch/write operation; it imposes no required order on client requests. The spec explicitly excludes coordination between separate server processes. Its exact boundary is documented in the [concurrency decision](badgeapp-mcp-concurrency-review.md).

Do not add resources, prompts, streaming, model sampling, authentication, remote transport, telemetry, or output-format options merely because the SDK supports them. Add protocol features only when an agreed workflow requires them. Keep stdout reserved for MCP and avoid logging document contents or full proposal URLs.

## Test strategy and stopping point

The scaffold smoke tests launch the installed CLI as a subprocess, exercise MCP discovery/tool listing with a timeout, and check that startup does not create storage. Building a wheel and running it outside the source tree checks the installable entry point. These tests establish protocol/package plumbing only; they do not validate the application specification.

During implementation, add deterministic domain tests for patches and transfer precedence, adapter fixtures for public reads, failure-injection tests for atomic storage, and actual MCP contract tests for typed results/errors. Exercise packaged criteria from a built wheel. Keep live BadgeApp reads separate from the default test suite; production saves are unnecessary.

The example host must use the public MCP client rather than importing server internals. Its implemented read workflow will grow into the document/storage workflow described in the [implementation plan](badgeapp-mcp-implementation-plan.md), including both explicit documents and project-keyed storage. Validate against an independent host before release; the SDK client alone does not prove that compatibility. [SDK client](https://py.sdk.modelcontextprotocol.io/client/)

**Current stop:** M2 implements public reads, live registration of the three read tools, and the reference-host read workflow. Draft mutation/storage, validation, generators, and the remaining host workflow are M3–M5 work. The [contract](badgeapp-mcp-contracts.md) fixes payloads, limits and edge cases; the [source baseline](badgeapp-mcp-upstream-baseline.md) identifies fixture requirements. Each milestone report establishes its verification status.

## M1 integration decisions

The pinned SDK high-level server treats unknown tool names as tool errors by default. A small subclass overrides the public call_tool method to raise the SDK's MCPError(-32602) for unknown names and delegates known names unchanged; it also sorts discovery deterministically. Real stdio tests distinguish unknown-name protocol errors from known-tool structured execution failures. This uses SDK exception/result machinery rather than a custom JSON-RPC layer.

M1 uses Pydantic 2.14.3 explicitly for strict models and its public MISSING sentinel. The SDK adapter validates both output variants and measures the SDK result including matching JSON text and server-identity metadata. Catalog generation uses development-only PyYAML 6.0.3 and the vendored source manifest, while runtime lookup uses standard-library JSON/importlib.resources. The Ruby oracle is an optional development diagnostic executing pinned upstream methods. Required catalog tests read the YAML/locale inputs and check the agreed semantics directly; Ruby-derived behavioral comparisons live under `tests/optional/`. The generator's digest and fixed snapshot-generation timestamp make checked-in catalog regeneration byte-reproducible.


## M2 integration decisions

The read handlers extend the SDK's public list_tools/call_tool interfaces and use the same M1 input/output models, error adapter and wire-envelope machinery. The lifespan context owns BadgeAppClient and its one BadgeAppHTTP instance; get_criteria reads only packaged data. Direct HTTPX2 use is pinned as a runtime dependency, even though the SDK also depends on it. Test-only factory injection supplies MockTransport without exposing arbitrary origins through the CLI.

Requests use the fixed HTTPS production origin and documented JSON paths. Query keys are sorted and spaces encoded as `%20`, matching the pinned upstream controller's Addressable canonicalization before sending the request, so expected search operations need no redirect following. One shared limiter spaces attempt starts by at least one second and respects shared Retry-After cooldowns; thirty seconds bounds queueing, retries and response consumption. A bounded stream reader and strict JSON decoder reject oversized, malformed or ambiguous bodies; cookies, credentials, environment proxies and redirect following are disabled.

The mapper retains upstream candidate order and ambiguity, reports uncertain pagination rather than guessing completion, and checks next links against the same origin/path/query. Saved answer absence remains distinct from a present null or unknown status; aliases are normalized without inventing answers. The reference host owns selection and workflow state in memory, uses only the MCP client, and neither reads server storage nor implements server domain rules. These are implementation choices within the approved M2 scope.


## M3 integration decisions

`drafts.py` owns pure patch/shape/identity logic; `validation.py` owns optional represented-answer checks. `transfer.py` shares eligibility, outcome aggregation and documented edit-form predictions between `proposals.py` and `scripts.py`; `artifacts.py` supplies their entry points. These cores have no network, storage, authentication or browser execution. `server.py` resolves explicit inputs and uses the lifespan client for fresh public observations only when generating artifacts. The complete-record snapshot adapter alone treats omitted known justifications as blank because the pinned JSON view deliberately omits them; ordinary progress responses retain actual field absence, and missing statuses remain unknown.

All nine contract snapshots are unchanged. The omitted-draft branch remains unavailable until storage implementation and returns an actionable structured error without touching the filesystem. New server tooling does not add host workflow policy, validation gates or remote mutations. The terminal host owns in-memory documents, explicit selection/override prompts, optional validation, and exact file export; it calls only public MCP tools.

Node 24 and locked jsdom 31.0.0 are development-only dependencies for actual DOM execution of returned scripts against six source-derived synthetic forms. They are absent from the Python runtime and wheel. Tests cover all-controls preflight, target guards, replacement/events and partial runtime failures. The independent Ruby controller/predicate oracle uses retained hashed source and minimal Rails helper stand-ins; its comparisons and execution are both optional under `make oracle-check`. Required tests express the documented decision matrix and agreed compatibility cases directly. The stand-in parameters preserve Rails string/symbol lookup semantics.

No code models Save/Submit behavior. Live QA compares actual form state with the proposal expectations and treats subsequent saved state as a separate observation. The full pinned upstream docs explain the URL path; the script remains a project fallback rather than an upstream-supported interface.
