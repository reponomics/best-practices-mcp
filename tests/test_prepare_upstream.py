"""Preparing an upstream snapshot for review: what is written, and what is reported.

The checkout here is synthetic. Catalog generation is replaced by a stand-in that echoes
the sources it was given, because the generator has its own tests in test_criteria.py.
"""

import hashlib
import importlib
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import check_upstream as check

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
prepare = importlib.import_module("prepare_upstream")
BASE = "a" * 40
PRODUCTION = "b" * 40
TIMESTAMP = "2026-11-13T15:00:00Z"
CHANGED = check.SOURCE_FILES[0]
GENERATED = "src/best_practices_mcp/data/generated.bin"


def generated_from(source: Path) -> dict[str, bytes]:
    """Stand in for catalog generation with output that depends on the sources read."""
    return {
        "generated.bin": (source / CHANGED).read_bytes() + (source / "source.json").read_bytes()
    }


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A checkout with a valid bundled snapshot, generated data and one unrelated file."""
    root = tmp_path / "checkout"
    source = root / "vendor/badgeapp"
    hashes = {}
    for name in check.SOURCE_FILES:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"bundled {name}".encode())
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"repository": check.UPSTREAM_URL, "revision": BASE, "files": hashes}
    (source / "source.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name, content in ((GENERATED, b"previous generated data"), ("unrelated/file", b"kept")):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(content)
    monkeypatch.setattr(prepare, "catalog_content", generated_from)
    return root


@pytest.fixture
def client():
    value = Mock(spec=check.GitHub)
    value.api.return_value = {"sha": PRODUCTION, "committer": {"date": TIMESTAMP}}
    return value


def read_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def production(checkout: Path, **changes: bytes | None) -> check.Report:
    """A report whose production files are the bundled ones with `changes` applied."""
    source = checkout / "vendor/badgeapp"
    revision, hashes = check.read_baseline(source)
    remote = {name: (source / name).read_bytes() for name in check.SOURCE_FILES}
    return check.Report(revision, PRODUCTION, hashes, remote | changes)


def result(output: Path) -> dict:
    return json.loads((output / "result.json").read_text(encoding="utf-8"))


def test_changed_snapshot_is_written_with_its_manifest_and_regenerated_data(
    checkout, client, tmp_path
):
    before = read_tree(checkout)
    report = production(checkout, **{CHANGED: b"updated upstream text"})
    output = tmp_path / "reports"
    assert prepare.prepare_update(client, report, checkout, output)
    assert result(output) == {"changed": True, "generation_error": None}
    after = read_tree(checkout)
    assert {name for name in after if after[name] != before.get(name)} == {
        f"vendor/badgeapp/{CHANGED}",
        "vendor/badgeapp/source.json",
        GENERATED,
    }
    assert json.loads(after["vendor/badgeapp/source.json"]) == {
        "repository": check.UPSTREAM_URL,
        "revision": PRODUCTION,
        "generated_at": TIMESTAMP,
        "files": report.production_hashes,
    }
    source = checkout / "vendor/badgeapp"
    assert after[GENERATED] == generated_from(source)["generated.bin"]
    # The refreshed snapshot is a valid baseline that no longer differs from production.
    revision, hashes = check.read_baseline(source)
    assert revision == PRODUCTION
    assert check.Report(revision, PRODUCTION, hashes, report.production_files).changed == []


def test_unchanged_snapshot_writes_nothing_and_makes_no_request(checkout, client, tmp_path):
    before = read_tree(checkout)
    output = tmp_path / "reports"
    assert prepare.prepare_update(client, production(checkout), checkout, output) == ""
    assert read_tree(checkout) == before
    assert result(output) == {"changed": False, "generation_error": None}
    client.api.assert_not_called()


def test_same_snapshot_prepares_identical_patches_in_two_checkouts(checkout, client, tmp_path):
    second = tmp_path / "second"
    shutil.copytree(checkout, second)
    report = production(checkout, **{CHANGED: b"updated upstream text"})
    first_body = prepare.prepare_update(client, report, checkout, tmp_path / "first")
    second_body = prepare.prepare_update(client, report, second, tmp_path / "second-report")
    assert read_tree(checkout) == read_tree(second)
    assert first_body == second_body


def test_file_missing_upstream_becomes_a_reviewable_deletion_without_new_generated_data(
    checkout, client, tmp_path
):
    before = read_tree(checkout)
    output = tmp_path / "reports"
    report = production(checkout, **{CHANGED: None})
    body = prepare.prepare_update(client, report, checkout, output)
    after = read_tree(checkout)
    assert f"vendor/badgeapp/{CHANGED}" not in after
    manifest = json.loads(after["vendor/badgeapp/source.json"])
    assert manifest["revision"] == PRODUCTION
    assert CHANGED not in manifest["files"]
    assert after[GENERATED] == before[GENERATED]
    assert CHANGED in result(output)["generation_error"]
    assert CHANGED in body


def test_generation_failure_keeps_previous_generated_data_beside_new_sources(
    checkout, client, tmp_path, monkeypatch
):
    before = read_tree(checkout)
    monkeypatch.setattr(prepare, "catalog_content", Mock(side_effect=KeyError("schema changed")))
    output = tmp_path / "reports"
    report = production(checkout, **{CHANGED: b"updated"})
    body = prepare.prepare_update(client, report, checkout, output)
    after = read_tree(checkout)
    assert after[f"vendor/badgeapp/{CHANGED}"] == b"updated"
    assert after[GENERATED] == before[GENERATED]
    assert "schema changed" in result(output)["generation_error"]
    assert "schema changed" in body


@pytest.mark.parametrize(
    "metadata",
    [
        {"sha": BASE, "committer": {"date": TIMESTAMP}},
        {"sha": PRODUCTION, "committer": {"date": "2026-11-13T15:00:00"}},
        {"sha": PRODUCTION, "committer": {"date": "not-a-date"}},
    ],
    ids=["another commit", "no timezone", "not a date"],
)
def test_invalid_commit_metadata_is_refused_before_anything_is_written(
    checkout, client, tmp_path, metadata
):
    before = read_tree(checkout)
    client.api.return_value = metadata
    report = production(checkout, **{CHANGED: b"updated"})
    with pytest.raises(ValueError):
        prepare.prepare_update(client, report, checkout, tmp_path / "reports")
    assert read_tree(checkout) == before


def test_source_timestamp_is_normalized_to_utc(client):
    client.api.return_value = {
        "sha": PRODUCTION,
        "committer": {"date": "2026-11-13T10:00:00-05:00"},
    }
    assert prepare.source_timestamp(client, PRODUCTION) == TIMESTAMP


def test_error_text_in_the_review_body_is_bounded_escaped_and_mentions_no_user():
    # Policy: upstream-controlled error text must not inject markup or notify people in a PR.
    escaped = prepare.error_text("<script>@maintainer</script>" + "x" * 2000)
    assert "<script>" not in escaped
    assert "@maintainer" not in escaped
    assert escaped.count("x") < 1500
