# Upstream updates

This document describes how the project keeps its pinned copy of the BadgeApp sources current: what the copy holds, how a change is detected, and how an update is reviewed.

## The pinned copy

`vendor/badgeapp/` holds eight files from one commit of `ossf/best-practices-badge`: two criteria YAML files, the English locale file, four documents and the license. `vendor/badgeapp/source.json` records that commit and the hash of each file. It is the only place that sets the pinned revision.

BadgeApp promotes changes from `main` through `staging` to `production`. The project follows the `production` branch. That branch is BadgeApp's release boundary. It does not prove which revision the website serves.

## Detecting a change

The Upstream criteria update workflow runs once a week and can be started manually. It resolves the `production` branch to one commit and compares the eight files at that commit with the pinned copy, byte for byte. A new commit with identical files is not a change.

## The update pull request

When a file differs, the workflow opens a pull request on the branch `automation/upstream-criteria` with the label `upstream`. The pull request contains:

- the eight files from the new commit and a new `source.json`
- the regenerated catalog, provenance file and license copy

The workflow changes no code, test or document.

The workflow keeps one open pull request. Each run rebuilds the branch from the current `main`, so a run can replace the commits on the branch. After the pull request merges, the workflow deletes the branch.

Three cases need attention:

- **Catalog generation fails.** The pull request still contains the new sources, and the generated files stay as they were. The pull request explains the failure, and the workflow run fails.
- **A file no longer exists upstream.** The pull request deletes it. Catalog generation is skipped and reported as failed.
- **A network, authentication or rate-limit error occurs.** The workflow stops and does not change the branch.

## Pausing the workflow

Set the repository variable `UPSTREAM_UPDATES_PAUSED` to `true` before you push a manual fix to the update branch. Without it, the next run can replace your commits. Use the same variable to defer or decline an update, because closing the pull request does not stop the next run from opening another. Remove the variable, or set it to `false`, when you are done.

## Reviewing an update

1. Read the diff of the upstream files and of the generated catalog. No tool classifies the change. An unchanged set of criterion IDs does not show that the requirements are unchanged.
2. Check CI. If generation or a test fails, pause the workflow and fix the code or the tests in the pull request. Do not weaken a test only to accept an update.
3. Update the project documents by hand where the upstream change affects them. [Upstream compatibility](../reference/upstream-compatibility.md) and [transfer rules](../reference/transfer-rules.md) are the usual ones.
4. Merge. Users receive the new catalog with the next release.

## Local commands

| Command | What it does |
| --- | --- |
| `make upstream-check` | Compares the pinned copy with `production` and prints the files that differ. It writes nothing. |
| `make upstream-prepare` | Makes the same comparison, then writes the new sources and the regenerated catalog into the checkout. It writes a report to `build/upstream/`. |

Both commands read from GitHub.

## Citing upstream documents

A project document that refers to an upstream document links to the pinned copy in `vendor/badgeapp/`. Do not put a commit SHA in such a link. A citation that names a specific commit is deliberate and stays tied to that commit.

[CI](ci.md#security-practices) describes the token that the workflow uses.
