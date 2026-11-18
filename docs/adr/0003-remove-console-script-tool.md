# ADR 0003: Remove the browser-console script tool

Status: Accepted. Date: 2026-11-15.

## Context

`prepare_update_script` produces JavaScript for execution in an authenticated BadgeApp edit page. It was inherited from the predecessor plugin, where a local preview of a saved BadgeApp form imported the same generator to populate its controls. That preview architecture is not part of this stdio MCP server. The [original preview implementation](https://github.com/hesreallyhim/ossf-best-practices-plugin-dev/blob/1e5b5ac1578d9bd6faaa6aceb669474d390dd716/ossf-badge/scripts/generate_preview.py) describes itself as a dry run of the console script.

The predecessor's [August 29 instructions](https://github.com/hesreallyhim/ossf-best-practices-plugin-dev/blob/1e5b5ac1578d9bd6faaa6aceb669474d390dd716/ossf-badge/SKILL.md#L439-L442) explicitly called the script an unofficial convenience. A [subsequent refactor](https://github.com/hesreallyhim/ossf-best-practices-plugin-dev/commit/878e121a3693db72caa9118baecd0910b3fabaeb) misleadingly described the submission paths as official. Investigation of the upstream repository and its documentation at the time found no sanctioned console-paste integration procedure.

The original claim that proposal URLs could not replace justification wording while leaving its status unchanged was incorrect. Upstream already had a [regression test for that exact operation using an explicit override](https://github.com/ossf/best-practices-badge/blob/5b4cb83667d893707c8e07d8fd438604a30ba23a/test/controllers/projects_controller_test.rb#L3552-L3567). The predecessor [corrected its explanation on October 24](https://github.com/hesreallyhim/ossf-best-practices-plugin-dev/commit/86a4912187b3dfa034b9efd39d1a971ef15c2f9c).

The script can avoid URL-length constraints and assign text without URL-processing whitespace trimming. A [September 3 commit](https://github.com/hesreallyhim/ossf-best-practices-plugin-dev/commit/18cf85a7481e7b8f7d66caceba287bf47df2a819) records a long URL failing in use. These conveniences do not provide a necessary unique capability for this MCP or justify the additional execution boundary. They do not establish what BadgeApp will ultimately save.

The fixed template and JSON serialization constrain the implementation, but asking users to paste executable output into an authenticated browser encourages an unsafe general practice. It requires trust in the exact delivered code and depends on undocumented DOM details and page event handlers. The tool also brings a separate DOM test harness, synthetic forms, npm dependencies, and additional host and release-tooling branches. It is not fit for the project's purpose of preparing changes through documented upstream procedures. No exploitable defect is being asserted by this decision.

## Decision

Remove `prepare_update_script` completely in the next beta. The project is still in beta with no known external users; there will be no compatibility alias, deprecated registration, warning stub, legacy schema, or migration handler. The supported MCP surface becomes ten tools. `prepare_update_url` remains the supported update artifact, following upstream's [proposal interface](https://github.com/ossf/best-practices-badge/blob/868e1677339a3fdb48851b0c2ae8862c553115eb/docs/automation-proposals.md), with final review and saving outside the server.

Delete the generator, script-only models and contract fixtures, DOM tests and forms, npm manifests, and the mandatory Node test setup. Remove their consumers from package checks, Make targets, CI, dependency scanning, tooling inventories, and release-bundle inputs. Retain shared URL transfer logic, identity checks, document/storage semantics, response limits, and source provenance. Python dependencies still used elsewhere, including pre-commit's `nodeenv`, remain. Optional MCP Inspector usage may still require externally installed Node/npm.

Update maintained documentation and the current tool inventory. Preserve historical release facts and clearly identify obsolete planning and QA material; remove the archived executable fill script and resolve its documentation links. This decision supersedes the DOM-test Node/npm requirements in [ADR 0002](0002-development-toolchain.md), without changing its Python/uv/Make decisions. The existing release-verification workflow continues checking the actual published assets and needs no old/new inventory compatibility branch.

## Reference host boundary

Retiring the reference host is a separate follow-up. This change only removes its script command, script export option, and script-specific branches. Simplify dispatch where removal makes it unnecessary, but do not redesign the host, replace it with Inspector, or migrate its remaining coverage in this change.

Keep the host's working URL, document, and stored-draft workflows and their existing tests. In mixed tests, remove only script operations and assertions. Where a script artifact merely acts as test data for shared behavior, use a URL artifact and preserve the behavioral assertion. In particular, retain exact UTF-8 exports, overwrite refusal, subset selection, explicit-versus-stored draft handling, stale-artifact clearing, uncertain-write handling, restart persistence, and project isolation. Existing protocol and fresh-package coverage also remain.

## Verification and consequences

The diff should primarily delete code and configuration. Remove tests dedicated to the retired feature and update existing positive discovery/schema tests to describe the supported interface. Do not add permanent tests asserting that the old tool, files, commands, or dependencies are absent. Any temporary removal checks must be discarded before completion.

Run the existing contributor validation, coverage, installed wheel/sdist checks, and release-bundle checks with the reduced inputs. Check coverage of surviving behavior rather than preserving a test count or treating an improved aggregate percentage as proof that coverage was retained.

The [live-browser runbook](../testing/live-browser-qa.md) remains a release check for proposal URLs: field population and retention, explicit overrides, status/justification coupling, clearing text, whitespace handling, and review before saving. Remove only its console-script steps. Neither the loss of DOM tests nor a green CI run replaces these checks against the actual website.

Users lose the console bulk-fill convenience. Oversized proposals can be handled through smaller user-selected proposals, manual entry, or upstream's repository-file mechanism. This change adds no automatic batching, replacement browser automation, authenticated write tool, or new fallback interface. The later host-removal change must account separately for every surviving behavior whose coverage currently depends on that host.

## Appendix: Unknown-status resets and the earlier fallback rationale

Added 2026-11-16 following investigation of the upstream implementation and live edit-form behavior.

The inability to reset an existing status to unknown (`?`) through a proposal URL supplies additional, substantive justification for the earlier idea of a form-fill fallback. This is distinct from the mistaken claim, discussed above, that URLs could not replace justification wording while retaining the same status. An explicit override supports that wording change. An explicit override does not currently make an unknown-status reset apply.

The upstream public guide describes `?` as an intentional reset, distinguishing a user-directed URL proposal from a JSON placeholder that supplies no information. The implementation instead discards unknown status proposals before evaluating their override flags. Live previews confirmed that known statuses remained unchanged with explicit or wildcard overrides, including a case with an empty justification, while ordinary `Unmet` overrides worked. [ADR 0005](0005-proposal-intent-and-compatibility-warnings.md#context-and-observations) records the observations; the [upstream guard](https://github.com/ossf/best-practices-badge/blob/31325acd7963e0c9203da0ff798802a766237517/app/controllers/projects_controller.rb#L1857) explains the behavior. The original implementation supported resets, and [the March override redesign](https://github.com/ossf/best-practices-badge/commit/a2a123743db58034ea4ffc7e6a02b8a80343bd50) made unknown rejection unconditional while the public reset explanation remained. This is an implementation/documentation gap, rather than merely a misreading of an otherwise complete proposal interface.

Earlier planning contains both the general fallback rationale and awareness of this discrepancy. The [server-managed draft workflow](../archive/initial-implementation/badgeapp-mcp-spec.md#server-managed-project-drafts) calls for `prepare_update_script` when URL transfer cannot carry some changes. The [upstream baseline](../archive/initial-implementation/badgeapp-mcp-upstream-baseline.md#three-important-compatibility-distinctions) records that the guide promises resets while `build_url_proposals` discards unknown. However, the [form-fill script specification](../archive/initial-implementation/badgeapp-mcp-spec.md#form-fill-scripts) also explicitly excludes unknown-status resets, and the [historical transfer matrix](../archive/initial-implementation/badgeapp-mcp-transfer-rules.md) says to leave the status control alone. These records support the broader motivation for a fallback; they do not show that the removed MCP tool already provided reset support.

A form-fill mechanism designed to express an explicit reset could select the form's unknown control without passing through the URL proposal filter. That is a potential capability advantage beyond URL length or whitespace preservation. Smaller URLs cannot remedy this gap, and repository JSON also ignores unknown statuses. Direct manual editing remains available. A reusable draft containing `?` would still need to be distinguished from a user's explicit request to clear an existing answer, and any future mechanism would need its form behavior and save-time effects verified.

This evidence qualifies the assessment of what an alternative submission path might offer. It gives potential justification to the earlier inclusion of a script tool without resolving the separate execution-boundary, DOM-dependency, and maintenance concerns that motivated removal. The accepted decision remains in force; restoring a tool or adding explicit reset support would require a separate decision. The current URL tool preserves the supplied `?` and reports the observed limitation as specified in ADR 0005.

The discrepancy has been reported upstream in [ossf/best-practices-badge issue #3135](https://github.com/ossf/best-practices-badge/issues/3135), requesting clarification of whether to correct the documentation or change the enforced policy.
