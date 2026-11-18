# Documentation

<!-- treestamp:start -->

<!-- treestamp:config
root = "docs"
hidden = ["docs/README.md"]
-->

```sh
./  # docs
├── adr/ (5 files)  # architecture decision records
├── archive/ (3 files, 1 folder)  # historical documents
├── maintenance/  # processes and project maintenance protocols
│   ├── ci.md  # protocols and requirements for CI/CD
│   ├── dependencies.md  # approach to dependency management (security and licensing)
│   ├── governance.md  # project governance structure
│   └── upstream-updates.md  # how the project stays in sync with BadgeApp
├── planning/  # planning documents and project roadmap
│   ├── api-coverage.md
│   ├── draft-storage-location.md
│   ├── project-metadata-tool.md
│   └── roadmap.md
├── reference/  # technical specifications of the project
│   ├── architecture.md  # the primary components and structure of the application
│   ├── catalog.md  # how the server manages the badge criteria
│   ├── contracts.md  # interfaces for tools and resources
│   ├── design.md
│   ├── schema-compatibility.md  # compatibility with MCP spec
│   ├── specification.md
│   ├── tool-scenarios.md  # intended use cases for tools
│   ├── transfer-rules.md
│   └── upstream-compatibility.md
├── release/  # release policy and verification instructions
│   ├── releasing.md
│   ├── verification.md  # how to verify release provenance and supply chain
│   └── versioning.md
├── security/  # security protocols
│   ├── assurance-case.md  # evaluation of the security posture and threat modeling
│   └── security-requirements.md  # what users can expect regarding security
├── testing/  # testing protocols and methodology
│   ├── live-qa/ (3 folders)  # records of manual testing with live BadgeApp forms
│   ├── fuzzing.md  # how the project incorporates fuzzing
│   ├── inspector-qa.md  # integration testing with MCP Inspector
│   ├── live-browser-qa.md  # manual testing with a live badge form
│   └── testing.md  # testing methodology
├── DCO.txt  # Developer Certificate of Origin (DCO) v1.1
└── interaction-log.md  # records real mcp usage
```

Maintained with [treestamp](https://github.com/reponomics/treestamp)

<!-- treestamp:end -->
