# Focused review: draft updates and concurrency

Historical initial-implementation record. This preserves planning and review context, including the implementation status at its original checkpoints. Use the [maintained documentation](../../README.md) for current behavior. Detailed execution reports and earlier versions are archived privately; milestone summaries retain substantive findings and outcomes.

2026-11-06. This independent recommendation resolves finding 8 in the deliverable specification. A review agent examined the current proposal, existing storage primitives, and MCP's stateless request model. No server implementation was changed or tested. The recommendation below is incorporated into [section 5 of the spec](badgeapp-mcp-spec.md#5-project-keyed-draft-storage).

Decision status: retain the internal guard to prevent patch updates from losing unrelated changes within one server process. The concurrency contract below is settled for v1.

## Decision

Use this interface:

```text
read_draft(project_id)
update_draft(project_id, changes)
```

Remove draft revision tokens, hashes, `expected_revision`, the missing-revision sentinel, and `draft_conflict`. Retain catalog revisions, which identify the source of criteria rather than a document's edit history. No read-before-write workflow is required.

Use one small in-memory guard per project while the server reads, patches, validates, and replaces that project's file. Do not use filesystem lock files or a cross-process locking dependency. The guard has no client-visible identity, session, or acquisition operation.

## Why the guard remains

Two requests can independently address the same project. If both read an old file, each can subsequently replace it with a different edited copy. Without coordination inside the server, both calls could report success while one discards an unrelated change from the other. That would violate the patch operation's promise to preserve unrelated fields.

The entire coordination pattern is:

```python
# Illustrative internal structure, not an implemented module.
async with lock_for(project_id):
    document = read_current_document_or_empty(project_id)
    updated = apply_and_check_patch(document, changes)
    atomic_write(project_id, updated)
```

The guard affects only overlapping updates to the same project. It does not order a conversation, require a previous request, coordinate agents' intentions, or impose an arrival-order guarantee. MCP's statelessness removes dependence on protocol sessions; it does not require simultaneous execution of operations addressing the same stored resource. [MCP changes](https://modelcontextprotocol.io/specification/2026-07-28/changelog)

## Exact guarantee and limit

Within one server process, overlapping updates behave as if applied one at a time. Disjoint patches both survive. If two patches set the same field, the later applied value wins; arrival order is unspecified. Different projects use different guards.

Writing through a same-directory temporary file and atomic replacement protects file integrity. A validation or pre-replacement write failure leaves the old file unchanged. A missing file is created by the first explicit update; a missing read creates nothing. An overlapping read sees complete JSON from before or after a server replacement.

Separate server processes and external editors are not coordinated. In particular, two MCP hosts can each launch a server using the same default data directory. They must avoid simultaneous writes to the same project, or use independent roots. Otherwise an entire replacement can lose even unrelated edits; atomic replacement does not merge them. This is an explicit v1 boundary, not a deferred implementation question.

If a response is lost after a completed write, the caller can read the draft to inspect the outcome. The server does not automatically retry that mutation.

## Acceptance evidence required during implementation

- Missing reads create nothing; an update creates the correct project file without a prior read.
- Invalid patches, invalid existing JSON, and an excessive resulting document size leave existing data unchanged.
- Forced overlap of same-process disjoint updates preserves both changes, including concurrent first-file creation.
- Same-field overlap yields a valid serial outcome; tests do not assume arrival order.
- A blocked update for one project does not hold a global guard for another project.
- Readers see complete JSON; injected pre-replacement failure preserves the old file.
- Public schemas and the example host contain no draft revision tokens or required conflict-resolution sequence.

Reuse the existing atomic-write approach and the idea of a process-local mutex. Do not import the registry or `fcntl`/lock-file layer. No cross-process concurrency success test is required because no such guarantee is offered.
