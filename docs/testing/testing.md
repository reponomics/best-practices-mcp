# Testing

This document states the testing policy, describes the kinds of test that the project has, and says when each kind runs. [Fuzzing](fuzzing.md) and the two manual runbooks have their own documents.

## Policy

A change that adds or changes behavior must add or update automated tests for that behavior in the same pull request. A bug fix must add a test that fails without the fix.

A pull request cannot merge while a test fails or while coverage is below the floor.

## What the tests take as authority

Expected values come from three sources: the upstream procedures that BadgeApp documents, the pinned criteria and locale files, and the [contracts](../reference/contracts.md) of this server. The retained upstream documents are in `vendor/badgeapp/docs/`.

The tests do not run BadgeApp code. They do not simulate what BadgeApp does when a person saves a form. [Design decisions](../reference/design.md#follow-documented-procedures-not-internal-save-behavior) explains this boundary.

## Kinds of test

All of these run on every pull request and every push to `main`, on each operating system and Python version of the CI matrix. They run offline, except the package check in fresh environments, which downloads dependencies. [CI](../maintenance/ci.md) describes the workflow.

| Kind | What it checks |
| --- | --- |
| Unit and contract tests | The domain rules, the tool input and output schemas, and the error results |
| MCP integration tests | The server as a subprocess over stdio, with a fixture in place of the network |
| Catalog checks | The packaged catalog is exactly what the generator produces from the pinned sources |
| Package checks | The wheel and source distribution build, install into a clean environment and start |
| Script tests | The development and release scripts in `scripts/` |
| Type checks | mypy in strict mode for the server package and the scripts, with a relaxed profile for tests. The settings are in `[tool.mypy]` in `pyproject.toml`. |

Three kinds of check are separate from the suite:

- [Fuzzing](fuzzing.md) runs in CI on Linux.
- The live checks read the public BadgeApp site. They are `make smoke-live`, `make smoke-badges` and `make qa-live`. A maintainer runs them by hand. They never run in CI.
- [Inspector qualification](inspector-qa.md) and the [live browser runbook](live-browser-qa.md) are manual checks. [Releasing](../release/releasing.md#what-the-maintainer-checks) says when they run. A passing CI run does not replace them.

## How tests are written

- A test states a behavior that must stay true. It fails when the behavior breaks and does not fail when the code is only rearranged.
- Tests do not assert on the content or location of project documentation.
- A functional test does not depend on the particular values that the codebase holds today. It uses synthetic or arbitrary inputs.
- The project applies a mix of methods. The test suite uses examples, and the [fuzz targets](fuzzing.md) check rules that must hold for any input, such as a round trip.
- Tests make no network requests. A test that needs BadgeApp responses uses the fixture server in `tests/fixtures/`.

## Running the tests

| Command | What it runs |
| --- | --- |
| `make test` | The offline suite |
| `make test-coverage` | The suite with coverage, and the coverage floor |
| `make typecheck` | The type checks |
| `make test-package` | The offline package checks |
| `make check-fresh-package` | The package checks in fresh environments. This command downloads dependencies. |
| `make validate` | The lockfile check, formatting and lint, the type checks, the suite with coverage, and the catalog check |

The `Makefile` also has targets that run one part of the suite, such as `make test-protocol`. `make help` lists them.

## Coverage

`make test-coverage` measures statement and branch coverage of the server package, including the code that runs in MCP subprocesses. The floor is the `fail_under` value in `[tool.coverage.report]` in `pyproject.toml`. The command fails when the combined figure is below the floor.

Every CI job enforces the floor. One job uploads its report to Codecov, which shows the trend. The Codecov figure is one platform's result and is not a combined figure.
