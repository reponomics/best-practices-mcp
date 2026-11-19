# Changelog

## [0.7.0](https://github.com/reponomics/best-practices-mcp/compare/v0.6.0...v0.7.0) (2026-11-19)


### ⚠ BREAKING CHANGES

* redesign MCP contracts and reorganize documentation ([#35](https://github.com/reponomics/best-practices-mcp/issues/35))

### Features

* redesign MCP contracts and reorganize documentation ([#35](https://github.com/reponomics/best-practices-mcp/issues/35)) ([c9c8223](https://github.com/reponomics/best-practices-mcp/commit/c9c82231a221c807816cb7c7b17c74e4d11d3ac2))


### Documentation

* replace relative links with full GitHub URLs ([#34](https://github.com/reponomics/best-practices-mcp/issues/34)) ([9f35174](https://github.com/reponomics/best-practices-mcp/commit/9f35174ebabef745d1e978f4f08e3dd0f1088bb4))

## [0.6.0](https://github.com/reponomics/best-practices-mcp/compare/v0.5.0...v0.6.0) (2026-11-17)


### Breaking changes

* `validate_draft` and `prepare_update_url` now require `section` instead of `level`. Use a supported badge level or `choose_section` to defer section selection to the user ([#25](https://github.com/reponomics/best-practices-mcp/pull/25)).
* `prepare_update_url` replaces `override_fields` with `overrides`: `{"mode":"none"}`, `{"mode":"all"}`, or `{"mode":"fields","fields":[...]}`. Its result replaces `requested_overrides` with the normalized `overrides` object and retains `effective_overrides` ([#25](https://github.com/reponomics/best-practices-mcp/pull/25)).
* Both tools return successful payloads with `schema_version: 2`, structured compatibility warnings, and level-aware reporting. Validation's `checked_criteria` entries are now `{level, criterion_id}` objects; findings and skipped entries include a level. Proposal transfer rows include applicability and restrictions by level. Other tool payloads and shared error payloads remain at version 1. See the [migration guide](https://github.com/reponomics/best-practices-mcp/blob/v0.6.0/docs/contracts.md#proposal-interface-migration) ([#25](https://github.com/reponomics/best-practices-mcp/pull/25)).

### Proposal features and compatibility

* Generate `/choose/edit` URLs that preserve proposals across badge levels and let the user choose the destination section. Validation can check supplied answers at each applicable level ([#25](https://github.com/reponomics/best-practices-mcp/pull/25)).
* Support wildcard override intent through `{"mode":"all"}`. This covers supplied eligible proposals; it does not change unspecified answers. Selected-field overrides continue to use exact canonical field names ([#25](https://github.com/reponomics/best-practices-mcp/pull/25)).
* Preserve unknown (`?`) statuses in generated proposals instead of dropping them. Validation and URL preparation return the nonblocking `unknown_status_reset_unsupported` warning because resetting a status through a proposal URL was observed not to work in BadgeApp, even with overrides. URL generation does not imply that a reset will succeed ([#25](https://github.com/reponomics/best-practices-mcp/pull/25)).

### Development and CI

* Enforce coverage.py's native 95% total coverage threshold in coverage runs and `make validate`, retaining coverage collection from MCP subprocesses ([#27](https://github.com/reponomics/best-practices-mcp/pull/27)).
* Add optional Atheris fuzzing for document parsing/serialization and proposal URL round trips, with Make targets, seed corpora, and a Linux CI workflow ([#31](https://github.com/reponomics/best-practices-mcp/pull/31)). Isolate temporary test repositories from inherited Git hook environment settings ([#32](https://github.com/reponomics/best-practices-mcp/pull/32)).
* Run upstream maintenance with the locked development dependencies and standard `.venv` setup ([#26](https://github.com/reponomics/best-practices-mcp/pull/26)). Expand upstream monitoring to API and JSON-format documentation, centralize snapshot provenance, and preserve fixed historical citations during snapshot updates ([#25](https://github.com/reponomics/best-practices-mcp/pull/25)).
* Check contributor checklist acknowledgments on human-authored pull requests ([#25](https://github.com/reponomics/best-practices-mcp/pull/25)).

### Documentation

* Add OpenSSF Best Practices Passing and Scorecard badges and record the project's Passing milestone ([#28](https://github.com/reponomics/best-practices-mcp/pull/28)).
* Shorten contributor guidance, consolidate Inspector setup and release qualification instructions, and move specialized CI guidance to its dedicated documentation ([#30](https://github.com/reponomics/best-practices-mcp/pull/30)).

## [0.5.0](https://github.com/reponomics/best-practices-mcp/compare/v0.3.0-beta.1...v0.5.0) (2026-11-16)


### Documentation

* document successful trial and add usage reporting issue form ([#21](https://github.com/reponomics/best-practices-mcp/issues/21)) ([4a6a919](https://github.com/reponomics/best-practices-mcp/commit/4a6a9191a0360d76fe87fdbf09c6a820b5ef0523))

## [0.3.0-beta.1](https://github.com/reponomics/best-practices-mcp/compare/v0.2.0-beta.4...v0.3.0-beta.1) (2026-11-16)


### Features

* remove prepare_update_script tool ([#18](https://github.com/reponomics/best-practices-mcp/issues/18)) ([252b16e](https://github.com/reponomics/best-practices-mcp/commit/252b16ec1463b340a6908d195264ee2becde8f3b))

## [0.2.0-beta.4](https://github.com/reponomics/best-practices-mcp/compare/v0.2.0-beta.3...v0.2.0-beta.4) (2026-11-16)


### Continuous Integration

* add release verification docs and confirmation workflow ([#16](https://github.com/reponomics/best-practices-mcp/issues/16)) ([ddd5407](https://github.com/reponomics/best-practices-mcp/commit/ddd5407ef8f9da3e3f35d5bdf202d57ef9a73191))

## [0.2.0-beta.3](https://github.com/reponomics/best-practices-mcp/compare/v0.2.0-beta.1...v0.2.0-beta.3) (2026-11-15)

This release includes the changes prepared for 0.2.0-beta.2, which was tagged but remained unpublished after release preflight failed. The notes below cover the cumulative changes since 0.2.0-beta.1.

### Bug Fixes

* **ci:** resolve draft releases by numeric ID ([#14](https://github.com/reponomics/best-practices-mcp/issues/14)) ([575f721](https://github.com/reponomics/best-practices-mcp/commit/575f721280c06ad9bf1c0371f7590614f9a2ec7b))
* **ci:** use the project's declared MIT license when scanning unpublished package versions ([#13](https://github.com/reponomics/best-practices-mcp/pull/13)).

### Development and CI

* Adopt a locked uv development environment, default to `.venv` while retaining custom environment overrides, and document Windows setup and validation ([#10](https://github.com/reponomics/best-practices-mcp/pull/10), [#13](https://github.com/reponomics/best-practices-mcp/pull/13)).
* Consolidate contributor checks in `make validate`, expand optional pre-commit checks, and run offline tests for documentation changes ([#10](https://github.com/reponomics/best-practices-mcp/pull/10)).
* Enforce dependency license policy alongside OSV vulnerability scanning, retain separate reports, and isolate workflow linting in a read-only CI workflow ([#10](https://github.com/reponomics/best-practices-mcp/pull/10)).
* Add release evidence validation, SBOMs, checksums, attestations, and retained scan reports to the publication workflow ([#10](https://github.com/reponomics/best-practices-mcp/pull/10)).

### Dependencies

* Update uv to 0.13.8, coverage to 7.17.3, and Ruff to 0.17.5 ([#12](https://github.com/reponomics/best-practices-mcp/pull/12), [#13](https://github.com/reponomics/best-practices-mcp/pull/13)).
* Raise the Node.js minimum to 24.22.3 ([#10](https://github.com/reponomics/best-practices-mcp/pull/10)).

## [0.2.0-beta.2](https://github.com/reponomics/best-practices-mcp/compare/v0.2.0-beta.1...v0.2.0-beta.2) (2026-11-15)

**Not published.** Release preflight failed; these changes are included in 0.2.0-beta.3.

### Dependencies

* Bump the python-minor-patch group with 3 updates ([#12](https://github.com/reponomics/best-practices-mcp/issues/12)) ([64c738d](https://github.com/reponomics/best-practices-mcp/commit/64c738dbd9ab43dd20b85aefb43149b5a28bcf6a))


### Continuous Integration

* use uv for development and ci ([#10](https://github.com/reponomics/best-practices-mcp/issues/10)) ([7a8ba3f](https://github.com/reponomics/best-practices-mcp/commit/7a8ba3fe12147468c8da9ea03a6bd972d9a1d4eb))

## [0.2.0-beta.1](https://github.com/reponomics/best-practices-mcp/compare/v0.1.1-beta.1...v0.2.0-beta.1) (2026-11-14)


### Features

* add tools for API badge endpoint ([#8](https://github.com/reponomics/best-practices-mcp/issues/8)) ([86f20b0](https://github.com/reponomics/best-practices-mcp/commit/86f20b0b3f959d8859bd7486b740032f6d3af43a))

## [0.1.1-beta.1](https://github.com/reponomics/best-practices-mcp/compare/v0.1.0-beta.1...v0.1.1-beta.1) (2026-11-14)


### Documentation

* add issue forms and pull request template ([#3](https://github.com/reponomics/best-practices-mcp/issues/3)) ([542e283](https://github.com/reponomics/best-practices-mcp/commit/542e2836ba1db6fe7b4b1e3ef03f4fe44f9daab0))

## 0.1.0-beta.1 (2026-11-12)


### Features

* bootstrap BadgeApp MCP server ([addf1e9](https://github.com/reponomics/best-practices-mcp/commit/addf1e98aafa2aa11f91da21c5b82496996b98ae))


### Documentation

* organize user setup and contributor guidance ([d6acd86](https://github.com/reponomics/best-practices-mcp/commit/d6acd8641388a126e2a5b9d0fe535c15a9c8494b))
