# Local live browser QA

A maintainer runs this check after a release is published and before a major change to the tools or to proposal URLs is released. The check has two halves. `scripts/qa_live.py` drives the candidate's tools and resources against a project's current saved answers and prints proposal URLs. A person then opens those URLs in an authenticated Chrome session and compares the edit form with the report. This is a short supervised integration check, not an automated production save. Discard the previews when finished.

## Project, level and roles

Use any project the tester can edit; [PolicyChecks](https://www.bestpractices.dev/en/projects/14356) (project 14356) has been used so far. The script assigns the roles below to whichever criteria of the chosen level meet their conditions when it runs, so no application has to be kept partly complete. A role that no criterion can fill is reported as unexercised.

| Role | Saved condition and supplied fields | Browser check after opening URL A |
| --- | --- | --- |
| A: blocked pair | Saved status and justification; propose a different known status and new justification; override only the justification | Saved status and justification retained; the justification is blocked by the unforced differing status |
| B: status override | Saved status and justification; supply the same status and new justification; override the status | Both fields remain in the URL. BadgeApp retains the same status and replaces the justification through its documented status-override implication |
| C: blank pair | Status `?` and blank justification; supply `Unmet` and new justification, no override | Both supplied values fill |
| D: retained wording | Saved justification; supply different text without a status or override | Saved wording retained |
| E: clear wording | Saved justification; supply an empty string and override that justification | Justification cleared |
| F: matching values | Supply the saved status and justification exactly, without overrides | Both fields remain in the URL; displayed values stay the same |

Roles A, B, D, E and F each take a different criterion that has a saved status and justification, in catalog order. A level with five such criteria and one unanswered criterion exercises every role in one run. A completed level leaves role C unexercised, and a level that has not been started exercises only role C; run the script once against each to cover all six. Do not change a saved answer to create a condition.

Each new justification is the string `  QA preview only — not saved. <repository URL>?q=a&x=2#qa  `. The `?q=a&x=2#qa` part belongs to the justification's URL; it is not a leaked proposal parameter. The text combines Unicode, URL punctuation, and leading and trailing ASCII spaces. It should appear only in fields where the proposal applies and should disappear when the preview is discarded. These are temporary test values, not criterion assessments.

## 1. Run the script

Follow the [checks after publication](../release/releasing.md#what-the-maintainer-checks) first. Then run:

```sh
make qa-live PROJECT_ID=14356 LEVEL=silver QA_ARGS='--server /absolute/path/to/bestpractices-mcp --output-dir INTERNAL/live-qa/<version>'
```

`--server` names the executable of the exact installed candidate. Without it the script runs this checkout, which is useful during development but does not qualify a release. `--output-dir` writes `report.md` (results, the criteria chosen and every proposal URL) and `calls.json` (each tool call's arguments and result, and each resource read). `INTERNAL/` is ignored by git; the files hold the project's own answer text and no credentials. The report states the server version and negotiated protocol. Record the distribution identity, OS, browser and date beside it.

The script makes about fifteen paced public GETs, stores one empty draft in a temporary directory that it deletes, opens no URL, and exits nonzero when a check fails. `unexercised` is not a failure. It checks:

| Area | Checks |
| --- | --- |
| Reads | `tools/list` returns the ten tools. `get_project_status` reports six levels. `get_project_answers` returns a status for every criterion of the level, with none unretrieved. An unknown level is refused with the allowed values. |
| Proposal URLs A and B | `build_draft` returns the supplied fields unchanged. For each URL every supplied field is `encoded`, the decoded query equals the document exactly (including the spaces, the empty value and role F's matching values), and `overrides` holds only the requested names, so role B's justification is not added. URL B adds role A's status to the overrides and nothing else. |
| Chooser and override-all | A document with one field from another level, sent with `section: "choose_section"` and `{"mode":"all"}`, produces `/choose/edit` with `overrides=*`, and the other level's field is reported with its level. |
| Unknown reset | For a saved status with a justification and one without: `?` proposals with named overrides, with `all`, and with no override each produce a URL that keeps the status and carry `unknown_status_reset_unsupported`. `validate_draft` returns the same warning, skips the unknown statuses and reports no findings. An ordinary override of the same fields is generated as a control. |
| Resources | `resources/list` holds the criteria documents and the repository-file guide, and no project document while no draft is stored. The three templates are listed. The level, category, criterion and guide documents are readable. The project document shows, for every criterion of the level, the status `get_project_answers` returned; the category document holds that category only. Two invalid URIs are refused. After `update_draft` creates a draft, the project's six level documents are listed. |

The script does not cover `find_project` or the badge SVG, which `make smoke-live` and `make smoke-badges` exercise, or stored-draft and reconnect behavior, which [Inspector qualification](inspector-qa.md) covers. The resource list-change notification is checked by the automated tests.

Resolve a failed check before the browser half. An unexpected `artifact: null`, exclusion or mismatch is a finding, not permission to hand-edit a generated URL.

## 2. Browser checks

Open the plain edit page for the level and record the starting values with screenshots of every chosen criterion, including neighboring controls. Public JSON is not a substitute for this browser baseline. If the page shows a value that differs from the report's saved status, record the discrepancy and investigate before continuing. The server does not predict form state, and the script does not observe it: the expectations printed in the report restate the role table, which derives from upstream's documented proposal procedures and the earlier browser records.

Each URL starts from the site's saved baseline. Do not save between cases, and record any automation notice separately from the proposed changes.

1. **URL A.** Open it by clicking the link in the rendered `report.md` and compare every chosen control with the role table. Verify BadgeApp's documented trimming of leading and trailing spaces in newly applied justification text, while interior text and punctuation survive. Distinguish the exact encoded value from the value the site displays. Check untouched neighboring controls as well.
2. **URL B.** Use a second delivery route: copy the complete raw URL into Chrome's address bar, and compare the copied string with the one in the report rather than reconstructing it from visible text. BadgeApp's documented status-override behavior should now replace role A's status and paired justification. Compare the remaining roles again.
3. **Chooser URL.** Choose each relevant badge section in separate unsaved previews and verify that the proposals and the wildcard survive chooser forwarding. Confirm that an ordinary known-status override applies and neighboring unspecified answers stay unchanged.
4. **Reset URLs.** Record that each attempted reset retains the saved status, including where the saved justification is empty. This is expected compatibility behavior despite conflicting upstream documentation; ordinary overrides remain supported. A changed result is new evidence requiring review of the shared warning and this expectation, not a reason for a calling agent to probe routinely.
5. **Control URL.** Confirm that the same controls change to the proposed status, then discard the preview.

## 3. Resources in a host (optional)

The script checks resources at the protocol level. Whether a host offers them to a person is a property of the host, so this case is not required for release. In Claude Code, connected to the candidate:

1. Type `@` and select a listed criteria document, for example `criteria://silver/security`. Confirm that its Markdown is attached.
2. Ask for an `update_draft` call for a project, then confirm that `project://<project_id>/<level>` appears in the picker and attaches with the saved answers.
3. Mention a template URI that is not listed, such as `criteria://silver/dco`. In a maintainer's check with Claude Code desktop in November 2026, such a mention arrived without content and without an error, and the model could still read the URI with its resource-reading tool. Record a change in that behavior, because the server instructions describe it.

## 4. Repository file (optional)

This case is not required for release and has not yet been exercised. It checks the claims in the `guide://repository-file` resource, using a repository the tester controls and its registered BadgeApp project.

1. Choose one criterion that is unanswered (`?`) and one with a saved status. Commit and push a `.bestpractices.json` at the repository root that gives the first a status and justification, and gives the second a status different from the saved one.
2. Open the section's edit page with `?reanalyze` appended. Record whether the unanswered criterion is filled from the file and whether the saved answer is kept and marked as differing.
3. Leave without saving, then remove the file from the repository. Update the guide if the observed behavior differs from it.

## Completion

Record each case as passed, failed or unexercised, with brief actual-versus-expected notes and screenshots of the baseline and each preview. Do not capture credentials or authentication cookies. Discard the previews by opening the plain edit page, and capture the restored controls for each chosen criterion. Confirm that their statuses and displayed text match the baseline and that the QA text is gone. Identify hidden or uninspected values explicitly. Running the script again should choose the same criteria and report the same saved statuses; this supplements rather than replaces the browser restoration check. Confirm that no Save/Submit action was performed.

The result qualifies the tested candidate, project, level, exercised roles and delivery paths; it does not establish all-level coverage or saved-state behavior. The [first scripted run](live-qa/2026-11-18/README.md) and the earlier [Chrome record](live-qa/2026-11-09/README.md) illustrate useful evidence but do not replace a fresh check. Resolve a failure before the next release, and rerun the affected cases after the fix.
