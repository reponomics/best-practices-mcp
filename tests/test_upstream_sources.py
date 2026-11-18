"""The retained upstream sources are the files their manifest describes."""

from pathlib import Path

import check_upstream

SOURCE = Path(__file__).resolve().parents[1] / "vendor/badgeapp"


def test_retained_sources_match_their_manifest():
    # read_baseline raises on a hash mismatch or an unexpected set of paths.
    revision, hashes = check_upstream.read_baseline(SOURCE)
    assert revision
    assert set(hashes) == set(check_upstream.SOURCE_FILES)
