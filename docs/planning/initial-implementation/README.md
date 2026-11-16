# Initial implementation records

These records preserve the planning, review and milestone history of the initial implementation. They are historical, including statements about what remained unimplemented at a particular checkpoint. The [maintained documentation](../../README.md) defines current behavior. References to development commit IDs identify the preserved development repository; those commits are not assumed to exist in the clean public history.

Detailed HTML QA reports, execution logs, test-count chronology and earlier document versions are archived privately. The concise milestone records retain design-relevant findings, fixes, qualification outcomes and limits. The milestone report generator and `demo-m*` commands have been retired. Commands and report paths in these historical plans describe the original process; use the [current validation commands](../../../CONTRIBUTING.md#validate-the-implementation) for maintained checks.

The optional Ruby comparisons and copied implementation sources described in these historical records were removed during pre-release cleanup. The investigation remains in the preserved development repository. Current verification follows the [testing policy](../../testing-policy.md); references here to removed test and vendor paths describe the earlier development state.

The console-script tool and its DOM test tooling were removed under [ADR 0003](../../adr/0003-remove-console-script-tool.md). References to them below describe historical scope, not supported functionality.

The reference terminal host was subsequently removed under [ADR 0004](../../adr/0004-remove-reference-host.md). Its commands and workflow tests below describe historical scope; use [Inspector qualification](../../inspector-qa.md) for the maintained independent-client procedure.

## Planning and review

| Record | Historical purpose |
| --- | --- |
| [Development context](development-context.md) | Extraction and adaptation from the exercised Badge Buddy CLI |
| [Specification](badgeapp-mcp-spec.md) | Initial bounded scope and host/server responsibilities |
| [Contracts](badgeapp-mcp-contracts.md) | Concrete payloads, edge cases, resource and network policies |
| [Architecture](architecture.md) | Initial runtime, SDK and module choices |
| [Implementation plan](badgeapp-mcp-implementation-plan.md) | Milestones, gates, reference host and verification process |
| [Upstream baseline](badgeapp-mcp-upstream-baseline.md) | Source pins, compatibility assumptions and fixture map |
| [Transfer rules](badgeapp-mcp-transfer-rules.md) | Proposal semantics and compatibility decisions |
| [Initial review](badgeapp-mcp-review.md) | Findings against the original proposal |
| [Review dispositions](badgeapp-mcp-review-response.md) | Accepted/rejected recommendations and applied corrections |
| [Concurrency decision](badgeapp-mcp-concurrency-review.md) | Internal guards and explicit cross-process boundary |
| [Readiness](badgeapp-mcp-readiness.md) | Bootstrap gaps, resolutions, preparation checklist and G0 review |
| [Schema investigation](mcp-schema-portability.md) | Portability warning, SDK mechanism and legacy discovery correction |
| [Testing-policy decision](testing-policy.md) | Required conformance authority and optional Ruby investigation |

## Milestone records

| Milestone | Outcome |
| --- | --- |
| [M0](milestones/M0.md) | Bounded plan specified and reviewed |
| [M1](milestones/M1.md) | Typed contracts, offline catalog and QA tooling |
| [M2](milestones/M2.md) | Public reads and reference-host read workflow |
| [M3](milestones/M3.md) | Document operations, validation and transfer artifacts; live Chrome checks |
| [M4](milestones/M4.md) | Optional project-keyed persistence and complete nine-tool surface |
| [M5](milestones/M5.md) | Native compatibility, installed packages, coverage and independent-host qualification |
| [M6](milestones/M6.md) | Publication preparation; extraction and release gates remain separate |
