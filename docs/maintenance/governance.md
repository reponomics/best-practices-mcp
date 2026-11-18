# Governance

This document says how the project makes decisions, who holds which role, and who has access to its sensitive resources. [CONTRIBUTING.md](../../CONTRIBUTING.md) says how to contribute.

## Decisions

Reponomics, a GitHub organization, runs the project. [@hesreallyhim](https://github.com/hesreallyhim) is its administrator and makes final decisions.

Anyone can propose a change in an issue or a pull request. A decision that shapes the design is recorded as an ADR in [`docs/adr/`](../adr/).

## Roles

| Role | Who | Responsibilities |
| --- | --- | --- |
| Administrator | [@hesreallyhim](https://github.com/hesreallyhim) | Merges changes, publishes releases, handles security and conduct reports, and manages access and settings |
| Member | [@BittuBarnwal7479](https://github.com/BittuBarnwal7479), [@costajohnt](https://github.com/costajohnt) | Contribute changes and review pull requests |
| Contributor | Anyone who opens an issue or a pull request | Follows the contributing guide and the [Code of Conduct](../../CODE_OF_CONDUCT.md) |

Every change reaches `main` through a pull request that passes the [required checks](ci.md#required-checks). Members often review pull requests, and the administrator merges them.

## Access

The administrator holds the access to the project's sensitive resources: the GitHub organization and repository settings, the repository secrets, the private vulnerability reports, the approval of a release, the project on PyPI, and the project mailboxes. Members have read access to the repository.

The organization requires two-factor authentication for its members.

## Granting access

Before a person receives write access, administrative access or access to a secret, the administrator reviews the request. The review checks that the person has a record of contributions to the project, that the person's identity is established, and that the account uses two-factor authentication.

The access is the least that the role needs. A change in roles or access is recorded in this document.

## Continuity

The administrator is currently the only person who can merge changes and publish releases. The source code is under the MIT License.
