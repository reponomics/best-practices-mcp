.DEFAULT_GOAL := help

BOOTSTRAP_PYTHON ?= python3
VENV ?= venv
PYTHON ?= $(VENV)/bin/python
PIP ?= $(PYTHON) -m pip
NPM ?= npm
NODE ?= node
UV ?= $(VENV)/bin/uv
ACTIONLINT ?= actionlint
RELEASE_DIST ?= build/release/dist
RELEASE_EVIDENCE ?= build/release/evidence.json
RELEASE_ARGS ?=

.PHONY: help setup check test format build run example test-contract test-catalog test-protocol test-package catalog catalog-check test-network test-api test-host host smoke-live

help: ## Show available development commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

$(VENV)/pyvenv.cfg:
	$(BOOTSTRAP_PYTHON) -m venv $(VENV)

setup: $(VENV)/pyvenv.cfg ## Create venv and install this package with development tools
	$(PIP) install -e '.[dev]'

check: ## Check formatting, lint, dependency consistency, and tests
	$(PYTHON) -m ruff format --check src tests examples scripts
	$(PYTHON) -m ruff check src tests examples scripts
	$(PIP) check
	$(MAKE) test

test: ## Run offline unit and MCP subprocess integration tests
	$(PYTHON) -m pytest

format: ## Format Python source, tests, and examples
	$(PYTHON) -m ruff format src tests examples scripts

build: ## Build source and wheel distributions
	$(PYTHON) -m build

run: ## Run the stdio server (waits for an MCP client)
	@$(PYTHON) -m best_practices_mcp

example: ## Discover implemented tools through the reference host (offline)
	$(PYTHON) examples/host.py --discover

test-contract: ## Verify nine-tool schemas and document normalization
	$(PYTHON) -m pytest tests/test_contracts.py tests/test_json_value_schema.py tests/test_documents.py tests/test_sdk_adapter.py

test-catalog: catalog-check ## Verify six-level source compatibility and catalog data
	$(PYTHON) -m pytest tests/test_criteria.py

test-protocol: ## Verify modern MCP and older-client stdio discovery and protocol errors
	$(PYTHON) -m pytest tests/test_stdio.py tests/test_protocol.py tests/test_read_tools.py tests/test_document_tools.py tests/test_storage_tools.py

test-package: ## Build and check an installed wheel offline with current venv dependencies
	$(PYTHON) scripts/check_package.py

catalog: ## Regenerate packaged catalog from pinned vendored inputs (offline)
	$(PYTHON) scripts/generate_catalog.py

catalog-check: ## Check catalog and provenance reproducibility without rewriting
	$(PYTHON) scripts/generate_catalog.py --check

.PHONY: upstream-check

upstream-check: ## Compare bundled criteria/locale with upstream production (network, read-only)
	$(PYTHON) scripts/check_upstream.py

test-network: ## Verify bounded HTTP retries, pacing and cancellation (offline)
	$(PYTHON) -m pytest tests/test_http.py

test-api: ## Verify BadgeApp mapping and real MCP read-tool calls (offline)
	$(PYTHON) -m pytest tests/test_badgeapp.py tests/test_read_tools.py

test-host: ## Verify interactive host lookup and selection through MCP (offline)
	$(PYTHON) -m pytest tests/test_host.py

host: ## Start the interactive document host (queries contact BadgeApp)
	$(PYTHON) examples/host.py

PROJECT_ID ?= 1
smoke-live: ## Opt-in paced public GET compatibility check (PROJECT_ID=1)
	$(PYTHON) scripts/smoke_live.py --project-id "$(PROJECT_ID)"

.PHONY: setup-dom test-upstream test-documents

setup-dom: ## Install locked development-only DOM tooling (Node 24 via nvm)
	$(NPM) ci --ignore-scripts

test-documents: ## Verify pure patches, mechanical checks and real MCP document paths
	$(PYTHON) -m pytest tests/test_drafts.py tests/test_validation.py tests/test_document_tools.py tests/test_storage_tools.py

test-upstream: ## Verify documented proposal rules and agreed script behavior (offline)
	NODE="$(NODE)" $(PYTHON) -m pytest tests/test_transfer_contract.py tests/test_upstream_sources.py tests/test_proposals.py tests/test_scripts.py

.PHONY: test-storage host-stored

test-storage: ## Verify atomic storage, concurrency, budgets and stored MCP paths (offline)
	$(PYTHON) -m pytest tests/test_storage.py tests/test_storage_tools.py

host-stored: ## Start the opt-in stored host; edits write server-local drafts
	$(PYTHON) examples/host.py --mode stored

.PHONY: test-coverage check-fresh-package

test-coverage: ## Measure server coverage including MCP subprocesses and write HTML/XML reports
	$(PYTHON) scripts/check_coverage.py

check-fresh-package: ## Build/install wheel and sdist in fresh temporary venvs (downloads dependencies)
	$(PYTHON) scripts/check_fresh_package.py --allow-downloads --output build/verification/fresh-package.json

.PHONY: lock lock-check workflow-check release-check release-build release-artifacts release-qualify

lock: ## Refresh the cross-platform development dependency inventory (network)
	$(UV) lock

lock-check: ## Verify the committed dependency inventory matches project metadata
	$(UV) lock --check

workflow-check: ## Lint all GitHub Actions workflows (requires actionlint)
	$(ACTIONLINT)

release-check: ## Check release tag/version/main identity (RELEASE_ARGS or CI environment)
	$(PYTHON) scripts/release_check.py source $(RELEASE_ARGS)

release-build: ## Build release candidates; choose an empty RELEASE_DIST for a new version
	$(PYTHON) -m build --no-isolation --outdir "$(RELEASE_DIST)"

release-artifacts: ## Verify exact candidate metadata, contents, notices and hashes (offline)
	$(PYTHON) -m twine check --strict "$(RELEASE_DIST)"/*
	$(PYTHON) scripts/release_check.py artifacts --dist "$(RELEASE_DIST)" --output "$(RELEASE_EVIDENCE)"

release-qualify: release-artifacts ## Install/probe the exact candidates in fresh venvs (downloads dependencies)
	$(PYTHON) scripts/release_check.py artifacts --dist "$(RELEASE_DIST)" --output "$(RELEASE_EVIDENCE)" --allow-downloads
