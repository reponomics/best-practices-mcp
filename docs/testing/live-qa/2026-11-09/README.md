# Live BadgeApp transfer checks in Chrome

These screenshots were captured during the **M3 live application QA checkpoint**, after document operations and artifact generation were implemented and before M4 added persistent drafts. The November 9, 2026 session exercised PolicyChecks (project 14356), silver level, in authenticated Chrome using MCP-generated proposals and a form-fill script.

The checks demonstrated edit-form behavior only. No Save or Submit action was taken. Temporary `Unmet` statuses and QA text were test inputs, not assessments of the project. The URLs and script below document the exercised inputs; current site data may produce different form results if they are replayed.

## Cases and associated artifacts

| Case | What the screenshots demonstrate | Screenshot | Associated URL or script |
| --- | --- | --- | --- |
| 1. Standalone justification without override | Existing explanation retained; status remained Met | [Retained explanation](01-no-override-retrospective.png) | Exact URL not retained. Proposal supplied `contribution_requirements_justification` without an override. |
| 2. Exact justification override | Proposed explanation displayed; status retained; automation marker present | [Overridden explanation](02-exact-override-retrospective.png) | Exact URL not retained. Proposal supplied `contribution_requirements_justification` and explicitly overrode that field. |
| 3. Divergent unforced status | Existing status and explanation retained despite an explicit justification override; divergent proposal notice displayed | [Blocked paired explanation](03-blocked-justification-retrospective.png) | Exact URL not retained. Proposal supplied `contribution_requirements_status=Unmet` and a justification, overriding only the justification. |
| 4. Unchanged forced status | Met remained selected; changed explanation retained its inherited override after the unchanged status was omitted from the URL | [Inherited override](04-inherited-override.png) | Exact URL not retained. The requested override named `contribution_requirements_status`; the effective emitted override named `contribution_requirements_justification`. |
| 5. Changed forced status | Both supplied controls replaced; expanded notice showed previous values | [Status and explanation replaced](05-changed-status-inherited-override.png) | [Exact proposal URL](05-proposal-url.txt) |
| 6. URL whitespace and Unicode | Form trimmed outer ASCII spaces while preserving internal text and Unicode | [URL text](06-whitespace-unicode.png) | [Exact proposal URL](06-proposal-url.txt), retaining the encoded leading/trailing spaces |
| 7. Script assignment | Exact raw text, including two leading and trailing spaces, preserved; console reported `filled` | [Selected text](07-script-whitespace-selection.png), [console result](07-script-console-second-execution.jpg) | [Historical generated script](https://github.com/reponomics/best-practices-mcp/blob/v0.2.0-beta.4/docs/live-qa/2026-11-09/07-fill.js) |
| 8. Multi-criterion preview | All 24 inspected controls across 12 criteria matched the expected fill, override, retention, blocking and unchanged cases | [Criterion screenshots below](#multi-criterion-preview) | [Exact proposal URL](08-proposal-url.txt) |
| 9. Discard and restore | Original form values restored after previews were discarded; no QA markers visible in the inspected form | [Restoration screenshots below](#baseline-restoration) | [Plain silver edit page](https://www.bestpractices.dev/en/projects/14356/silver/edit#all), without proposal parameters |

The first three images are retrospective captures from existing tabs. In case 7, the selected-text image records the first form observation; the console image records a second execution of the same script. The reopened-console image without a result is excluded. The notice in case 3 shows the supplied proposal, not an independent BadgeApp assessment.

### Multi-criterion preview

The bulk preview supplied 21 answer fields; its URL encoded 14 and omitted seven unchanged fields. Each screenshot is associated with the same [bulk proposal URL](08-proposal-url.txt).

| Criterion | Screenshot |
| --- | --- |
| Automated integration testing | [View](08-automated_integration_testing.png) |
| Contribution requirements | [View](08-contribution_requirements.png) |
| Cryptographic weaknesses | [View](08-crypto_weaknesses.png) |
| Developer Certificate of Origin | [View](08-dco.png) |
| Architecture documentation | [View](08-documentation_architecture.png) |
| Security documentation | [View](08-documentation_security.png) |
| Unsafe dynamic analysis | [View](08-dynamic_analysis_unsafe.png) |
| External dependencies | [View](08-external_dependencies.png) |
| Governance | [View](08-governance.png) |
| Report tracker | [View](08-report_tracker.png) |
| Tests documented and added | [View](08-tests_documented_added.png) |
| Strict warnings | [View](08-warnings_strict.png) |

### Baseline restoration

The restored form matched twelve baseline statuses and eight displayed justifications. Four preview-filled justifications were no longer displayed, so their hidden values were not asserted from browser inspection. A subsequent public MCP read matched the earlier silver baseline; this separate observation does not establish save-time behavior.

| Criterion | Screenshot |
| --- | --- |
| Contribution requirements | [View](09-baseline-contribution_requirements.png) |
| Cryptographic weaknesses | [View](09-baseline-crypto_weaknesses.png) |
| Developer Certificate of Origin | [View](09-baseline-dco.png) |
| Architecture documentation | [View](09-baseline-documentation_architecture.png) |
| Unsafe dynamic analysis | [View](09-baseline-dynamic_analysis_unsafe.png) |

The console-script tool has since been removed under [ADR 0003](../../../adr/0003-remove-console-script-tool.md). Case 7 records historical behavior and is no longer part of the live-browser runbook.

## Evidence treatment and limits

The browser images remove exactly the top 175 pixels containing browser chrome; the console image is uncropped. Retained pixels were verified unchanged and embedded metadata was removed. The originals remain in the private development archive. These images and associated artifacts are repository-only documentation, excluded from wheel and source distributions.

Clicking generated links in the Codex UI successfully opened the previews, demonstrating a working path beyond a host opening the browser directly. The separately reported Claude Code → TextEdit → browser copy-paste failure was not reproduced or diagnosed; equivalence with that path is not assumed.

## Attribution

The observed project record supplied the attribution “Please credit Really Him and the CII Best Practices badge contributors.” and license `CC-BY-3.0+`. These apply to reproduced project-entry material, separately from this server's MIT license. “CII Best Practices” is the legacy upstream name retained in that attribution. This independent Reponomics project is not affiliated with or endorsed by OpenSSF, the Linux Foundation, BadgeApp or its contributors.
