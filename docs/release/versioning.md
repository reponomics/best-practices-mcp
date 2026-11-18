# Versioning

This document says how the project numbers its releases, how a version number is chosen, and where the number is recorded. [Releasing](releasing.md) describes how a version is published.

## Scheme

Versions follow Semantic Versioning: `MAJOR.MINOR.PATCH`. The project has not reached 1.0. While the major number is 0, the rules are:

| Change | Number that increases |
| --- | --- |
| A breaking change | Minor |
| A new feature | Minor |
| A fix | Patch |

A minor release can therefore contain a breaking change. Read the release notes before you upgrade across a minor version. From 1.0 on, a breaking change will increase the major number.

## How a version is chosen

Release Please chooses the next version from the commits on `main` since the last release. Each commit on `main` is one squashed pull request, and its message is the pull request title. The title follows Conventional Commits:

- `fix:` produces a patch release.
- `feat:` produces a minor release.
- `!` after the type, or a `BREAKING CHANGE:` footer, marks a breaking change.
- Other types, such as `docs:`, `test:`, `ci:` and `build:`, do not produce a release on their own.

The PR Requirements workflow rejects a title that does not follow this form. See [CI](../maintenance/ci.md#workflows).

## Where the version is recorded

Release Please writes the version to `pyproject.toml`, to the project's entry in `uv.lock`, to the installation commands in `README.md`, and to `.github/.release-please-manifest.json`. It makes these changes in the release pull request. Do not edit them by hand.

Each release has a Git tag of the form `vX.Y.Z` on the release commit. The tag is a lightweight tag. The release commit has a verified signature, and GitHub makes a published release and its tag immutable.

## Prereleases

The release tooling also accepts a tag of the form `vX.Y.Z-beta.N`. Python package metadata writes the same version as `X.Y.ZbN`. GitHub marks such a release as a prerelease. A prerelease is requested through the [Release Please configuration](https://github.com/googleapis/release-please/blob/main/docs/manifest-releaser.md).

## Release notes

`CHANGELOG.md` holds the notes for every release. Release Please writes them from the pull request titles and lists breaking changes under their own heading. The notes for a release that fixes a vulnerability name the vulnerability, as [SECURITY.md](../../SECURITY.md#coordinated-disclosure) describes.

The `schema_version` field in a tool result is separate from the package version. [Contracts](../reference/contracts.md) defines it.

## Support

The project supports the latest release only. A fix is delivered in a new release, and the upgrade path is to install that release. [SECURITY.md](../../SECURITY.md#supported-versions) states the support policy.
