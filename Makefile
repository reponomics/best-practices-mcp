.DEFAULT_GOAL := help

# Empty lets uv read .python-version; CI overrides this with its matrix version.
BOOTSTRAP_PYTHON ?=
UV_PYTHON_ARG = $(if $(BOOTSTRAP_PYTHON),--python "$(BOOTSTRAP_PYTHON)")
VENV ?= .venv
ifeq ($(OS),Windows_NT)
# Native GNU Make launched from PowerShell/cmd; do not depend on Git Bash.
SHELL := cmd.exe
.SHELLFLAGS := /d /c
PYTHON ?= $(VENV)/Scripts/python.exe
else
PYTHON ?= $(VENV)/bin/python
endif
PIP ?= "$(PYTHON)" -m pip
UV ?= uv
OSV_SCANNER ?= osv-scanner
GO ?= go
# Keep in sync with the license scan in .github/workflows/osv-scanner.yml.
OSV_LICENSES := MIT,MIT-0,BSD-2-Clause,BSD-3-Clause,Apache-2.0,ISC,PSF-2.0,MPL-2.0,BlueOak-1.0.0,0BSD,Unlicense
RELEASE_DIST ?= build/release/dist
RELEASE_EVIDENCE ?= build/release/evidence.json
RELEASE_ARGS ?=
RELEASE_TOOLS_VENV ?= build/release-tools
ifeq ($(OS),Windows_NT)
RELEASE_SBOM_PYTHON ?= $(RELEASE_TOOLS_VENV)/Scripts/python.exe
else
RELEASE_SBOM_PYTHON ?= $(RELEASE_TOOLS_VENV)/bin/python
endif
RELEASE_SBOM ?= 0
RELEASE_SBOM_ARG = $(if $(filter 1,$(RELEASE_SBOM)),--sbom-python "$(RELEASE_SBOM_PYTHON)")

export UV_PROJECT_ENVIRONMENT := $(VENV)
# Evidence must identify this Make executable, including gmake/custom paths.
export VERIFICATION_MAKE := $(MAKE)

.PHONY: help setup quality tooling-check ci-environment check test format build run test-contract test-catalog test-protocol test-package catalog catalog-check test-network test-api smoke-live

help: ## Show available development commands (no project environment required)
	@"$(UV)" run --no-project $(UV_PYTHON_ARG) python scripts/dev_tools.py help

setup: ## Sync the locked development group into .venv (Python 3.11 by default)
	"$(UV)" sync --locked --group dev --no-group audit-tools $(UV_PYTHON_ARG)

quality: tooling-check ## Check formatting, lint and installed dependency consistency
	"$(PYTHON)" -m ruff format --check src tests scripts
	"$(PYTHON)" -m ruff check src tests scripts
	$(PIP) check

check: quality ## Run quality checks and the offline test suite
	"$(MAKE)" test

.PHONY: validate

validate: ## Run contributor checks and the coverage floor (OSV scans run in CI)
	"$(MAKE)" -k lock-check quality test-coverage catalog-check workflow-check

tooling-check: ## Verify the uv bootstrap requirement matches its locked audit inventory
	"$(UV)" run --no-project $(UV_PYTHON_ARG) python scripts/dev_tools.py tooling-check

ci-environment: ## Record allowlisted environment facts for CI evidence
	"$(PYTHON)" scripts/ci_environment.py --output build/verification/environment.json

test: ## Run offline unit and MCP subprocess integration tests
	"$(PYTHON)" -m pytest

format: ## Format Python source, tests, and development scripts
	"$(PYTHON)" -m ruff format src tests scripts

build: ## Build source and wheel distributions
	"$(PYTHON)" -m build

run: ## Run the stdio server (waits for an MCP client)
	@"$(PYTHON)" -m best_practices_mcp

test-contract: ## Verify ten-tool schemas and document normalization
	"$(PYTHON)" -m pytest tests/test_contracts.py tests/test_json_value_schema.py tests/test_documents.py tests/test_sdk_adapter.py

test-catalog: catalog-check ## Verify six-level source compatibility and catalog data
	"$(PYTHON)" -m pytest tests/test_criteria.py

test-protocol: ## Verify modern MCP and older-client stdio discovery and protocol errors
	"$(PYTHON)" -m pytest tests/test_stdio.py tests/test_protocol.py tests/test_read_tools.py tests/test_document_tools.py tests/test_storage_tools.py

test-package: ## Build and check an installed wheel offline with current venv dependencies
	"$(PYTHON)" scripts/check_package.py

catalog: ## Regenerate packaged catalog from pinned vendored inputs (offline)
	"$(PYTHON)" scripts/generate_catalog.py

catalog-check: ## Check catalog and provenance reproducibility without rewriting
	"$(PYTHON)" scripts/generate_catalog.py --check

.PHONY: upstream-check upstream-prepare

upstream-check: ## Compare retained BadgeApp sources with production (network, read-only)
	"$(PYTHON)" scripts/check_upstream.py

upstream-prepare: ## Prepare local source/catalog/doc updates for review (network, writes files)
	"$(PYTHON)" scripts/check_upstream.py --prepare-update

test-network: ## Verify bounded HTTP retries, pacing and cancellation (offline)
	"$(PYTHON)" -m pytest tests/test_http.py

