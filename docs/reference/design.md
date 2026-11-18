# Design decisions

## Prepare changes; leave the final save to the human

The server has no tool that saves to BadgeApp. It prepares a draft and a proposal URL. A person opens the URL, reviews the form in BadgeApp and decides whether to save.

Reasons:

- BadgeApp documents an authenticated API for changes, but its [automation proposals documentation](../../vendor/badgeapp/docs/automation-proposals.md) recommends the proposal interface. With a proposal, the person can review, change or discard each answer in the site's own form.
- A save through the API would require the server to hold the user's credentials.
- A save tool would move the approval step into each host. The server could then make the final change on its own.

"The human" means that the decision and the save happen outside this server. A user can let a host agent operate the browser. The server neither implements nor prevents that.

Two consequences follow:

- The server reports which fields a proposal URL carries. It does not predict what the form will show or what BadgeApp will store.
- The server does not certify that a person reviewed anything. Its guarantee is narrower: its tools do not save.

Adding a save operation would need a new decision and an ADR.

## Follow documented procedures, not internal save behavior

The server follows the automation procedures that BadgeApp documents, together with the pinned criteria and locale files. It does not copy what BadgeApp's code does internally when a form is saved.

Reasons:

- The documents are the interface that upstream intends other tools to use. Internal behavior can change without notice.
- The server cannot observe a save, so any model of it would be a guess.

In practice the server sends the exact values that it was given and the overrides that were requested. It does not drop a value because it equals the saved one, and it does not simulate the result of a submission.

Where the documentation is unclear, or differs from what the site does, the project records an explicit decision. [ADR 0005](../adr/0005-proposal-intent-and-compatibility-warnings.md) is an example. [Upstream compatibility](upstream-compatibility.md) states which documents are the authority.
