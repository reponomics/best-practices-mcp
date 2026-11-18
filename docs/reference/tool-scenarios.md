# Tool scenarios

This page is for maintainers. It states what each tool is for by the question it answers, so that a change to a name, argument or result can be checked against the intent. The [contracts](contracts.md) define the payloads exactly; the results below are shortened, use synthetic data, and leave out the fields named under each one.

## Which tool answers which question

| Someone asks | Tool | Why this one |
| --- | --- | --- |
| "Does this repository have a badge entry?" | `find_project` | Only lookup by URL, ID or text returns a `project_id`. |
| "What's the status of this project?" "How far along is it?" "When was it updated?" | `get_project_status` | One call covers every level; no other tool returns percentages. |
| "What has it answered for silver?" "What's left?" "Did my change save?" | `get_project_answers` | The only read of per-criterion answers. Always for one level. |
| "What does this criterion require?" "What is in the Security category?" | `get_criteria` | Offline catalog; says nothing about any project. |
| "Record this answer." | `update_draft` | The only tool that writes, and only to the local draft. |
| "Is my draft acceptable?" | `validate_draft` | Mechanical rules only; never judges whether an answer is true. |
| "Give me something to review and save." | `prepare_update_url` | The only way answers reach BadgeApp, through a person in a browser. |
| "Add the badge to my README." | `get_project_badge_svg` | Image and embed snippet; carries no status data. |

`build_draft` and `read_draft` serve the draft tools: the first patches a document the caller holds without storing it, the second returns the stored draft.

Two rules keep the read tools apart. Status figures appear only in `get_project_status`, and saved answers appear only in `get_project_answers`. If a change would put a percentage in the answers result or an answer in the status result, the names stop being enough to choose between them.

## Routing prompts

These prompts check that the tool names and descriptions alone lead to the right first call. Project 123 is already selected. The table states the intended routing; the last run of the check is described below it.

| Prompt | Expected first call | What it checks |
| --- | --- | --- |
| When was this project's record last updated? | `get_project_status(project_id=123)` | `updated_at` comes from the status result. The tool takes no level or badge family. |
| What Best Practices badge does this project currently report? | `get_project_status(project_id=123)` | `badge_level` is the answer. |
| What Baseline badge does it currently report? | `get_project_status(project_id=123)` | No field names a Baseline badge. The description gives BadgeApp's rule, applied to the three Baseline entries in `levels`: the highest level at 100 percent. |
| Show progress across all six badge levels. | `get_project_status(project_id=123)` | One call, not six reads of answers. |
| How close is this project to silver? | `get_project_status(project_id=123)` | A percentage question goes to status even when it names a level. |
| What is left to do for silver? | `get_project_answers(project_id=123, level="silver", statuses=["Unmet", "?"])` | The counterpart of the previous prompt: a question about criteria goes to answers. |
| I saved a new passing-level description_good justification. Check whether it is present. | `get_project_answers(project_id=123, level="passing", criterion_ids=["description_good"])` | Reads the saved answer itself instead of inferring a save from `updated_at`. Comparing it needs the proposed text. |
| Give me Markdown for its Best Practices badge in the README. | `get_project_badge_svg(project_id=123, family="best_practices")` | The image artifact and embed snippet; editing the README is a host action. |
| Download its Baseline SVG badge. | `get_project_badge_svg(project_id=123, family="baseline")` | The right first call; saving the file is a host action. |

To run the check, give a fresh-context agent only the tool list as a client receives it (names, descriptions and input schemas), the selected project ID and the prompts, with no repository access and no expected answers. Ask for the first tool and arguments for each prompt without executing anything, and compare the choices with the table. One run with one model shows that the descriptions are clear to that model; it is not a benchmark and does not cover tool execution, reading of results, repeated trials or other hosts.

The check was last run on 2026-11-18 against all ten tool definitions at commit `c32cb21`, with one agent (Claude Fable 5.2). Its first call and arguments matched the table for all nine prompts, with no more than slight hesitation on any. Asked how it would answer the Baseline prompt, it applied the rule in the description: the highest Baseline level at 100 percent, otherwise baseline-1's percentage. It read only the exported tool list; its session also carried the instructions of an older connected build of this server, which it was told to ignore. Two runs earlier the same day chose the same calls and led to description changes for the points it had been unsure of: the Baseline badge, whether answers include requirement text, how to save an SVG, and whether "saved" means the site or the local draft. An earlier run on 2026-11-14 against the previous tool names is summarized in [ADR 0001](../adr/0001-badge-image-and-status-tools.md).

## Scenarios

### Find a project

```json
{"name": "find_project", "arguments": {"query": "https://code.example.org/alpha"}}
```

```json
{
  "query_kind": "url",
  "candidates": [
    {
      "project": {"project_id": 123, "name": "Fixture Alpha", "repo_url": "https://code.example.org/alpha", "homepage_url": "https://example.org/alpha"},
      "match_basis": "repo_url"
    }
  ],
  "next_page": null
}
```

Not shown: `query`, `page`, `pagination_complete`, `observation`. The tool returns candidates and never picks one. An empty list means the project is not registered, which happens on the website.

### Report a project's status

```json
{"name": "get_project_status", "arguments": {"project_id": 123}}
```

