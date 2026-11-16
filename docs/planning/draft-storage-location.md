# Draft storage location proposal

Research date: 2026-11-16. Recommendation: retain the current platform defaults and make the existing `BESTPRACTICES_DATA_DIR` override easier to discover. A home dot directory remains an option for users, not an implemented default change.

The proposal was to replace macOS Application Support, potentially across all platforms, with `~/.bestpractices-mcp`. This would give users one memorable location. The examples reviewed show differing conventions rather than a common MCP persistence location:

- [FastMCP settings](https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/settings.py) use `platformdirs.user_data_dir("fastmcp", appauthor=False)` for the default home, with a `FASTMCP_` environment prefix for settings. This supports platform-specific application-data directories.
- [MCP Inspector's storage design](https://github.com/modelcontextprotocol/inspector/blob/main/specification/v2_servers_file.md#file-location) documents `~/.mcp-inspector/` and its `storage/` subtree. This is precedent in MCP tooling for a home dot directory, though it concerns the Inspector client rather than server draft storage.

Keeping the existing defaults respects platform conventions and preserves discovery of already-stored drafts. Users who prefer a dot directory can choose it today with an absolute `BESTPRACTICES_DATA_DIR` value; the README now illustrates that configuration.

If the default changes later, treat it as a compatibility change. Existing drafts would otherwise appear missing, and a subsequent update could create an independent draft in the new root. Document retaining the old root with the override or explicitly moving the existing `projects` directory while server instances are stopped. Avoid automatic migration or fallback across two roots: startup and read operations must remain non-writing, and draft precedence should stay unambiguous.
