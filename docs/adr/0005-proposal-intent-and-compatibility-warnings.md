# ADR 0005: Express proposal intent and report upstream limitations

Status: Accepted and implemented. Date: 2026-11-16. See the [implementation qualification](../live-qa/2026-11-16/proposal-interface.md).

## Context and observations

Before this decision, `prepare_update_url` required a badge level, accepted only exact override field names, and removed unknown (`?`) statuses. Hosts should express proposal intent through discoverable MCP inputs without learning URL syntax or repairing generated URLs. The [proposal guide](../../vendor/badgeapp/docs/automation-proposals.md) supports wildcard overrides and deferring section selection to the human, and documents unknown-status resets. The [decision matrix](../../vendor/badgeapp/docs/automation-approach.md#the-decision-matrix) contradicts that reset claim.

Live preview probes on 2026-11-16 found that PolicyChecks silver (project 14356) retained `Met` when `?` was proposed, both with and without an explicit status override. This occurred for `contribution_requirements` with an existing justification and for `code_of_conduct` with an empty justification. Control proposals to `Unmet` with an override applied; plain-form restoration was verified without saving. The maintainer also reported the same reset failure for `osps_br_04_01` on project 16754, Baseline Level 2, using a wildcard override. These are preview observations, not deployment or persistence guarantees.

## Functional contract

**Override intent.** Offer an `overrides` choice with modes `none`, `all`, or `fields`; only `fields` carries a nonempty list of canonical supplied field names. Default to `none`, preserving legitimate fill-only proposals. `all` expresses “override all supplied eligible proposals” and generates BadgeApp's wildcard override; it does not change unspecified answers. Reject contradictory mode/field combinations. Echo the mode and encoded override scope without claiming application. Tool guidance must explain status/justification coupling. This decision does not require exposing raw globs to callers.

**Section intent.** Require an explicit `section` input: one supported badge level or `choose_section`. Omission is an input error; choosing the human-selection mode is not. `choose_section` generates the documented default/chooser entry point with no particular badge level selected. Use documented chooser routing, not an assumed bare edit route. Preserve cross-level proposals and report their applicability. If a shared field permits a value in at least one applicable level, retain it and report restrictions at other levels; do not pick one level's rules arbitrarily. A specific section retains reporting for excluded other-section fields.

**Unknown status.** Continue accepting `?` in draft tools and validation, and include it in generated proposals. Return a nonblocking compatibility warning rather than removing it or marking it invalid/unsupported. An otherwise valid unknown-only proposal still produces an artifact. Preserve accompanying justification independently.

Illustrative tool input, not a URL interface:

```json
{
  "project_id": 16754,
  "section": "choose_section",
  "overrides": {"mode": "all"},
  "draft": {"osps_br_04_01_status": "?"}
}
```

**Validation and warnings.** `validate_draft` accepts the same explicit section choice. A specific section scopes mechanical checks to that level; `choose_section` checks supplied answers at each applicable level and qualifies findings/skips by level. Check only supplied answers; do not claim whole-application completeness. Unknown answers skip status-dependent checks and receive the same advisory as preparation. Both tools expose structured `warnings` with a stable code such as `unknown_status_reset_unsupported`, affected fields, an explanatory message, and the observation date/scope. State the observed limitation directly: “URL proposals to reset a status to `?` are observed not to work, even with overrides, despite conflicting BadgeApp documentation.” Ordinary overrides work. An unknown draft answer alone is not evidence of reset intent; advise manually changing the status in BadgeApp if a reset is intended. Validation must not claim a URL was generated; preparation must not claim a reset succeeded. Warnings appear in structured results and text fallback without failing the call or requiring a bypass flag. Use a shared advisory, not a per-call live probe; revise it when evidence changes.

## Boundaries and implementation acceptance

Retain explicit project identity, existing draft-source precedence, canonical field/type checks, size limits, and human review/save ownership. Preparation still works without prior validation. This ADR changes proposal intent and reporting, not project discovery, draft persistence, authentication, automatic saves, or upstream behavior.

Implementation must update tool discovery descriptions, input/output schemas, examples, transfer reports, and validation together. Replacing `level` and `override_fields` changes the interface: explicitly version affected schemas and document caller migration. Do not silently choose a section when the required input is omitted. The affected success payloads use schema version 2; shared error payloads and all other tools retain version 1.

Acceptance covers: all/none/selected override modes and invalid combinations; a mixed-level chooser proposal and level-qualified validation; unchanged exact answer text; an unknown-only artifact with a warning; matching preparation/validation advisories without suppressing justification; and preserved identity, storage, and size checks. Exercise discovery and calls through MCP, and verify chooser forwarding and override scope in unsaved browser previews. The known upstream reset failure is a compatibility observation, not a reason for the encoder test to expect the field's removal.
