# Architecture

The core component of the architecture is an MCP server that interacts with the OpenSSF Best Practices BadgeApp website. It facilitates data retrieval from the BadgeApp API, and it transforms structured response data into URLs, or "automation proposals," which populate the form fields of a project's badge form in edit mode. Opening a proposal URL, authenticating with the BadgeApp site, and other privileged interactions are outside the scope of the server, and are the responsibility of the host application, the agent, and the user. It can also manage the storage of draft proposal documents on the user's machine. It exposes tools for requesting data from the BadgeApp server and interacting with local documents, and it bundles the criteria for the different badge levels, which it exposes as resources.

This document describes the parts of the server, the actors that it works with, and how data moves between them. The [specification](specification.md) defines the behavior of each tool, and the [contracts](contracts.md) define the payloads and limits. [Design decisions](design.md) gives the reasons for the two main constraints.

The server is a Python package. An MCP host starts it as a local process and exchanges MCP messages with it over standard input and output. The official MCP Python SDK handles the protocol.

## Actors

| Actor | What it does |
| --- | --- |
| User | Chooses the project, reviews a proposal in the browser and saves it |
| MCP host and model | Start the server, call its tools, read its resources and present the results |
| Server | Reads public data, keeps local drafts and builds proposal URLs |
| BadgeApp | Serves public project data. It receives a proposal only when the user opens a URL. |
| Local file system | Holds the drafts |

## Components

| Module | Responsibility |
| --- | --- |
| `server.py`, `__main__.py` | Startup, tool registration and dispatch, server instructions |
| `models.py`, `contracts.py`, `sdk_adapter.py` | Input and result models, published schemas, argument errors, conversion to MCP results |
| `criteria.py`, `data/` | The packaged [criteria catalog](catalog.md) |
| `resources.py` | Markdown resources for criteria and for a project's saved answers |
| `http.py` | The one HTTP client: fixed routes, pacing, retries and size limits |
| `badgeapp.py`, `badges.py` | Mapping of project records, search results and badge images to results |
| `documents.py`, `drafts.py` | Parsing and limits for JSON documents, draft fields, patches |
| `validation.py`, `compatibility.py` | Mechanical checks of a draft against the catalog, and compatibility warnings |
| `transfer.py`, `proposals.py` | The field report and the proposal URL |
| `storage.py` | The draft store |

The modules below `server.py` do not depend on the SDK. They take and return plain values. `server.py` and `sdk_adapter.py` convert those values to MCP results and enforce the limit on the size of a result.

## Data flows

**Criteria.** `get_criteria` and the criteria resources read the packaged catalog. They use no network.

**Project reads.** `find_project`, `get_project_status`, `get_project_answers` and `get_project_badge_svg` send a GET request through the HTTP client and map the response to a result. Each result records the source URL and the time of the read. [Upstream compatibility](upstream-compatibility.md) lists the routes.

**Drafts.** `build_draft` applies changes to a document that the caller holds and returns it. `update_draft` applies changes to the stored draft of a project, and `read_draft` returns it. `validate_draft` checks a draft against the catalog rules. Its findings are advice and do not block any other tool.

**Proposals.** `prepare_update_url` reads the project record to confirm the target, then builds a URL from the draft. The server's part ends there. The user opens the URL, BadgeApp fills the edit form, and the user saves. [Transfer rules](transfer-rules.md) states what the URL carries.

**Resources.** The project resources combine a read of saved answers with the catalog and return one Markdown document. The resource list gains a project's documents when its first draft is stored.

## Constraints

- **No session.** Every tool call is independent and names its project. The drafts are the only state that the server keeps.
- **One client.** Every request to BadgeApp goes through one client and one rate limiter. The server never fetches a URL that appears in a tool argument or in a response.
- **No remote write.** The server has no operation that changes data on BadgeApp.
- **Two kinds of error.** A domain failure is a structured tool result with an error code. A malformed MCP request is a protocol error from the SDK.
- **Standard output is for the protocol.** Diagnostics go to standard error.

## Draft store

The store keeps one JSON file per project under the data directory. Only `update_draft` creates directories or writes a file. A draft that is passed in a tool call is never merged with the stored draft and never written to it.

An update holds a lock for its project, checks the size of the new document, writes a temporary file in the same directory, and replaces the draft atomically. A reader sees the old draft or the new draft and never a partial file.

The lock covers one server process. Two server processes, or an external editor, can still overwrite each other's changes. After a write whose outcome is uncertain, a caller should read the draft before it sends another update.
