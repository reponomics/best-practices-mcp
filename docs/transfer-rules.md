# Artifact transfer rules

The MCP prepares faithful proposal URLs from supplied drafts. The [server specification](specification.md) and [contracts](contracts.md) define the payloads and limits; BadgeApp determines the effects of opening a proposal URL.

## Primary references

- [Automation proposals](../vendor/badgeapp/docs/automation-proposals.md): public URL format, fields, overrides, and review flow.
- [Automation approach: decision matrix](../vendor/badgeapp/docs/automation-approach.md#the-decision-matrix): BadgeApp's status-first, justification-second precedence.
- [Repository JSON](../vendor/badgeapp/docs/bestpractices-json.md): file locations, unknown answers, and triggering import.

## Artifact contents

Every eligible supplied field is included, including values equal to the public record. Artifact generation does not compare saved answers, trim text, classify blankness, suppress unchanged values, or predict the resulting form state. The public read verifies the registered target and any supplied identity; it does not drive answer selection.

The transfer report contains one row per supplied normalized field. It identifies encoded fields and exclusions for unsupported fields, invalid transfer values, provenance, or another badge level. It does not repeat answer bodies or report whether an encoded proposal will fill, replace, retain or be blocked in the actual form. The host reviews the artifact and the rendered BadgeApp form.

| Input | Local draft | Proposal URL |
| --- | --- | --- |
| Missing field | No answer supplied | No field encoded |
| Eligible value equal to saved answer | Preserve supplied value | Encode supplied value |
| Status `?` | Preserve unknown answer | Encode with an observed-reset-failure warning |
| `?` plus justification | Preserve both | Encode both; evaluate justification independently |
| Justification alone | Valid partial draft | Encode only supplied justification |
| Empty justification | Preserve intentional empty text | Encode empty string |
| Whitespace or control characters | Preserve exact text | Percent-encode exact text |
| Override intent | Not an answer field | Encode no override, all supplied eligible fields, or selected eligible fields |
| Patch value `null` | Remove local field | Does not request remote deletion |

Values in encoded artifacts remain exact strings. How BadgeApp parses a URL value or a browser represents a control value is verified in the actual interface, not simulated from upstream implementation details.

BadgeApp's [justification-value documentation](../vendor/badgeapp/docs/automation-proposals.md#justification-values) specifies trimming leading and trailing whitespace from URL-proposed justification text. The tool description communicates this procedure; the MCP preserves the supplied text in the URL and leaves trimming to BadgeApp.

## Explicit overrides

Default URLs contain unforced proposals. `overrides` is an intent object: `{"mode":"none"}` (default), `{"mode":"all"}`, or `{"mode":"fields","fields":["canonical_supplied_field"]}`. `all` generates the wildcard override for supplied eligible fields; it does not change unspecified answers. `fields` requires a nonempty list of canonical supplied in-scope names, sorted and deduplicated in the returned `overrides` object. Reject contradictory combinations and invalid field selections. `effective_overrides` lists encoded fields covered by the selected mode, and each row’s `override` flag reports membership in that list.

The MCP does not expand a status override into an additional justification override. It preserves the supplied status and justification along with the explicit override, so BadgeApp can apply its documented implication. It also preserves unforced supplied pairs even when an existing answer differs. The site decides whether their proposals apply.

For host guidance, BadgeApp documents that an unforced differing status can retain the existing answer and block its supplied justification, including when only the justification is forced. A status override also applies to a supplied paired justification. These are website procedures to consider when choosing overrides and reviewing the form; they are not per-field predictions returned by the MCP. See the upstream decision matrix for the complete rules.

## Section selection

Both validation and preparation require `section`: a supported badge level or `choose_section`. The latter produces the documented `/choose/edit` entry point and leaves section selection to the human. A chooser proposal retains fields eligible at any applicable level; the transfer report records `applicable_levels` and per-level `restrictions`. Validation checks supplied criteria independently at each applicable level and qualifies findings and checked/skipped scope by level.

## URL boundaries

Return one exact URL and its encoded UTF-8 byte length. Do not truncate, batch, retry delivery, or impose a guessed URL-length limit. The host handles display, copying and opening. The URL path is the upstream-recommended interface for external automation.

Repository publishing and import acceptance belong to the host and BadgeApp. Local drafts and artifact generation do not enforce internal importer limits or predict importer results. A fresh public read after a separately authorized save records observed saved state.

## Repository file

BadgeApp can also take answers from a `.bestpractices.json` committed to the project's repository. Drafts use that file's format, and the stored draft shares its name, but the server has no tool that reads, writes or sends the repository file: BadgeApp reads it from the pushed repository, which no tool here can cause. A host with file access can copy a stored draft from its `location`, or write out a `build_draft` result, and the user commits and pushes it.

The server instructions mention the file in one sentence and point to the `guide://repository-file` resource, whose text is [repository-file.md](../src/best_practices_mcp/data/repository-file.md). That guide separates what upstream documents from what was read in upstream source at the pinned revision: file values fill unanswered criteria and do not replace saved answers, so replacing an answer remains a job for a proposal URL with overrides. The route is untested with this server; the [live browser runbook](live-browser-qa.md#3-repository-file-optional) has an optional case for it.

## Unknown-status limitation

URL proposals to reset a status to `?` are observed not to work, even with overrides, despite conflicting BadgeApp documentation. Ordinary overrides work. The MCP encodes `?` and returns the nonblocking `unknown_status_reset_unsupported` warning from both preparation and validation, with affected fields and observation date. Unknown-only proposals still produce an artifact, and accompanying justification is evaluated independently. The warning reports the limitation without recommending an alternative update method. The warning reflects the [recorded live previews](adr/0005-proposal-intent-and-compatibility-warnings.md#context-and-observations), not a per-call probe. [Public guide](../vendor/badgeapp/docs/automation-proposals.md#status-value-semantics-query-strings-vs-json), [decision matrix](../vendor/badgeapp/docs/automation-approach.md#the-decision-matrix).

Required checks and live compatibility verification are mapped in the [testing policy](testing-policy.md).
