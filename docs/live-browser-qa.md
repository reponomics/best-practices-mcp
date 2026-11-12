# Local live browser QA

Exercise the published beta before promoting it to stable. Repeat this check for subsequent release candidates. Use an MCP host connected to the exact installed candidate, an authenticated Chrome session, and the [PolicyChecks silver form](https://www.bestpractices.dev/en/projects/14356/silver/edit). This is a short supervised integration check, not an automated production save. Discard the previews when finished.

## Preparation

Follow the [published-package checks](releasing.md#verify-the-published-beta-and-advance-to-stable) first. Record the server version, distribution identity, host, browser and date in `INTERNAL/live-qa/<version>/`. Keep generated tool arguments/results, exact URLs/script and screenshots there; do not capture credentials or authentication cookies. The existing [Chrome record](live-qa/2026-11-09/README.md) illustrates useful evidence but does not replace a fresh check.

Through the host, call `get_project_progress` with `{"project_id":14356,"level":"silver"}` and `get_criteria` with `{"level":"silver"}`. Verify the returned project is `reponomics/PolicyChecks`. Open the plain edit page and record the actual starting values. If page automation changes a value relative to the public response, choose another field for that condition or record the discrepancy and investigate. The MCP does not predict form state; the table below derives browser checks from upstream's documented proposal procedures and the actual baseline.

Choose distinct silver criteria with the baseline conditions below, using canonical field names returned by `get_criteria`. Selection is deliberate because a project's answers change over time. Possible candidates include `contribution_requirements`, `crypto_weaknesses`, `external_dependencies`, `dco` and `documentation_architecture`; inspect their current states before assigning roles. If a required condition is unavailable, mark that case unexercised and select another authorized application before claiming complete coverage.

| Role | Baseline and supplied fields | Browser check after opening URL A |
| --- | --- | --- |
| A: blocked pair | Existing known status; propose a different known status and new justification; override only the justification | Existing status and justification retained; justification is blocked by the unforced differing status |
| B: status override | Existing known status and nonblank justification; supply the same status and new justification; override the status | Both fields remain in the URL. BadgeApp retains the same status and replaces the justification through its documented status-override implication |
| C: blank pair | Blank or unknown status and blank justification; supply `Unmet` and new justification, no override | Both supplied values fill |
| D: retained wording | Existing nonblank justification; supply different text without a status or override | Existing wording retained |
| E: clear wording | Existing nonblank justification; supply an empty string and override that justification | Justification cleared |
| F: matching values | Supply a known status and justification exactly equal to their current values, without overrides | Both fields remain in the URL; displayed values stay the same |

Use unmistakable preview text, for example the exact string `  QA preview only — not saved. https://github.com/reponomics/PolicyChecks?q=a&x=2#qa  `, for each new nonempty justification. This combines Unicode, URL punctuation, and leading/trailing ASCII spaces. The six roles supply at least ten fields in the same artifact. Additional silver standalone justifications may be included with explicit overrides. They are temporary test values, not criterion assessments.

## 1. Two combined proposal URLs

Build a flat document using `build_draft` with `draft: {}` and the chosen fields in `changes`; retain its returned `draft`. Call `prepare_update_url` with `project_id: 14356`, `level: "silver"`, that explicit `draft`, and `override_fields` containing A's justification, B's status, E's justification and any explicitly selected additional fields. Substitute actual canonical names; the role letters above are not tool arguments.

Retain the returned field-level `transfer`, `requested_overrides`, `effective_overrides` and exact `artifact.url`. Check that every eligible supplied field is marked `encoded` and represented exactly in the decoded query, including F's matching values and all whitespace. The `overrides` parameter must contain only the explicit requested names; B's justification must not be added automatically. The report must contain no expected-form classifications. Open URL A by clicking the host-displayed link and compare all selected controls with the table. Verify BadgeApp's documented trimming of leading/trailing spaces in newly applied justification text, while interior text and punctuation survive. Distinguish the exact encoded value from the value displayed by the site. Check untouched neighboring controls as well. An unexpected `artifact: null`, exclusion, or browser result is a finding to resolve, not permission to hand-edit the generated URL.

Generate URL B from the same document, adding A's status to `override_fields`. Verify that the supplied field values are identical between URLs and only the explicit override list changes. BadgeApp's documented status-override behavior should now replace A's status and paired justification. Open the exact returned URL through a second delivery route, such as copying the raw URL directly into Chrome's address bar; this tests that a host opening the browser is not the only usable route. Compare the remaining fields again. Each URL starts from the site's saved baseline; do not save between cases. Record any automation notice separately from the proposed changes.

## 2. One generated script

Call `prepare_update_script` with `project_id: 14356`, `level: "silver"` and the same explicit `draft`. Save the exact `artifact.javascript` and read its returned instructions. Open the plain silver edit page again, then execute that script in the browser console. Confirm the report is `filled`, its reported fields agree with the emitted artifact, and the corresponding controls contain the supplied values: A and D are replaced without URL overrides, E is cleared, and new textarea text retains both leading and trailing spaces. Every eligible supplied field, including F's matching values, must appear in the script payload and in `filled_fields` after successful execution. The only omitted draft keys should be those explicitly excluded in the preparation report.

As a guard check, open the same project's passing edit page and execute the **same silver script** there. It should report `preflight_failed` and leave the form unchanged. Close that preview and return to the plain silver form without saving. The deterministic DOM suite covers malformed controls and injected runtime failures; do not damage the live page to recreate those cases.

## Completion

Record each case as passed, failed or unexercised, with brief actual-versus-expected notes and screenshots of the relevant controls and script report. Retain both exact proposal URLs and the script alongside their tool results. Confirm that no Save/Submit action was performed. The result qualifies the tested candidate, PolicyChecks silver, selected conditions and delivery paths; it does not establish all-level coverage or saved-state behavior. Resolve failures before stable promotion and rerun affected cases after a candidate change.
