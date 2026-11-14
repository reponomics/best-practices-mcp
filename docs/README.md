# Documentation

This is an independent Reponomics project, not affiliated with, sponsored by, endorsed by, or an official project of OpenSSF, the Linux Foundation, or the OpenSSF Best Practices Badge (BadgeApp) project or its contributors. References identify compatibility and provenance.

## Maintained documentation

| Document | Purpose |
| --- | --- |
| [Roadmap](roadmap.md) | Planned work and proposals under consideration |
| [Contributing](../CONTRIBUTING.md) | Development setup, validation commands and MCP client tooling |
| [Server specification](specification.md) | Supported behavior, eleven tools and host/server responsibilities |
| [Design decisions](design.md) | Human-review boundary, deliberate exclusion of direct saves and documented-procedure authority |
| [ADR 0001: Badge image and status tools](adr/0001-badge-image-and-status-tools.md) | Accepted separation of SVG retrieval, compact status observations and detailed progress; reasons to keep update time and progress together |
| [Architecture](architecture.md) | Modules, data flow, protocol adaptation and persistence boundaries |
| [Implementation contracts](contracts.md) | Exact payloads, errors, size/network policies and edge cases |
| [Upstream compatibility](upstream-compatibility.md) | Source baseline, routes, catalog conventions and update procedure |
| [Transfer rules](transfer-rules.md) | Faithful artifact contents, explicit overrides, exclusions and script behavior |
| [Schema compatibility](schema-compatibility.md) | SDK-supported schema declarations and interoperability checks |
| [Testing policy](testing-policy.md) | Deterministic contract tests, defensive DOM tests and live compatibility evidence |
| [Live browser QA](live-browser-qa.md) | Local PolicyChecks URL/script checks after first publication and for subsequent release candidates |
| [CI and repository setup](ci.md) | Native compatibility matrix, security checks and service activation |
| [Release procedure](releasing.md) | Release Please, approvals, OIDC publication and published-package QA |

The [project README](../README.md) covers installation, host configuration and everyday use. The [contributor guide](../CONTRIBUTING.md) covers development commands. The [reference terminal host](../examples/host.py) demonstrates both explicit documents and optional server-managed storage using MCP calls.

## Historical records

[Initial implementation planning](planning/initial-implementation/README.md) preserves the original scope, reviews and development decisions. These historical records do not override the maintained documentation.

The [live Chrome QA record](live-qa/2026-11-09/README.md) includes the approved screenshots, associated retained proposal URLs/script, and the limits of the exercised transfer cases.
