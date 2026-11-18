# Contracts

This document is the reference for the tools, the resources, the errors and the limits. The server publishes a JSON Schema for the input and the output of every tool in its tool list. Those schemas are authoritative, and `tests/fixtures/contracts/schemas.json` holds a copy that the tests compare. This document summarizes them for a reader.

## Common conventions

- Names use snake_case.
- Types are strict. A string is not accepted where a number is expected. [Schema compatibility](schema-compatibility.md#declared-schemas-and-accepted-input) describes the exceptions.
- An unknown argument is rejected.
- Every result is a JSON object with a `schema_version`. The value belongs to one tool and increases when that tool's result changes incompatibly. It is 2 for `get_criteria`, `validate_draft` and `prepare_update_url`, and 1 for the others.
- A result is returned as structured content and as the same JSON in text.
- A field that can be absent is present with the value `null`.
- Text from BadgeApp is returned unchanged.

## Shared objects

| Object | Fields |
| --- | --- |
| `project` | `project_id`, `name`, `repo_url`, `homepage_url` |
| `observation` | `project_id`, `source_url`, `fetched_at`, and the `attribution` and `license` that the project record states |
| `catalog` | `revision`, `source_url`, `generated_at`, `format_version` |
| `identity` | `association` (`storage_key`, `document_provenance` or `explicit_target`), `id_check` (`matched` or `absent`), `repo_check` (`matched`, `absent` or `not_checked`) |
| `draft_source` | `kind` (`explicit` or `stored`), `location` |

`identity` says how a draft was tied to the project of the call. It records an association and is not an authentication.

## Tools

An argument with `?` is optional. Every result also has `schema_version`.

| Tool | Arguments | Result fields |
| --- | --- | --- |
| `get_criteria` | `level?`, `criterion_ids?`, `category?`, `detail?` | `level`, `detail`, `levels`, `criteria`, `catalog` |
| `find_project` | `query`, `page?` | `query`, `query_kind`, `page`, `candidates`, `next_page`, `pagination_complete`, `observation` |
| `get_project_status` | `project_id` | `project`, `badge_level`, `levels`, `updated_at`, `observation` |
| `get_project_answers` | `project_id`, `level`, `criterion_ids?`, `statuses?`, `include_justifications?` | `project`, `level`, `answers`, `statuses_not_retrieved`, `level_criterion_count`, `observation`, `catalog` |
| `get_project_badge_svg` | `project_id`, `family` | `project_id`, `family`, `image_url`, `project_url`, `markdown`, `artifact`, `observation`, `caveats` |
| `build_draft` | `draft`, `changes?` | `draft`, `issues`, `serialized_size_bytes` |
| `update_draft` | `project_id`, `changes` | `project_id`, `applied_patch`, `created`, `location`, `issues`, `serialized_size_bytes`, `identity` |
| `read_draft` | `project_id` | `project_id`, `draft`, `location`, `issues`, `serialized_size_bytes`, `identity` |
| `validate_draft` | `project_id`, `section`, `draft?` | `project_id`, `section`, `draft_source`, `identity`, `catalog`, `findings`, `checked_criteria`, `skipped_criteria`, `warnings` |
| `prepare_update_url` | `project_id`, `section`, `draft?`, `overrides?` | `project_id`, `section`, `catalog`, `draft_source`, `observation`, `identity`, `warnings`, `outcome`, `no_artifact_reason`, `transfer`, `overrides`, `effective_overrides`, `artifact` |

Notes on individual tools:

- **`get_criteria`.** With no arguments it returns the levels. With a level it returns an index: the ID, category and requirement word of each criterion. With `criterion_ids`, or with `detail` set to `full`, it returns the full records. `category`, `criterion_ids` and `detail` each need a level. `category` and `criterion_ids` cannot be combined.
- **`find_project`.** `query_kind` is `id`, `url` or `text`. Each candidate has a `project` and a `match_basis`. The tool returns candidates and does not choose one.
- **`get_project_status`.** Each entry of `levels` has `level`, `percentage`, `achieved_at` and `lost_at`.
- **`get_project_answers`.** `answers` is in the draft format. `statuses` and `criterion_ids` narrow the result and can be combined. `statuses_not_retrieved` lists criteria whose status the response lacked.
- **`get_project_badge_svg`.** `family` is `best_practices` or `baseline`. `artifact` has `svg`, `media_type`, `suggested_filename` and `encoded_size_bytes`.
- **Draft tools.** In `changes`, a `null` value removes a field. `issues` lists fields that the server does not recognize or that have a wrong type. `update_draft` sets `created` when it stores the first draft of a project.
- **`validate_draft`.** A finding has `level`, `criterion_id`, `field`, `code`, `requirement` and `message`. The codes are `invalid_type`, `invalid_status`, `unknown_field`, `na_not_allowed`, `missing_required_justification` and `missing_required_url`. `skipped_criteria` gives the criteria that were not checked and the reason.
- **`prepare_update_url`.** `outcome` is `complete`, `partial`, `no_transferable_changes` or `no_supplied_transferable_answers`. Each row of `transfer` has `field`, `disposition`, `reason`, `override`, `applicable_levels` and `restrictions`. `artifact` has `url` and `encoded_size_bytes`, or is `null` with a `no_artifact_reason`. [Transfer rules](transfer-rules.md) explains the dispositions.

## Resources

Every resource is a Markdown document with the media type `text/markdown`. The resources hold the same data as the tools.

| URI | Content | Listed |
| --- | --- | --- |
| `criteria://levels` | The six levels with their criterion counts and categories | Yes |
| `criteria://{level}` | Every criterion of one level: its requirement word and description | Yes |
| `criteria://{level}/{category}` | The criteria of one category in full | Yes |
| `criteria://{level}/{criterion_id}` | One criterion in full | No. It is a template. |
| `project://{project_id}/{level}` | Each criterion of a level beside the status and justification that the project has saved | It is a template. It is also listed for a project that has a stored draft. |
| `project://{project_id}/{level}/{category}` | The same for one category | No. It is a template. |
| `guide://repository-file` | How BadgeApp uses a `.bestpractices.json` file in a repository | Yes |

- `{level}` is one of the six level names.
- `{category}` is the category name in lower case with each space replaced by a hyphen. "Change Control" becomes `change-control`.
- A listed resource appears in `resources/list`. A template appears in `resources/templates/list`, and a client reads it by building the URI.
- When `update_draft` stores the first draft of a project, the server adds that project's level documents to the list and announces that the list changed.
- A `project://` resource reads the project record from BadgeApp. The criteria resources and the guide use no network.
- In a document, upstream HTML is converted to Markdown. The tools return the upstream text unchanged.

A failed read is an MCP error with a message that states the problem and the allowed values. It does not use the result form of the next section.

## Errors

A failure is a tool result with `isError` set. Its content is `{schema_version: 1, error}`, and `error` has `code`, `message`, `details`, `recovery` and `retry_after_seconds`.

| Code | Meaning |
| --- | --- |
| `invalid_arguments` | An argument is missing, unknown or of the wrong form. `details.issues` names each argument and, where the values are few, lists them. It does not repeat the value that was sent. |
| `invalid_level`, `invalid_criterion`, `invalid_category`, `invalid_query`, `invalid_override`, `invalid_field` | A value is well formed but not acceptable, such as a criterion that the level does not define. For `invalid_criterion`, `details.other_levels` gives the levels that do define each refused name. |
| `invalid_document`, `document_too_large` | A draft is not a valid document, or exceeds a limit |
| `draft_not_found`, `draft_read_failed`, `draft_write_failed` | The stored draft is absent, or the store could not read or write it |
| `project_not_found` | BadgeApp has no project with that ID |
| `project_mismatch`, `project_identity_unresolved` | The identity in a draft, or in the record that BadgeApp returned, does not match the project of the call, or cannot be compared |
| `upstream_unavailable`, `upstream_invalid_response` | BadgeApp did not answer within the retry policy, or its answer was not in the expected form or exceeded the size limit |
| `rate_limited` | BadgeApp asked the server to wait. `retry_after_seconds` says how long. |
| `response_too_large` | The selected answers or the tool result exceed a size limit. Narrow the request. |
| `internal_error` | An unexpected failure |

An unknown tool name or a malformed request is an MCP protocol error and does not use this form.

## Limits

The values are constants in `documents.py` and `http.py`.

| Limit | Value |
| --- | --- |
| A draft or other JSON document | 1 MiB, and 64 levels of nesting |
| A tool result | 16 MiB |
| A JSON response from BadgeApp | 8 MiB |
| A badge image | 1 MiB |
| Requests to BadgeApp | One per second |
| Attempts for one read | 3, with 10 seconds for each attempt and 30 seconds in total |
| Statuses that are retried | 429, 502, 503, 504 |