```json
{
  "project": {"project_id": 123, "name": "Fixture Alpha", "repo_url": "https://code.example.org/alpha", "homepage_url": "https://example.org/alpha"},
  "badge_level": "passing",
  "levels": [
    {"level": "passing", "percentage": 100, "achieved_at": "2026-10-01T09:00:00.000Z", "lost_at": null},
    {"level": "silver", "percentage": 12, "achieved_at": null, "lost_at": null}
  ],
  "updated_at": "2026-11-13T12:34:56.000Z"
}
```

Not shown: the other four `levels` entries and `observation`. Every value is copied from the project record. The server does not decide whether a badge is held; it reports the percentage and both timestamps.

### List what is left at a level

```json
{"name": "get_project_answers", "arguments": {"project_id": 123, "level": "silver", "statuses": ["Unmet", "?"], "include_justifications": false}}
```

```json
{
  "level": "silver",
  "answers": {"dco_status": "?", "code_of_conduct_status": "Unmet"},
  "statuses_not_retrieved": [],
  "level_criterion_count": 55
}
```

Not shown: `project`, `observation`, `catalog`. The matching criteria are the ones with a `_status` key in `answers`. BadgeApp saves `?` for every criterion until one is chosen, so `?` means unanswered. `statuses_not_retrieved` is normally empty; an entry is a retrieval failure, not an answer.

The same tool confirms a save: pass `criterion_ids` for the criteria just changed and compare the returned values.

### Read requirements

A level alone returns an index, which is small enough to read whole:

```json
{"name": "get_criteria", "arguments": {"level": "passing", "category": "Reporting"}}
```

```json
{
  "level": "passing",
  "detail": "index",
  "criteria": [
    {"criterion_id": "report_process", "category": "Reporting", "requirement": "MUST"},
    {"criterion_id": "report_tracker", "category": "Reporting", "requirement": "SHOULD"}
  ]
}
```

Not shown: `levels`, `catalog`, six further criteria. Naming criteria returns the full text, field names and status rules:

```json
{"name": "get_criteria", "arguments": {"level": "passing", "criterion_ids": ["report_process"]}}
```

With no arguments the tool lists the six levels with their criterion counts and categories.

### Record answers and hand them over

```json
{"name": "update_draft", "arguments": {"project_id": 123, "changes": {"interact_status": "Met", "interact_justification": "Issues and discussions are open."}}}
```

```json
{"created": true, "applied_patch": {"interact_status": "Met", "interact_justification": "Issues and discussions are open."}, "issues": []}
```

Not shown: `project_id`, `location`, `serialized_size_bytes`, `identity`. The stored draft holds every level's answers for the project; later calls send only the fields that change.

```json
{"name": "validate_draft", "arguments": {"project_id": 123, "section": "passing"}}
```

```json
{"draft_source": {"kind": "stored"}, "findings": [], "checked_criteria": [{"level": "passing", "criterion_id": "interact"}]}
```

Findings are advice. They never block the next step.

```json
{"name": "prepare_update_url", "arguments": {"project_id": 123, "section": "passing"}}
```

```json
{
  "outcome": "complete",
  "transfer": [
    {"field": "interact_justification", "disposition": "encoded"},
    {"field": "interact_status", "disposition": "encoded"}
  ],
  "artifact": {"url": "https://www.bestpractices.dev/en/projects/123/passing/edit?interact_justification=Issues%20and%20discussions%20are%20open.&interact_status=Met"}
}
```

Not shown: `catalog`, `observation`, `identity`, `warnings`, `overrides`, and the remaining fields of each transfer row. A person opens the URL, reviews the form and saves. By default BadgeApp applies proposed values only to unanswered criteria; `overrides` asks it to replace saved ones.

### A rejected call

```json
{"name": "get_project_answers", "arguments": {"project_id": 123, "level": "bronze"}}
```

```json
{
  "error": {
    "code": "invalid_arguments",
    "message": "Invalid arguments for get_project_answers.",
    "details": {"issues": [{"field": "level", "problem": "is not an allowed value", "allowed": ["passing", "silver", "gold", "baseline-1", "baseline-2", "baseline-3"]}]},
    "recovery": "Correct the listed arguments and call again."
  }
}
```

Every tool failure uses this envelope with `isError` set; an unknown tool name is a protocol error instead. An argument error names each argument and, where the values are enumerable, lists them, so the caller can correct the call without another lookup.

## The same reads as resources

A person can attach these with `@` in a host that lists resources; a model can read them by URI. [Contracts](contracts.md#resources) is the reference for the URIs.

| URI | Content | Same data as |
| --- | --- | --- |
| `criteria://levels`, `criteria://{level}`, `criteria://{level}/{category}` | Criteria as Markdown | `get_criteria` |
| `criteria://{level}/{criterion_id}` | One criterion in full | `get_criteria` with `criterion_ids` |
| `project://{project_id}/{level}`, `…/{category}` | Each criterion beside the project's saved answer | `get_criteria` and `get_project_answers` together |
| `guide://repository-file` | How BadgeApp uses a repository `.bestpractices.json` | No tool; explanation only |

Level documents for a project are listed only when that project has a stored draft. The other project and criterion URIs are templates.

## What no tool does

- Save to BadgeApp. The proposal URL is the only handoff, and a person completes it.
- Read, write or send a repository's `.bestpractices.json`.
- Compute a percentage or decide whether a badge is held.
- Judge whether an answer is true.
