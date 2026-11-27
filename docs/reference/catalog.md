# Criteria catalog

This document describes the criteria catalog that the server packages: where it comes from, what the generator does to the upstream data, and how to regenerate it.

## What it is

The catalog is two files in `src/best_practices_mcp/data/`:

- `catalog.json` holds every criterion of the six levels.
- `provenance.json` records where the catalog came from.

`scripts/generate_catalog.py` produces both files from the pinned upstream sources in `vendor/badgeapp/`: the two criteria YAML files and the English locale file. The server reads criteria only from the packaged catalog. It never fetches criteria from the network.

The criterion text is upstream material under its own license. [Third-party notices](../../THIRD_PARTY_NOTICES.md) gives the terms.

## What a criterion record holds

Each record has the criterion ID, its level, its category, the requirement word (such as MUST), the description and details text, the names of its status and justification fields, and four flags: whether N/A is allowed, and whether a justification or a URL is required for a Met or an N/A answer.

## Generation rules

The generator copies upstream values and applies these rules:

- **Order.** Within a level, the catalog lists criteria in the order of the criteria YAML, which is the order of BadgeApp's edit form. The server returns criteria in that order and names each category where its first criterion appears. The Metal levels' categories are upstream's own groups, so their order is upstream's. A Baseline category is derived from each identifier (see Category), so the order of Baseline categories follows from the order of the criteria, and nothing upstream keeps the criteria of one category together.
- **Category.** The category is the major group in the criteria YAML. The Baseline levels are an exception, because upstream puts every Baseline criterion in one group. For those, the generator reads the two-letter code in the identifier and looks it up in the "OSPS category codes" table of the pinned automation proposals document. A code that is not in the table fails the generation.
- **Aliases.** A Baseline criterion also carries its display identifier as an alias.
- **Details.** A criterion without details text of its own takes the details of the same criterion at the nearest lower level that has them. BadgeApp applies the same rule.
- **Implied flags.** A required URL implies a required justification. A required justification for N/A implies that N/A is allowed. The generator sets the implied flag even when the YAML omits it.
- **Lifecycle.** Upstream can mark a criterion `obsolete` or `future`. The generator leaves such a criterion out of the catalog and lists it under `excluded_criteria` in the provenance file.

A flag with a value that is not a Boolean fails the generation.

## Provenance

`provenance.json` records the upstream revision and its commit time, the hash of each source file, the hash of the generator script, the per-level criterion counts and the excluded criteria.

`catalog.json` holds no revision or timestamp. A new upstream revision with unchanged criteria changes only `provenance.json`.

The server builds the catalog reference and source links in its responses from the provenance file.

## Regenerating

| Command | What it does |
| --- | --- |
| `make catalog` | Regenerates both files from `vendor/badgeapp/` |
| `make catalog-check` | Fails if the committed files differ from what the generator produces |

`make catalog-check` runs in CI and in the pre-commit hooks.

The provenance file records the hash of the generator script. Any edit to `scripts/generate_catalog.py`, including a change to a comment, changes that hash. Run `make catalog` after such an edit and commit the new `provenance.json`.

[Upstream updates](../maintenance/upstream-updates.md) describes how the pinned sources change.
