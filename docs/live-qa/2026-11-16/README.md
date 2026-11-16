# Baseline Level 1 milestone — November 16, 2026

We used best-practices-mcp v0.3.0-beta.1 in Codex to prepare the project's own OSPS Baseline Level 1 application. The maintainer reviewed the proposal, opened it in BadgeApp, then saved and exited. A subsequent MCP read confirmed **100% completion: 23 Met and one N/A**, with all 48 saved status/justification fields matching the reviewed draft. The public entry is [project 16754](https://www.bestpractices.dev/en/projects/16754/baseline-1).

The interaction was guided by the badge-buddy plugin's reference material, with the MCP tools replacing its older BadgeApp CLI workflow. Repository evidence, a peer review of the draft, and two maintainer confirmations supported the assessment: releases come from this single repository, and untrusted contributors use fork pull requests. No project remediation was needed during this session.

The exercised MCP tools all succeeded:

| Tool | What happened |
| --- | --- |
| `find_project` | Resolved the repository URL to project 16754, which was explicitly selected. |
| `get_project_progress` | Retrieved the initial 54% state, rechecked it before preparing the proposal, and confirmed 100% after the maintainer saved. |
| `get_criteria` | Supplied the 24 Baseline-1 criteria and catalog provenance for the assessment. |
| `build_draft` | Built and revised an explicit draft, preserving existing answers where appropriate. |
| `validate_draft` | Checked all 24 criteria with no findings. Evidence review remained a separate human/agent task. |
| `prepare_update_url` | Produced a complete proposal URL for 14 criteria: 11 previously unknown answers and three revised justifications. |

The proposal carried 28 answer fields and exactly three justification overrides. The 4,665-byte URL opened successfully in Chrome; BadgeApp showed all 24 controls complete and marked the three replacements as corrected by automation. The server generated the proposal, while the maintainer performed the website save.

A few useful observations for future work:

- The local review board worked for Baseline-1 through the plugin's separate renderer. The board is outside the MCP's scope; a preview showing saved values, proposed values and differences would be a useful plugin/host improvement, not a missing MCP capability.
- Explicit documents worked well. Optional server-managed draft storage was not exercised; local working artifacts stayed under ignored `build/baseline-1-assessment/`.
- Some answers already filled by BadgeApp lacked supporting URLs. The form described URLs as optional, so these were retained where the explanation was sufficient. Clearer evidence-writing guidance could help without imposing a blanket URL requirement.

This was a successful real-project workflow smoke test, not exhaustive qualification of every tool or transfer case. A full-page screenshot of the proposal form, `best-practices-mcp-baseline-level-proposal-url-11-16-2026.png` (about 3.1 MB), remains outside the repository. It documents the preview; the post-save MCP read establishes the persisted outcome.
