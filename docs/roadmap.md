# Roadmap

Planned items are accepted directions for future work, without a committed release date. Proposed items remain under consideration and do not change the supported contract.

## Planned

- **Deprecate the interactive reference host application.** Replace the full terminal workflow with a small executable SDK integration example. Preserve server behavior coverage through the existing SDK-based tests, and use MCP Inspector for independent-client smoke checks and exploratory QA. The current host remains available until that transition is implemented.

## Proposed

- **Support translations.** Explore localized criteria and language selection for BadgeApp interactions. Define language coverage, fallback behavior and translation maintenance before adding this capability; the current catalog and generated edit links use English.
- **BadgeApp API coverage.** Expand tools to cover more of the BadgeApp public API - see https://github.com/ossf/best-practices-badge/blob/main/best_practices.openapi.yaml.
