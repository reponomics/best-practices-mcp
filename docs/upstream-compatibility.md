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

The [Upstream criteria check workflow](../.github/workflows/upstream-criteria.yml) runs every Monday at 09:23 UTC and supports **Run workflow** from GitHub Actions on `main`. It resolves `ossf/best-practices-badge`'s `production` branch once, then compares these files at that exact commit against the verified bundled copies:

- `criteria/criteria.yml`
- `criteria/baseline_criteria.yml`
- `config/locales/en.yml`

BadgeApp promotes `main` through `staging` to `production`; its [release policy](https://github.com/ossf/tac/blob/main/process/project-lifecycle-documents/best_practices_badge_graduation_stage.md#release-cadence) identifies releases by commit rather than semantic version. Monitoring `production` follows that release boundary. It does not independently verify which revision the website currently serves, and deployment can fail after a branch update.

Comparison is byte-for-byte: minor wording, whitespace and any English locale text count, including UI strings outside the criteria. Different commit IDs alone do not count. A missing upstream file counts as a change. A failed fetch, invalid response or invalid local source hash fails the check and leaves the tracking issue untouched; it cannot produce an “unchanged” result. This check covers catalog inputs, not every upstream automation document or application change.

When differences exist, the workflow creates or updates one issue titled **Review upstream production criteria and locale changes**. Its stable hidden marker identifies the issue even if renamed. The report lists changed files, links to both source revisions and all compared hashes. Repeated identical results make no issue writes or comments. A closed tracker reopens if differences remain or return; the tracker closes when all three files match. The workflow owns the issue body, so keep review decisions in comments and retain its marker. Closing the issue manually does not acknowledge an outstanding difference. Concurrent manual and scheduled runs are serialized to avoid duplicate creation.

Run the same comparison locally without creating or updating issues:

```sh
make upstream-check
```

The script uses the Python standard library and public GitHub reads. It exits zero after a successful comparison, including detected changes, and nonzero on errors. The workflow explicitly enables issue synchronization with its job-scoped `GITHUB_TOKEN`; no PAT, release App credential or additional repository variable is required. It runs only on `main` in `reponomics/best-practices-mcp` and writes its report to the Actions job summary. After the workflow reaches `main`, a maintainer can trigger it from the CLI:

```sh
gh workflow run upstream-criteria.yml --ref main
```

Scheduled runs can be delayed, and GitHub can disable schedules in public repositories after 60 days without repository activity. Check the workflow's last successful run when reviewing catalog freshness, and re-enable it or use the manual trigger when needed. See [GitHub's schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). This workflow is maintenance automation, not a required PR check or a runtime freshness guarantee.

## Updating the baseline

For a tracking issue, review and update through a pull request:

1. Inspect the file changes between the report's bundled and production commits, including wording-only clarifications. Identify changes to criterion IDs, levels, requirements, aliases and flags; distinguish unrelated locale text from criteria text. Record the assessment in the tracking issue or PR.
2. Refresh retained source inputs from the reviewed commit and update `vendor/badgeapp/source.json` with the revision, timestamp and file hashes. Keep each manifest's revision and hashes consistent with its contents. Even a locale-only change can be incorporated after review so the bundled snapshot matches the reviewed source.
3. Run `make catalog`, review the generated catalog and provenance diff, and adjust relevant contract tests or compatibility documentation if behavior changes. A wording-only change normally needs no runtime code change. Do not silently expand supported levels or tools to match new upstream features.
4. Run `make check catalog-check` and the relevant protocol, artifact and package checks. Merge the reviewed update and manually rerun the upstream workflow; it closes the tracker when the bundled files match production. Publish the refreshed catalog through the ordinary release process so installed users receive it.

Review changes to the upstream documentation and criteria before changing a compatibility rule. Regenerate the catalog from identified inputs, review semantic differences and retained notices, update provenance and required regression examples, then run the relevant protocol, artifact and package checks. Investigate discrepancies against the documented contract rather than copying internal behavior automatically. Live read/form checks complement deterministic tests; production saves are not required acceptance checks. The first live browser check follows beta publication and gates stable promotion; subsequent release candidates repeat that check.

BadgeApp source notices are preserved under its MIT license. Public project records carry their own attribution and license values; the MCP passes those through in observation metadata, including legacy names where supplied. Those statements describe the selected project record, not credit for using MCP. See the [third-party notices](../THIRD_PARTY_NOTICES.md) for licensing distinctions and non-affiliation.
