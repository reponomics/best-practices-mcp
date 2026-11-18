# The repository `.bestpractices.json` file

BadgeApp can read answers from a file committed to a project's own repository. This server's drafts use the same format, which is why its stored draft has the same file name. They are different files, and this server does not read, write or send the repository one.

## What BadgeApp does with it

From BadgeApp's documentation:

- It looks for `.bestpractices.json` at the top of the repository, then for `.project.d/bestpractices.json`.
- It uses the file to propose answers when a badge section is edited for the first time, when the edit page is opened with `?reanalyze` in its URL, and when the form is saved with "Save (and continue)".
- A status of `?` in the file is ignored.

From BadgeApp's source at the revision this server is pinned to. These details are internal and may change:

- Only `<criterion_id>_status` and `<criterion_id>_justification` fields are used. Project metadata and any other fields are ignored.
- Values from the file fill criteria that are unanswered. They do not replace an answer that is already saved; a saved answer that differs is kept and marked on the form.
- At most 100 KB of the file is read.

The file has to be committed and pushed to the repository that the BadgeApp project names. A local copy has no effect. A person still reviews and saves the form in the browser.

## Using a draft as the repository file

A draft from this server is already a valid repository file. `read_draft` and `update_draft` return the stored draft's `location`; copy that file to `.bestpractices.json` at the top of the repository, or write out a document returned by `build_draft`. Committing and pushing are the user's decision.

To change answers that are already saved, use `prepare_update_url` with `overrides`. The repository file cannot do that.

This route has not been tested end to end with this server.
