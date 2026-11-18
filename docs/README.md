# Documentation

This is an independent Reponomics project, not affiliated with, sponsored by, endorsed by, or an official project of OpenSSF, the Linux Foundation, or the OpenSSF Best Practices Badge (BadgeApp) project or its contributors. References identify compatibility and provenance.

## Maintained documentation

| Document | Purpose |
| --- | --- |
| [Roadmap](roadmap.md) | Planned work and proposals under consideration |
| [MCP interaction log](interaction-log.md) | Working table of real sessions, intended to grow through voluntary user reports |
| [Contributing](../CONTRIBUTING.md) | Development setup, validation and submitting changes |
| [Server specification](specification.md) | Supported behavior, ten tools and host/server responsibilities |
| [Design decisions](design.md) | Human-review boundary, deliberate exclusion of direct saves and documented-procedure authority |
| [ADR 0001: Badge image and status tools](adr/0001-badge-image-and-status-tools.md) | Accepted separation of SVG retrieval from status; its compact status tool was later replaced by `get_project_status` |
| [ADR 0002: Development toolchain](adr/0002-development-toolchain.md) | Canonical cross-platform Make tasks, locked uv environments and bootstrap-tool audit inventory |
| [Architecture](architecture.md) | Modules, data flow, protocol adaptation and persistence boundaries |
| [Implementation contracts](contracts.md) | Exact payloads, errors, size/network policies and edge cases |
| [Upstream compatibility](upstream-compatibility.md) | Source baseline, routes, catalog conventions and update procedure |
| [Transfer rules](transfer-rules.md) | Faithful artifact contents, explicit overrides, and exclusions |
| [Schema compatibility](schema-compatibility.md) | SDK-supported schema declarations and interoperability checks |
| [Testing policy](testing-policy.md) | Deterministic contract tests and live compatibility evidence |
| [Inspector qualification](inspector-qa.md) | Independent-client walkthrough and CLI checks for an installed candidate |
| [Live browser QA](live-browser-qa.md) | Local PolicyChecks proposal-URL checks after first publication and for subsequent release candidates |
| [CI and repository setup](ci.md) | Native compatibility matrix, security checks and service activation |
| [Release procedure](releasing.md) | Release Please, approvals, OIDC publication and published-package QA |
| [Release verification](verification.md) | Consumer checks for asset integrity, authenticity, provenance, SBOMs and scan evidence |

The [project README](../README.md) covers installation, host configuration and everyday use. The [contributor guide](../CONTRIBUTING.md) covers development commands. [Inspector qualification](inspector-qa.md) covers explicit documents and optional server-managed storage through the public MCP interface.

## Historical records

Removal decisions and their implementation audit are retained for provenance, not as operating instructions:

- [Console-script removal decision](adr/0003-remove-console-script-tool.md)
- [Reference-host removal decision](adr/0004-remove-reference-host.md)
- [Reference-host removal audit](reference-host-removal-audit.md)

[Initial implementation planning](planning/initial-implementation/README.md) preserves the original scope, reviews and development decisions. These historical records do not override the maintained documentation.

The [live Chrome QA record](live-qa/2026-11-09/README.md) includes the approved screenshots, associated retained proposal URLs and historical script reference, and the limits of the exercised transfer cases.

The [Baseline Level 1 milestone](live-qa/2026-11-16/README.md) records the project's own application workflow through the MCP, maintainer submission, and confirmation of 100% saved completion.
