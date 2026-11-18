# Proposal: a tool for project metadata

This is a working proposal. It is not part of the supported behavior, and it is not maintained to the standard of the documents in `docs/`. The [roadmap](roadmap.md) lists its status.

Propose `update_project_metadata` with required `project_id` and explicit optional string inputs for `name`, `description`, `license`, and `implementation_languages`. Require at least one metadata input; omitted fields remain unchanged and empty strings are intentional values. This makes the supported metadata discoverable without requiring callers to know generic draft keys.

Use the existing draft operations: when a caller supplies a draft, return its patched copy without touching storage; otherwise update the project's stored draft, creating it if absent. Preserve criterion answers and other existing content, retain identity checks, and return the updated draft. Pass that draft to the existing `prepare_update_url`, or let preparation read the stored draft. Keep generic draft tools available for combined edits; do not add a separate metadata URL generator. This updates the selected local draft only: website saves remain human-owned, and subsequent live edits require deliberate reconciliation.
