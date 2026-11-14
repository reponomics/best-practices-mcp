# Architecture

The server is an installable Python package with a bounded eleven-tool interface over local stdio. Python 3.11 is the supported minimum. The official MCP Python SDK owns protocol handling; independent domain modules implement BadgeApp reads, document operations, artifact preparation and optional local persistence. The [specification](specification.md) defines behavior and the [contracts](contracts.md) define precise payloads and limits.

## Responsibilities and data flow

| Component | Responsibility |
| --- | --- |
| `server.py`, `__main__.py` | CLI startup, service lifecycle, eleven-tool registration and dispatch |
| `models.py`, `contracts.py`, `sdk_adapter.py` | Typed inputs/results, JSON Schema declarations, tool annotations, error and result-envelope adaptation |
| `criteria.py`, `data/` | Offline six-level catalog, source revision and notices |
| `documents.py`, `drafts.py` | Bounded JSON normalization, aliases, structural diagnostics and pure patches |
| `http.py`, `badgeapp.py`, `badges.py` | Shared bounded JSON/SVG GET transport, pacing/retries, public-record mapping and compact badge observations |
| `validation.py` | Optional mechanical checks using the selected level's catalog requirements |
| `transfer.py`, `artifacts.py`, `proposals.py`, `scripts.py` | Transfer eligibility, identity checks, field reports, exact proposal URLs and guarded form-fill scripts |
| `storage.py` | Project-keyed paths, process-local guards and atomic local draft replacement |
| `examples/host.py` | Reference terminal host using the public MCP client interface |

A host resolves and selects an existing BadgeApp project before application work. It can own a document and pass it explicitly, or use the optional project-keyed draft store. An explicit document, including `{}`, takes precedence over storage. Omitting a document reads one complete stored snapshot for that call. Each generator separately fetches a current public project observation, checks the registered target and any supplied identity provenance, and returns an artifact plus a field-level inclusion/exclusion report. Supplied answer values are not compared with the observation; every eligible field is encoded, including values equal to saved answers. There is no hidden active-project session or shared snapshot across separate calls.

Business rules remain callable without an MCP host. Services return domain values; the MCP boundary adapts them to typed protocol results and enforces complete serialized-result budgets. Structural/domain errors remain distinct from protocol errors and from successful validation results containing findings.

## Protocol and schema boundary

The conformance baseline is MCP **2026-07-28**, implemented through the pinned official SDK `2.3.0` and `MCPServer`. The SDK handles discovery, per-request metadata, result envelopes and transport lifecycle. Discovery and tool lists are deterministic and use `CacheHint(ttl_ms=0, scope="public")`; these hints do not cache tool-call results. Stdout contains only protocol traffic and diagnostics use stderr.

Known fields use concrete strict models. Intentionally arbitrary JSON uses the shared Pydantic `JsonValue` runtime type with its public `WithJsonSchema` annotation, explicitly declaring the six JSON kinds without narrowing accepted values. Success/error unions have an object root because every branch is an object; this also supports the SDK's legacy discovery requirements. [Schema compatibility](schema-compatibility.md) explains the supported customization and its verification boundary.

The implemented capability set needs no resources, prompts, sampling, subscriptions, task extension or HTTP transport. Project drafts are application data, not protocol session state. The [official SDK](https://github.com/modelcontextprotocol/python-sdk) and [MCP specification](https://modelcontextprotocol.io/specification/2026-07-28) are the protocol references.

## Public reads and transfer artifacts

One lifespan-managed asynchronous HTTP client and monotonic request limiter serve all public reads. Requests target fixed production BadgeApp JSON routes and explicit badge SVG routes, use bounded attempts/time/body size, respect shared cooldowns, and never fetch supplied repository or evidence URLs. Full-record observations carry source URL, fetch time and upstream attribution/license values. They are not silently synchronized into drafts. The compact badge adapter fetches one badge family per call, with a separate status result and SVG artifact result. It does not fetch the full project record to enrich either response. SVG text is returned unchanged as data after bounded UTF-8/XML validation; the server neither renders nor sanitizes it. Compact status separates service credit from unavailable project-entry attribution and preserves record update time independently of fetch time.

Validation is local and advisory. It neither checks claim truth nor gates artifact generation. URL generation follows the documented status-first proposal matrix and explicit compatibility choices; script generation uses guarded control replacement. Both preserve exact returned bytes. The host decides how to display, export or open them.

The MCP has no authenticated remote-write capability and generated artifacts do not submit forms. A user may authorize a host agent to click Save, but that delegation is outside this implementation. The [design decision](design.md#prepare-changes-leave-the-final-save-to-the-human) explains why final saving remains outside the tool surface. The server does not simulate Save/Submit outcomes from internal Ruby behavior.

## Optional local persistence

The store holds one multi-level `.bestpractices.json` per registered project under a default or explicitly configured data root. Startup validates configuration without creating files. Only `update_draft` creates directories or writes a draft. Complete reads preserve unfamiliar JSON and return structural diagnostics; updates reject invalid recognized fields and target mismatches before changing storage.

A per-project in-memory guard covers each read/patch/check/replace operation. The store checks document size and the prospective complete read/update responses, then uses a same-directory temporary file, flush/fsync and atomic replacement. Cancellation shielding retains the guard until replacement or cleanup completes. There is no cleanup after a successful replacement that could falsely claim rollback.

This protects concurrent updates within one server process and prevents partial-file visibility. It does not coordinate independent servers or external editors, guarantee request-arrival order, or promise survival of sudden power loss. An uncertain write requires a fresh read before deciding whether to issue another patch. The reference host clears stale artifacts after an uncertain mutation and does not retry it automatically.

## Reference host and verification

The reference terminal host launches the server through the official MCP client; it does not import server internals or read draft files directly. Document mode supports local imports, edits, validation, artifact generation and exact exports. Stored mode is opt-in and uses MCP reads/patches for persistence, including explicit document subsets derived from a complete read. Its interactive choices are illustrative host policy, not new MCP requirements.

Required verification covers pure domain rules, controlled DOM execution, injected network/filesystem failures, real stdio discovery/calls, reference-host workflows and fresh wheel/sdist installation. The CI matrix covers Python 3.11/3.12 on native Linux, macOS and Windows. Synthetic DOM tests verify defensive script behavior; the [live browser runbook](live-browser-qa.md) checks current website compatibility. The [testing policy](testing-policy.md) defines the evidence boundaries. Coverage, package-verification and release results are written under ignored `build/coverage/`, `build/verification/` and `build/release/`, respectively.
