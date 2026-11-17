# Fuzzing

Two offline [Atheris](https://github.com/google/atheris) targets exercise document and proposal boundaries:

- `scripts/fuzz_documents.py` passes arbitrary bytes to the document parser. Expected domain errors are accepted only at that boundary. Accepted documents must serialize and reparse without error, with stable canonical bytes regardless of object key order.
- `scripts/fuzz_proposals.py` decodes arbitrary bytes into text, constructs a valid draft, and passes it through document serialization and parsing before URL generation. It verifies exact query values (including the explicit override), the fixed destination, byte accounting, unchanged input, and independence from draft key order. Invalid UTF-8 is replaced so every input reaches URL generation.

Neither target contacts BadgeApp. These checks complement the ordinary unit tests and coverage floor; fuzz runs do not contribute to the reported coverage percentage.

## Running locally

The locked Atheris 3.1.0 distribution provides Linux x86_64 wheels for Python 3.12–3.14. Use Linux x86_64 for these commands. Normal development setup does not install the optional `fuzz` group, so macOS, Windows and Python 3.11 contributors can continue to run the regular suite.

```sh
make setup-fuzz
make fuzz
```

`setup-fuzz` defaults to Python 3.12 and installs the locked development and fuzz groups in the selected project environment (`.venv` by default). It may replace an existing Python 3.11 environment; `make setup` restores normal development setup. It does not create a second top-level virtual environment.

Each target runs for 30 seconds by default, with a 64 KiB input limit and a ten-second per-input timeout. The unit suite retains the explicit document size and nesting boundary cases. Increase the fuzzing duration or run just one target:

```sh
make fuzz FUZZ_SECONDS=300
make fuzz-documents FUZZ_ARGS="-seed=123 -runs=10000"
make fuzz-proposals FUZZ_SECONDS=60
```

`FUZZ_ARGS` passes additional native libFuzzer options. The proposal target constructs two text fields from each input; keep its input limit at 64 KiB to remain within the document byte budget even when JSON escaping expands control characters.

Committed seed inputs live in `tests/fuzz/`. Generated corpus entries and failure inputs go to `build/fuzz/<target>/`, which is ignored by Git. The first corpus directory is writable; committed seeds are read from the second. Preserve a useful generated input as a new seed when it exercises behavior worth keeping.

## Failures and CI

The Fuzzing workflow runs both targets on Linux/Python 3.12 for pull requests, pushes to `main`, and manual runs. It attempts both targets even if one fails and retains the generated corpora and any failure inputs for 14 days. Unexpected exceptions, failed assertions, crashes and timeouts fail the job.

Download a failure input and replay it with the matching harness:

```sh
.venv/bin/python scripts/fuzz_documents.py path/to/crash-input
.venv/bin/python scripts/fuzz_proposals.py path/to/crash-input
```

A file argument replays that input without starting an open-ended fuzz run. Investigate the failure and add an ordinary regression test for a confirmed bug before fixing it. A time-bounded passing run means only that no failure was found during that run.

The optional dependency is inventoried in `uv.lock` and included in the existing OSV vulnerability and license scans. `osv-scanner.toml` corrects missing registry license metadata for Atheris 3.1.0 to Apache-2.0, verified against the published wheel's license. Recheck that evidence when updating Atheris; vulnerability scanning remains enabled.
