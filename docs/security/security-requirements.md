# Security requirements

This document states what a user can and cannot expect from the server in terms of security. The [assurance case](assurance-case.md) explains why the server meets these requirements. [SECURITY.md](../../SECURITY.md) says how to report a vulnerability.

## How the server runs

An MCP host, such as a coding assistant, starts the server as a local process and talks to it over standard input and output. The server runs with the permissions of the user who started the host. It opens no network port.

## What a user can expect

**The server never changes a badge entry.**

- It has no tool that saves to BadgeApp. It produces a URL, and a person opens that URL in a browser, reviews the form and saves.
- It never asks for, stores or sends a BadgeApp password, cookie or token.

**The server makes a narrow set of network requests.**

- Every request is an HTTPS GET to `www.bestpractices.dev`, to one of the routes in [upstream compatibility](../reference/upstream-compatibility.md#requests).
- It verifies the TLS certificate and does not follow redirects.
- A request carries a project ID or a search query. It never carries draft answers.
- The server sends no telemetry and contacts no other host.

**The server stores data only in one directory, and only on request.**

- It writes a file only when `update_draft` is called. Each draft is one JSON file per project in the data directory, which the [README](../../README.md#optional-draft-storage) describes.
- On POSIX systems it creates the directory for the owner only and each file for the owner only.
- It replaces a draft file atomically, so an interrupted write does not leave a partial file.
- A tool argument cannot name a file path. The server builds every path from a numeric project ID.

**The server validates its input.**

- It rejects a tool call that has an unknown argument, a wrong type or a value outside the allowed set. The error names the argument and does not repeat its value.
- It limits the size and the nesting depth of every document that it reads, from a tool call, from disk or from the network.

**The server treats BadgeApp content as data.**

- Project names, saved answers and badge images come from third parties. The server returns them unchanged and marks them as data. It never interprets them as instructions and never renders or executes them.

**The server limits its load on BadgeApp.**

- It sends at most one request per second, retries a failed request a bounded number of times, and stops when the site asks it to wait.

**A release can be verified.**

- Each release has signed provenance and an SBOM. [Verify a release](../release/verification.md) gives the steps.

## What a user cannot expect

- **Protection from the host or the model.** The host decides which tools to call and what to do with the results. Text from BadgeApp can contain instructions that are aimed at a model. The server marks that text as data, but it cannot stop a host from acting on it.
- **Private proposal URLs.** A proposal URL carries the answers in its query string. The browser history, the site and any proxy on the path can see them. Do not put a secret in an answer.
- **Encrypted drafts.** Drafts are plain JSON files. Another process that runs as the same user, or an administrator, can read and change them. On Windows the server sets no permissions of its own. The default data directory is inside the user's profile, which Windows restricts to that user.
- **Proxy support.** The server connects to BadgeApp directly and ignores proxy settings in the environment. It has no setting for a proxy, so its network tools do not work where outbound HTTPS is allowed only through a proxy.
- **A judgment of the answers.** The server checks the form of an answer. It does not check that an answer is true.
- **A guarantee about BadgeApp.** The server reports what the site returns over a verified TLS connection. It cannot confirm that the site's data is correct, and it does not work when the site is unavailable.
- **Isolation.** The server is not a sandbox. It relies on the operating system to separate it from other users.

## Supported versions

Security fixes are delivered in a new release. [SECURITY.md](../../SECURITY.md#supported-versions) states which versions are supported.
