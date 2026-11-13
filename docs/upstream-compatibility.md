# Upstream compatibility

Compatibility is based on BadgeApp revision **868e1677339a3fdb48851b0c2ae8862c553115eb**. A source pin identifies the documented and tested baseline; it does not establish which revision the live website currently runs. The server follows documented automation procedures and prepares artifacts without predicting edit-form or save-time outcomes.

## Sources and authority

The primary references are the pinned [API documentation](https://github.com/ossf/best-practices-badge/blob/868e1677339a3fdb48851b0c2ae8862c553115eb/docs/api.md), [automation proposals](https://github.com/ossf/best-practices-badge/blob/868e1677339a3fdb48851b0c2ae8862c553115eb/docs/automation-proposals.md), [automation approach](https://github.com/ossf/best-practices-badge/blob/868e1677339a3fdb48851b0c2ae8862c553115eb/docs/automation-approach.md), and [repository JSON guidance](https://github.com/ossf/best-practices-badge/blob/868e1677339a3fdb48851b0c2ae8862c553115eb/docs/bestpractices-json.md). Catalog generation uses the pinned criteria YAML and English locale; packaged provenance records source hashes and generator details.

Vendored criteria, locale, documentation and license notices support reproducibility. Required tests derive expectations from documented procedures, criteria definitions and the agreed contract. Synthetic form fixtures retain a concise derivation record with pinned upstream references, without claiming those forms reproduce the live application. See the [testing policy](testing-policy.md) and [design boundary](design.md#follow-documented-procedures-not-internal-save-behavior).

## Routes and public observations

All network requests use GET against `https://www.bestpractices.dev`, without authentication or cookies. Public JSON routes are locale-independent; generated HTML edit links use English paths.

| Operation | Route and interpretation |
| --- | --- |
| Project lookup/progress | `/projects/{project_id}.json`; a missing ID is empty discovery or `project_not_found` for progress/generation |
| URL discovery | `/projects.json?url={query}&page={page}`; the URL is a query value, never fetched; preserve upstream candidates and their own search semantics |
| Text discovery | `/projects.json?q={query}&page={page}`; preserve returned candidate order and explicit pagination uncertainty |
| Proposal/edit link | `/en/projects/{project_id}/{level}/edit`; all six level names map directly to section names |

Query keys are sorted and spaces percent-encoded as `%20` to use the site's canonical request representation without following redirects. Discovery matching is intentionally more permissive than generator identity checks: an upstream search candidate is not discarded merely because strict repository-URL identity comparison cannot establish equality.

Omitted public fields remain absent: neither a missing status nor a missing justification is synthesized. Unexpected supplied JSON values remain visible for diagnostics. Artifact generators use the public record to verify the registered target and supplied identity, not to classify supplied answers or infer the edit form's current state.

## Catalog and transfer semantics

The six supported levels are `passing`, `silver`, `gold`, `baseline-1`, `baseline-2`, and `baseline-3`. Catalog requirements are level-qualified. Explicit public flags expand upstream's logical entailments: `met_url_required` implies `met_justification_required`, and `na_justification_required` implies `na_allowed`. An omitted entailed YAML field is not absence of the requirement.

Proposal URLs encode all eligible supplied fields and exact explicit overrides. Fields equal to the public record are still included. BadgeApp applies its documented status-first, justification-second matrix when the form is opened; the MCP does not evaluate that matrix against saved answers or expand a status override into additional override fields.

Original text, including whitespace, control characters and empty strings, is preserved in drafts and artifact payloads. The generator does not normalize values or reproduce Ruby/Rails trimming and blankness rules. Advisory justification predicates are separate and do not strip text before checking it. Artifact rules and the documented disagreement over URL `?` resets are in [transfer rules](transfer-rules.md).

The form-fill script is a guarded project feature, not an upstream-supported API. It checks exact production origin, project ID and section; preflights intended controls; then replaces specified values without submitting. Its defensive behavior is verified against controlled synthetic forms; compatibility with current website controls is checked through the [live browser runbook](live-browser-qa.md). Neither script execution nor a URL preview establishes the final saved state.

## Checking for upstream changes

The [Upstream criteria update workflow](../.github/workflows/upstream-criteria.yml) runs every Monday at 09:23 UTC and supports **Run workflow** from GitHub Actions on `main`. It resolves `ossf/best-practices-badge`'s `production` branch once and compares the complete retained source snapshot at that commit: both criteria YAML files, the full English locale, the automation approach and proposals documents, and the upstream license. All six paths are recorded in `vendor/badgeapp/source.json`.

BadgeApp promotes `main` through `staging` to `production`; its [release policy](https://github.com/ossf/tac/blob/main/process/project-lifecycle-documents/best_practices_badge_graduation_stage.md#release-cadence) identifies releases by commit rather than semantic version. Monitoring `production` follows that release boundary. It does not independently verify which revision the website currently serves, and deployment can fail after a branch update.

Comparison is byte-for-byte, including minor wording, whitespace and English UI strings outside the criteria. A different commit alone does not trigger an update. When retained files differ, the automation refreshes the complete snapshot, source revision and hashes; regenerates the packaged catalog, provenance and upstream license; and updates the source references in maintained compatibility, transfer, design, specification and third-party-notice documents. Historical records and fixture derivation references retain their original revisions. Source snapshots use the upstream commit timestamp for deterministic metadata, so identical reruns do not manufacture new changes.

Every update follows the same regular PR path on the reserved `automation/upstream-criteria` branch, with title **fix(catalog): refresh upstream BadgeApp sources**. The `upstream` label identifies the update; `upstream: criterion-ids` is an advisory label when the set of level-qualified criterion IDs changes. The report lists added and removed IDs. These labels do not classify wording, interpret requirements, claim compatibility, choose a draft state or bypass review. Conditions and text flow through catalog generation. Maintainers inspect the diff and ordinary CI determines whether the existing code and tests accept it.

A catalog generation failure still produces a PR containing the refreshed source inputs and documentation pins. Previous generated files remain unchanged, the PR explains the failure, and the update workflow fails after publishing the patch. Catalog reproducibility and regression checks must pass before merging. An unavailable ID comparison is reported without blocking preparation. Missing upstream files appear as deletions; network/authentication/rate-limit errors and invalid local hashes abort preparation without updating the branch. The workflow never executes downloaded upstream code or automatically changes runtime code, tests, supported levels or tools.

## Branch ownership and credentials

The workflow uses the existing `RELEASE_APP_CLIENT_ID` and `RELEASE_APP_PRIVATE_KEY` to create a short-lived repository-scoped App token after preparing the patch. The App signs commits and supplies its own bot identity for sign-off; no PAT or personal signing key is used. App-created PRs run normal CI. Additional repository variables are unnecessary for normal operation.

The [Create Pull Request action](https://github.com/peter-evans/create-pull-request) maintains one open PR on the fixed branch. It fetches the existing branch and regenerates/rebases it from current `main`, updating it only when necessary; this may rewrite the generated branch history. It also recovers a branch whose PR creation was interrupted. Scheduled/manual runs and merge cleanup share one concurrency group. A separate merge handler deletes only this reserved branch, and only if it still points to the merged PR's head; other branches are unaffected. The action also removes an obsolete branch on a later run when there is no remaining diff.

**Before making manual fixes on the generated branch, set the repository Actions variable `UPSTREAM_UPDATES_PAUSED=true`.** Otherwise a subsequent run can overwrite those fixes. Pause first, push the fixes to the existing PR, run the required checks, and merge after review. Unset the variable or set it to `false` afterward. Closing an unmerged PR alone does not reject an update permanently: without a pause, the next run can create another PR while the sources differ. Use the same pause mechanism when deferring or declining an update. A maintainer can mark a PR as draft manually; automation does not use draft state to classify changes.

## Local checks and manual runs

Read-only comparison, with no repository edits or GitHub writes:

```sh
make upstream-check
```

Prepare the same patch locally on a clean working branch after `make setup`, without creating or updating a remote branch or PR:

```sh
make upstream-prepare
```

Preparation writes the retained sources, generated files and maintained documentation pins. Its review body and machine-readable result are under ignored `build/upstream/`. A successful preparation command exits zero even if catalog generation failed, allowing the workflow to publish the reviewable patch; inspect the reported result and run `make catalog-check` before treating preparation as complete. The read-only comparison uses the Python standard library; preparation additionally uses the project's pinned PyYAML dependency.

After the workflow reaches `main`, run it through GitHub Actions or the CLI:

```sh
gh workflow run upstream-criteria.yml --ref main
```

Scheduled runs can be delayed, and GitHub can disable schedules in public repositories after 60 days without repository activity. Check the workflow's last successful run when reviewing catalog freshness, and re-enable it or use the manual trigger when needed. See [GitHub's schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). This workflow is maintenance automation, not a required PR check or a runtime freshness guarantee.

## Reviewing and merging an update

1. Inspect the retained upstream files, generated catalog and documentation-reference changes. Review wording and conditions as well as added or removed IDs, including the compatibility and release implications of removing accepted fields. A stable set of IDs does not prove that requirements are unchanged. The API and repository-JSON documents are linked rather than vendored, so inspect those documents at the proposed revision when reviewing their updated references.
2. Inspect CI. If generation or tests fail, pause automation and fix the code or tests in the PR as appropriate. Preserve meaningful assertions; do not weaken tests merely to accept an update. Refresh compatibility prose or notices manually if the upstream changes require it.
3. Run `make check catalog-check` and any relevant protocol, artifact, package or live-browser checks. The automation updates references and copied documents, not interpretations of changed procedures or licensing terms.
4. Merge after maintainer review and passing checks. The merge handler removes the reserved branch; the next update starts a fresh branch and PR. Publish the refreshed catalog through the ordinary release process so installed users receive it.

Review changes to the upstream documentation and criteria before changing a compatibility rule. Regenerate the catalog from identified inputs, review semantic differences and retained notices, update provenance and required regression examples, then run the relevant protocol, artifact and package checks. Investigate discrepancies against the documented contract rather than copying internal behavior automatically. Live read/form checks complement deterministic tests; production saves are not required acceptance checks. The first live browser check follows beta publication and gates stable promotion; subsequent release candidates repeat that check.

BadgeApp source notices are preserved under its MIT license. Public project records carry their own attribution and license values; the MCP passes those through in observation metadata, including legacy names where supplied. Those statements describe the selected project record, not credit for using MCP. See the [third-party notices](../THIRD_PARTY_NOTICES.md) for licensing distinctions and non-affiliation.
