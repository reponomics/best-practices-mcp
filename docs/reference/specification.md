# Specification

This document says what the server does and what it does not do. [Contracts](contracts.md) gives the exact arguments, results, errors and limits. [Tool scenarios](tool-scenarios.md) gives worked examples. [Architecture](architecture.md) describes the structure.

## Purpose

The server lets an AI assistant help a person with an OpenSSF Best Practices badge application on bestpractices.dev (BadgeApp). It gives the assistant the official criteria and the public data of a project. It keeps a draft of answers. It builds a URL that fills BadgeApp's edit form, so that the person can review the answers and save them.

## Principles

1. **A standard protocol.** The server implements the Model Context Protocol through the official Python SDK. It adds no protocol features of its own.
2. **BadgeApp's rules.** The server uses the public routes and the proposal interface that BadgeApp documents for automation, and it limits its request rate. See [upstream compatibility](upstream-compatibility.md).
3. **The person decides.** The server never signs in to BadgeApp and never saves an application. See [design decisions](design.md).
4. **Information, not judgment.** The server supplies the official criteria text and the project's own data. It does not say whether a project meets a criterion, and it does not advise how to meet one. Its only checks on an answer are mechanical.
5. **Security in the design.** The server has one fixed network target, validates its input strictly, and passes third-party text on as data. See [security requirements](../security/security-requirements.md).

## Tools

| Tool | What it does | Network | Writes |
| --- | --- | --- | --- |
| `get_criteria` | Returns criteria from the packaged catalog: the levels, the index of one level, or the full text of named criteria | No | No |
| `find_project` | Searches BadgeApp by project ID, by repository or homepage URL, or by text, and returns the candidates | Yes | No |
| `get_project_status` | Returns the badge level of a project, the percentage and the achievement times for each level, and the time of the last update | Yes | No |
| `get_project_answers` | Returns the status and justification that a project has saved for the criteria of one level | Yes | No |
| `get_project_badge_svg` | Returns the badge image of one badge series and a Markdown snippet for a README | Yes | No |
| `build_draft` | Applies changes to a draft that the caller holds and returns the result | No | No |
| `update_draft` | Applies changes to the stored draft of a project | No | One local file |
| `read_draft` | Returns the stored draft of a project | No | No |
| `validate_draft` | Checks a draft against the rules of one level | No | No |
| `prepare_update_url` | Builds the proposal URL for a draft | One read, to confirm the project | No |

A tool that works on a project takes the numeric `project_id`. The server keeps no selected project between calls.

## Resources

The server also publishes the criteria and a project's saved answers as Markdown resources, so that a person can attach them in a host. They hold the same data as the tools. [Contracts](contracts.md#resources) lists the URIs.

## Drafts

A draft is a flat JSON object in the format of BadgeApp's `.bestpractices.json` file:

- `<criterion_id>_status` is `Met`, `Unmet`, `N/A` or `?`.
- `<criterion_id>_justification` is text.
- `name`, `description`, `license` and `implementation_languages` describe the project.
- `id` and `repo_url` are optional and identify the project.

One draft holds the answers for every level of a project. A caller can hold the draft itself and pass it in each call, or it can let the server store one draft per project. A draft that is passed in a call is used as it is. The server never merges it with the stored draft.

The server keeps a field that it does not recognize and reports it. If a draft carries an `id` or a `repo_url`, the value must match the project of the call.

## Validation

`validate_draft` checks four things for each answered criterion of a level:

- The status is one of the four values.
- `N/A` is used only where the criterion allows it.
- A justification is present where the criterion requires one. A justification counts when it has at least five characters and does not begin with `// `.
- The justification contains an `http` or `https` URL where the criterion requires one. The server does not fetch the URL.

The findings are advice. They do not block any other tool. The check says nothing about whether an answer is true.

## Proposal URLs

`prepare_update_url` puts every valid field of the chosen section into the URL and reports what it did with each field. The section is one level, or `choose_section` to let the person pick the level on the site.

By default BadgeApp applies a proposed value only to an unanswered criterion. The `overrides` argument asks it to replace saved answers: for every field, or for named fields. A proposal of `?` does not reset a saved answer, and the result carries a warning when a draft contains one. [Transfer rules](transfer-rules.md) gives the details.

## Out of scope

- Signing in to BadgeApp, saving a form, or creating a project entry.
- Judging whether an answer is correct, or advising how to satisfy a criterion.
- Reading a project's repository. The `guide://repository-file` resource explains how BadgeApp uses a `.bestpractices.json` file in a repository.
- A hosted or network transport. The server runs over standard input and output only.
- Criteria text in languages other than English.

## Running the server

The command `bestpractices-mcp` starts the server on standard input and output. `--help` and `--version` print information and exit. The environment variable `BESTPRACTICES_DATA_DIR` sets the data directory, as the [README](../../README.md#optional-draft-storage) describes. `pyproject.toml` states the supported Python versions.
