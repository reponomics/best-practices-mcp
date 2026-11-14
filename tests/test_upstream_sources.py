"""Verify integrity of the retained upstream documents, criteria and locale.

Synthetic form source references record derivation, not live-site conformance.
"""

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
