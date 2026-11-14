# Badge tool discovery routing exercise

Date: 2026-11-14. Related decision: [ADR 0001](../adr/0001-badge-image-and-status-tools.md). This is a bounded review of the implemented descriptions, not a benchmark or guarantee of host behavior.

A fresh-context subagent received the three discovery descriptions from `server.py` and their argument constraints, without repository access, prior review discussion or expected answers. Project 123 was specified as already selected. It was asked to choose the first tool and arguments for ten prompts without executing any tools. The resulting choices were compared with the ADR's intended task boundaries.

| Prompt | Selected first call | Assessment |
| --- | --- | --- |
| When was this project's record last updated? | `get_project_badge_status(project_id=123)` | Uses the explicit default family, without an unnecessary clarification. |
| What Best Practices badge does this project currently report? | `get_project_badge_status(project_id=123, family="best_practices")` | Compact metal-family observation. |
| What Baseline badge does it currently report? | `get_project_badge_status(project_id=123, family="baseline")` | Compact Baseline observation. |
| Show progress across all six badge levels. | `get_project_progress(project_id=123)` | Retains the existing all-level summary. |
| How close is this project to silver? | `get_project_progress(project_id=123, level="silver")` | Does not confuse tiered progress with an individual level percentage. |
| What is its Baseline level-3 completion percentage? | `get_project_progress(project_id=123, level="baseline-3")` | Does not substitute the compact endpoint's level-1 percentage. |
| Give me Markdown for its Best Practices badge in the README. | `get_project_badge_svg(project_id=123, family="best_practices")` | Retrieves the image artifact and embed snippet. |
| Download its Baseline SVG badge. | `get_project_badge_svg(project_id=123, family="baseline")` | Appropriate first call; saving remains a host action. |
| I saved a new passing-level description_good justification. A quick status lookup still shows the old updated_at. Check whether my justification is present. | `get_project_progress(project_id=123, level="passing", criterion_ids=["description_good"])` | Reads the relevant saved answer despite an unchanged timestamp. |
| Give me a quick Best Practices badge status and last-update summary. | `get_project_badge_status(project_id=123, family="best_practices")` | Keeps related fields in one observation. |

All ten choices and argument sets matched the intended routing. The evaluator noted that downloading may require a later host file-write action, and exact justification comparison requires the proposed text; neither changes the first tool choice. The exercise did not test actual tool execution, response interpretation, repeated trials, alternative models, all eleven tools together, or ambiguous requests without a specified badge family. Protocol and adapter tests separately exercise tool execution. This evidence supports the descriptions' basic clarity while leaving broader routing reliability unclaimed.
