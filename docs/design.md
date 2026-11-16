# Design decisions

The server prepares changes for review while leaving authentication, browser interaction and final saving to the host and user.

## Prepare changes; leave the final save to the human

Here, leaving the save to the human means leaving the decision and its execution outside this MCP, not requiring the user to click a button personally. A user may authorize a host agent to operate the browser and click Save on their behalf. That delegation belongs to the user and host; it is neither implemented nor prohibited by this server.

The MCP deliberately provides no tool that directly saves changes to a BadgeApp application through an authenticated API request. This is a scope and interaction-design decision, not an assertion that upstream lacks an API for changing project data.

Upstream documents REST writes, but its [automation proposals documentation](https://github.com/ossf/best-practices-badge/blob/868e1677339a3fdb48851b0c2ae8862c553115eb/docs/automation-proposals.md) explicitly no longer encourages that route for changes: authentication is an additional responsibility, and REST writes do not let the user review changes in the BadgeApp UI. The proposal interface instead gives the authorized human an opportunity to review, modify, approve, or discard proposed answers before saving. The same document describes existing-project REST changes as `PUT`; the exclusion here applies to authenticated remote writes regardless of HTTP method.

The server therefore prepares portable draft documents and proposal URLs. Updating a stored draft changes a local file only. Opening a proposal URL prepares the edit form without submitting it. The human reviews the resulting application in BadgeApp and decides whether to save it. Authentication, browser interaction, and presentation of the handoff belong to the host and user, not to the MCP server.

A direct API save could be preceded by a host-managed approval step, so it is not inherently incompatible with human approval. Nevertheless, adding that tool would move the approval boundary into each host and allow the server to perform the final remote mutation. Keeping the final save in BadgeApp better supports upstream's human-review principle while keeping this server's tool surface bounded. Adding direct saving would require a separately approved scope and design change.

The MCP does not enforce a host's entire approval workflow or certify that a human has reviewed an artifact. Its narrower guarantee is that its tools do not save BadgeApp applications. Artifact generation reports which supplied fields it includes or excludes. It does not predict edit-form effects. Advisory validation and artifact generation do not predict final persisted values or reproduce BadgeApp's Save/Submit processing. Those outcomes remain the site's responsibility.

## Follow documented procedures, not internal save behavior

The server is designed to respect upstream's documented automation procedures. Its compatibility contract draws on the pinned automation documentation, criteria YAML and English locale, and explicitly agreed MCP rules. It implements bounded artifact preparation with exact supplied values and explicit overrides. It does not classify per-field edit-form effects, suppress answers equal to a public record, simulate submission, or infer final acceptance, saved values, importer behavior or automated assessments. BadgeApp interprets proposal URLs, and the host reviews the actual form.

Where documentation is ambiguous or conflicts with observed internals, make the compatibility decision explicit and review it rather than silently adopting the internal behavior.

Required tests check documented procedures, criteria inputs, and explicit contracts. A locally supervised live browser check establishes proposal-URL compatibility with the actual site. See the [testing policy](testing-policy.md) and [live browser runbook](live-browser-qa.md).