test-api: ## Verify BadgeApp mapping and real MCP read-tool calls (offline)
	"$(PYTHON)" -m pytest tests/test_badgeapp.py tests/test_read_tools.py

.PHONY: test-badges

test-badges: ## Verify badge transport, observations, SVG artifacts and MCP calls (offline)
	"$(PYTHON)" -m pytest tests/test_http.py tests/test_badges.py tests/test_badge_tools.py

PROJECT_ID ?= 1
smoke-live: ## Opt-in paced public GET compatibility check (PROJECT_ID=1)
	"$(PYTHON)" scripts/smoke_live.py --project-id "$(PROJECT_ID)"

.PHONY: smoke-badges

smoke-badges: ## Opt-in paced JSON/SVG badge compatibility check (PROJECT_ID=1, read-only)
	"$(PYTHON)" scripts/smoke_badges.py --project-id "$(PROJECT_ID)"

.PHONY: test-upstream test-documents

test-documents: ## Verify pure patches, mechanical checks and real MCP document paths
	"$(PYTHON)" -m pytest tests/test_drafts.py tests/test_validation.py tests/test_document_tools.py tests/test_storage_tools.py

test-upstream: ## Verify documented proposal rules (offline)
	"$(PYTHON)" -m pytest tests/test_transfer_contract.py tests/test_upstream_sources.py tests/test_proposals.py

.PHONY: test-storage

test-storage: ## Verify atomic storage, concurrency, budgets and stored MCP paths (offline)
	"$(PYTHON)" -m pytest tests/test_storage.py tests/test_storage_tools.py

.PHONY: test-coverage check-fresh-package

test-coverage: ## Measure server coverage and enforce the configured total floor
	"$(PYTHON)" scripts/check_coverage.py

check-fresh-package: ## Build/install wheel and sdist in fresh temporary venvs (downloads dependencies)
	"$(PYTHON)" scripts/check_fresh_package.py --allow-downloads --output build/verification/fresh-package.json

.PHONY: lock lock-check workflow-check release-check release-build release-artifacts release-qualify

lock: ## Resolve project metadata into the cross-platform development lockfile (network)
	"$(UV)" lock $(UV_PYTHON_ARG)

lock-check: tooling-check ## Verify the committed lockfile matches project metadata
	"$(UV)" lock --check $(UV_PYTHON_ARG)

workflow-check: ## Lint tracked GitHub Actions workflows through managed actionlint
	"$(PYTHON)" -m pre_commit run actionlint --all-files

.PHONY: setup-hooks pre-commit-check

setup-hooks: ## Enable offline tests and applicable checks at commit time (optional)
	"$(PYTHON)" -m pre_commit install

pre-commit-check: ## Run all configured hooks against tracked files (no live tests)
	"$(PYTHON)" -m pre_commit run --all-files

.PHONY: scan-vulnerabilities scan-licenses

.PHONY: actionlint-inventory

actionlint-inventory: ## Generate CI-only actionlint inventory (network; requires Go and PyYAML)
	"$(PYTHON)" scripts/actionlint_inventory.py --go "$(GO)"

scan-vulnerabilities: ## Scan the Python lockfile for vulnerabilities (network; requires OSV-Scanner)
	"$(OSV_SCANNER)" --config=osv-scanner.toml --lockfile=uv.lock --no-resolve --format=sarif --output-file=osv-scanner.sarif

scan-licenses: ## Check dependency license policy and retain JSON (network; requires OSV-Scanner)
	"$(OSV_SCANNER)" --config=osv-scanner.toml --lockfile=uv.lock --no-resolve --licenses=$(OSV_LICENSES) --all-packages --format=json --output-file=osv-licenses.json

release-check: ## Check release tag/version/main identity (RELEASE_ARGS or CI environment)
	"$(PYTHON)" scripts/release_check.py source $(RELEASE_ARGS)

release-build: ## Build release candidates; choose an empty RELEASE_DIST for a new version
	"$(PYTHON)" -m build --no-isolation --outdir "$(RELEASE_DIST)"

release-artifacts: ## Verify exact candidate metadata, contents, notices and hashes (offline)
	"$(PYTHON)" scripts/dev_tools.py check-dist --dist "$(RELEASE_DIST)"
	"$(PYTHON)" scripts/release_check.py artifacts --dist "$(RELEASE_DIST)" --output "$(RELEASE_EVIDENCE)"

.PHONY: release-evidence-setup

release-evidence-setup: export UV_PROJECT_ENVIRONMENT := $(RELEASE_TOOLS_VENV)
release-evidence-setup: ## Install isolated locked SBOM tooling for release evidence only
	"$(UV)" sync --locked --only-group release-tools --no-install-project $(UV_PYTHON_ARG)

release-qualify: release-artifacts ## Install/probe the exact candidates in fresh venvs (downloads dependencies)
	"$(PYTHON)" scripts/release_check.py artifacts --dist "$(RELEASE_DIST)" --output "$(RELEASE_EVIDENCE)" --allow-downloads $(RELEASE_SBOM_ARG)

.PHONY: release-bundle

release-bundle: ## Bind qualified archives and release reports into a checksummed publication bundle
	"$(PYTHON)" scripts/release_bundle.py --dist "$(RELEASE_DIST)" --evidence "$(RELEASE_EVIDENCE)" --reports build/release/reports --output build/release/bundle
