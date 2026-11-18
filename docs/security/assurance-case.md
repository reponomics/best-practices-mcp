# Assurance case

This document argues that the server meets its [security requirements](security-requirements.md). It gives the trust boundaries, the threats that were considered, the design principles that were applied, and the common weaknesses that the implementation counters. [Architecture](../reference/architecture.md) describes the components that this document refers to.

## What is protected

- The user's machine and files.
- The drafts that the server stores.
- The user's badge entry on BadgeApp, including the account that can edit it.
- The BadgeApp service, which the server must not overload.
- The users who install a release.

## Trust boundaries

| Boundary | What crosses it | How the server treats it |
| --- | --- | --- |
| MCP host to server | Tool calls, whose arguments a model writes | Untrusted. Every call is validated. |
| BadgeApp to server | Project records, search results, badge images | Untrusted third-party content. It is bounded, checked for type and passed on as data. |
| Disk to server | Stored drafts | Untrusted on read. A stored draft passes the same checks as a draft in a tool call. |
| Server to browser | A proposal URL that a person opens | The person reviews and saves. The server takes no part in the authenticated session. |
| Release pipeline to user | The published package | The user can verify it. |

## Threats and responses

The impact is the worst outcome if the threat succeeded and nothing countered it.

| Threat | Impact | Response |
| --- | --- | --- |
| A model sends harmful arguments, by mistake or because injected text told it to | High. It could read or write files outside the data directory, or reach other hosts. | Input models are strict. The server accepts no file path and no URL to fetch. It runs no shell command and evaluates no code. |
| A request is steered to another host | High. It could reach a service on the user's network or send data to another party. | The origin is fixed. A URL in a search is only a query value. The client follows no redirect and allows only the documented routes. |
| A response is oversized, deeply nested or malformed | Medium. It could exhaust memory or crash the server. | The client limits the size, the JSON depth and the time. It rejects unexpected types. It rejects an SVG that has a DTD or entity declarations. |
| Text from BadgeApp tells a model to act | Medium. It could mislead the assistant into wrong answers or unrequested tool calls. | No tool can save to BadgeApp or act outside the data directory. The most that injected text can cause through this server is a public read, a change to a local draft, or a URL that a person must still review. |
| A badge entry changes without the owner's intent | High. A public badge entry could show false answers. | The server holds no credentials and has no save operation. A proposal replaces a saved answer only when the override is explicit. |
| A local file is replaced by a link, or a path escapes the data directory | High. It could overwrite or expose another file of the user. | Paths come from numeric IDs under an absolute root. The store refuses a link or a file of the wrong type. |
| A crash or two concurrent writes damage a draft | Low. The user could lose answers that are not yet saved on BadgeApp. | Writes are atomic, and each project has a lock. |
| The server overloads BadgeApp | High. It could degrade or deny the BadgeApp service for others. | All requests share one limiter. Retries are bounded, and the client waits when the site asks. |
| A dependency has a vulnerability | Medium to high. It depends on the flaw, and it could affect every installation. | The runtime dependencies are few and pinned. [Scans](../maintenance/dependencies.md#scanning) run on every change and every week. |
| The package is altered between source and user | High. It could run an attacker's code on a user's machine. | Releases are built in CI from a signed commit, published through trusted publishing with signed provenance, and kept immutable. See [releasing](../release/releasing.md). |

## Design principles

- **Economy of mechanism.** The server has a small, fixed set of tools, one HTTP client and one store. It keeps no state other than the drafts.
- **Fail-safe defaults.** Unknown arguments are rejected. A proposal overrides nothing unless the caller asks. A missing value is reported as missing and is never filled in.
- **Complete mediation.** Every tool call passes input validation. Every request goes through the one client, which applies the route check and the limits.
- **Least privilege.** The server has no credentials, makes only GET requests and writes only in its data directory. Each CI job has only the permissions that it needs.
- **Separation of privilege.** A change to a badge entry needs a person in a browser. A release needs passing checks and a maintainer's approval.
- **Open design.** The source, the contracts and this argument are public. Nothing depends on a secret.
- **Small attack surface.** The server listens on no port and parses only JSON and SVG.

## Common weaknesses

| Weakness | Why it does not apply, or how it is countered |
| --- | --- |
| Injection | The server builds no SQL, shell command or HTML. It percent-encodes every value in a proposal URL. |
| Server-side request forgery | The origin and the routes are fixed. |
| Path traversal | No path comes from input. |
| XML external entities | An SVG with a DTD or entity declarations is rejected. |
| Unsafe deserialization | The server reads only JSON. |
| Resource exhaustion | Sizes, depth, time, retries and request rate are bounded. |
| Hard-coded or leaked credentials | The server has none. Secret scanning and push protection cover the repository. |
| Missing certificate validation | The client uses the default TLS verification and ignores environment settings that could change it. |
| Information exposure in errors | An error does not repeat an argument value. |
| Memory safety | The server is written in Python and has no native code of its own. |

## Evidence

- The [test suite](../testing/testing.md) covers the validation rules, the limits, the route allowlist and the storage checks. Coverage has an enforced floor.
- [Fuzzing](../testing/fuzzing.md) exercises document parsing and proposal encoding.
- CodeQL analyzes the code on every change. mypy runs in strict mode.
- The [required checks](../maintenance/ci.md#required-checks) block a change that fails any of these.

## Limits

The requirements document lists what the server does not protect against. The main ones are the behavior of the host, the visibility of a proposal URL, and the lack of encryption for drafts.
