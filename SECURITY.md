# Security reporting

Report suspected vulnerabilities through [GitHub private vulnerability reporting for reponomics/best-practices-mcp](https://github.com/reponomics/best-practices-mcp/security/advisories/new). Do not post sensitive vulnerability details in public issues.

If you are unable to access this preferred reporting channel for some reason, you may also contact [security@reponomics.org](mailto:security@reponomics.org).

Include the affected version, the MCP client and host application, the tool(s) involved, the impact, and a minimal reproduction. Remove credentials and unrelated private data from examples. Use [public issues](https://github.com/reponomics/best-practices-mcp/issues) for ordinary bugs and [conduct@reponomics.org](mailto:conduct@reponomics.org) for conduct reports.

## Coordinated disclosure

The maintainer acknowledges each report within 14 days and keeps the reporter informed while it is assessed and fixed. The project aims to release a fix and publish the vulnerability within 90 days of the report, and coordinates the publication date with the reporter. Earlier publication may be necessary if the vulnerability is already public or actively exploited.

Confirmed vulnerabilities are published as [GitHub security advisories](https://github.com/reponomics/best-practices-mcp/security/advisories), with the affected and fixed versions, how to tell whether a system is affected, and how to remediate it. A CVE is requested through GitHub when appropriate, and the fix appears in the [changelog](CHANGELOG.md).

## Dependency and code scanning findings

OSV-Scanner and Dependabot report known vulnerabilities in dependencies, and CodeQL reports security weaknesses in the code. OSV-Scanner is run against the project's dependencies and is enforced as a check on Pull Requests. Vulnerabilites in existing dependencies, and other security findings are fixed according to their severity, counted from when they are reported:

| Severity | Fixed |
| --- | --- |
| Critical or high | Before the next release, and within 30 days |
| Medium | Within 90 days |
| Low | At the maintainer's discretion |

No release is published while a critical or high finding is open. A finding that does not affect best-practices-mcp may be suppressed only with a recorded reason, given in the code scanning dismissal or the scanner's ignore entry.

When a vulnerability in a dependency of the released package does not affect best-practices-mcp, the project records that in the OpenVEX document `vex/best-practices-mcp.openvex.json`, with the affected best-practices-mcp versions, the status `not_affected`, a justification, and an explanation, before suppressing the finding. [`vex/best-practices-mcp.openvex.example.json`](vex/best-practices-mcp.openvex.example.json) shows the format.

## Supported versions

Each release is supported until the next release is published. Support covers bug fixes and security fixes, which are delivered in a new release; once a newer release exists, earlier releases receive no further updates, including security updates. The project does not provide long-term support for older versions. Reports should identify the exact affected version.
