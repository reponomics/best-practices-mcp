"""Verify integrity of the retained upstream documents, criteria and locale."""

import hashlib
import json
from pathlib import Path

from scripts import check_upstream

ROOT = Path(__file__).resolve().parents[1]


def test_retained_source_hashes():
    source = ROOT / "vendor/badgeapp"
    manifest = json.loads((source / "source.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected


def test_required_retained_sources_form_a_complete_verified_baseline():
    source = ROOT / "vendor/badgeapp"
    revision, hashes = check_upstream.read_baseline(source)
    manifest = json.loads((source / "source.json").read_text(encoding="utf-8"))
    assert revision == manifest["revision"]
    assert hashes == manifest["files"]
    assert set(hashes) == set(check_upstream.SOURCE_FILES)


def test_active_revision_is_owned_only_by_source_and_packaged_provenance():
    manifest = ROOT / "vendor/badgeapp/source.json"
    revision = json.loads(manifest.read_text(encoding="utf-8"))["revision"]
    candidates = [manifest, *ROOT.glob("*.md"), *ROOT.glob("*.toml"), ROOT / "Makefile"]
    for directory in ("src", "scripts", "docs", ".github"):
        candidates.extend(
            path
            for path in (ROOT / directory).rglob("*")
            if path.is_file()
            and path.suffix in {".py", ".json", ".md", ".yml", ".yaml", ".toml"}
            and not set(path.relative_to(ROOT).parts[:2]) & {"adr", "planning", "archive"}
        )
    occurrences = {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8").count(revision)
        for path in candidates
        if revision in path.read_text(encoding="utf-8")
    }
    assert occurrences == {
        "vendor/badgeapp/source.json": 1,
        "src/best_practices_mcp/data/provenance.json": 1,
    }
