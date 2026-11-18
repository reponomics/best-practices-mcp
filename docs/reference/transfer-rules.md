# Transfer rules

This document states what a proposal URL contains: which fields go into it, how overrides are expressed, and what the server leaves to BadgeApp. The [specification](specification.md#proposal-urls) gives the overview, and the [contracts](contracts.md#tools) list the result fields.

BadgeApp defines what a proposal does. Its [automation proposals](../../vendor/badgeapp/docs/automation-proposals.md) document gives the URL format, and its [decision matrix](../../vendor/badgeapp/docs/automation-approach.md#the-decision-matrix) gives the rules that the edit form applies.

## What goes into a URL

The server puts a supplied field into the URL when the field is valid and belongs to the chosen section. It does not compare the draft with the saved answers, so a value that equals the saved one is still included.

| Draft content | In the URL |
| --- | --- |
| A field that the draft does not have | Nothing |
| A value that equals the saved answer | The value |
| A justification without a status | The justification |
| An empty justification | An empty value |
| Leading or trailing spaces, or control characters | The exact text, percent-encoded |
| A status of `?` | The value, with a warning. See below. |
| The fields `id` and `repo_url` | Nothing. They identify the project and are not answers. |
| A field that the server does not recognize, or a field of another level | Nothing |

The server never trims or changes answer text. BadgeApp removes leading and trailing spaces from a proposed justification when it fills the form.

## The transfer report

The result has one row for each field of the draft. A row gives the field, its disposition, a reason, whether an override covers it, and the levels to which it applies.

| Disposition | Meaning |
| --- | --- |
| `encoded` | The field is in the URL |
| `outside_level` | The field belongs to a level other than the chosen section |
| `unsupported` | The server does not recognize the field |
| `invalid` | The value has the wrong type, or the status is not allowed for the criterion |
| `omitted` | The field is not an answer, or its status is invalid, so its justification is left out |

The report does not repeat answer text. It does not say what the form will show.

## Overrides

By default BadgeApp applies a proposed value only where the project has no answer. The `overrides` argument asks it to replace saved answers.

| Mode | Effect |
| --- | --- |
| `{"mode": "none"}` | No override. This is the default. |
| `{"mode": "all"}` | An override for every field in the URL. It does not affect fields that the URL lacks. |
| `{"mode": "fields", "fields": [...]}` | An override for the named fields. Each must be a field of the draft that belongs to the section. |

The server sends exactly the overrides that were requested. It does not add one. Two rules of BadgeApp matter when you choose them:

- If a proposed status differs from the saved status and has no override, BadgeApp keeps the saved status and also keeps the saved justification.
- An override for a status also applies to the justification of the same criterion.

## Sections

The `section` argument is one of the six levels or `choose_section`. With `choose_section` the URL points to BadgeApp's section chooser, and the person picks the level there. Such a URL keeps the fields of every level.

## URL length

The server returns one URL and its length in bytes. It does not shorten or split a URL, and it does not assume a maximum length.

## Resetting an answer to unknown

A proposal of `?` does not reset a saved answer on BadgeApp, with or without an override. Upstream documentation suggests that it should. The server still puts the value in the URL. Both `prepare_update_url` and `validate_draft` return the warning `unknown_status_reset_unsupported`, which names the affected fields. [ADR 0005](../adr/0005-proposal-intent-and-compatibility-warnings.md) records the observations.

## The repository file

BadgeApp can also read answers from a `.bestpractices.json` file in the project's repository. Drafts use the same format. The server has no tool that reads, writes or sends that file. The [guide](../../src/best_practices_mcp/data/repository-file.md) that the server publishes as `guide://repository-file` explains how BadgeApp uses the file.
