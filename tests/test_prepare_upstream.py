"""Prepare real upstream snapshots for review without modifying runtime code or tests."""

import importlib
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from scripts import check_upstream as check

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
prepare = importlib.import_module("prepare_upstream")
PRODUCTION = "b" * 40
TIMESTAMP = "2026-11-13T15:00:00Z"
GENERATED = ("catalog.json", "provenance.json", "BADGEAPP-LICENSE.txt")


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    shutil.copytree(ROOT / "vendor/badgeapp", root / "vendor/badgeapp")
    names = [
        *prepare.DOC_PINS,
        *(f"src/best_practices_mcp/data/{name}" for name in GENERATED),
        "src/best_practices_mcp/criteria.py",
        "tests/test_criteria.py",
        "docs/planning/initial-implementation/badgeapp-mcp-upstream-baseline.md",
    ]
    for name in names:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    return root


@pytest.fixture
def client():
    value = Mock(spec=check.GitHub)
    value.api.return_value = {"sha": PRODUCTION, "committer": {"date": TIMESTAMP}}
    return value


def read_tree(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def remote_files(root):
    return {name: (root / "vendor/badgeapp" / name).read_bytes() for name in check.SOURCE_FILES}


def report_for(root, remote):
    revision, hashes = check.read_baseline(root / "vendor/badgeapp")
    return check.Report(revision, PRODUCTION, hashes, remote)


def load_yaml(contents, name):
    return yaml.load(contents[name], Loader=prepare.SourceLoader)


def replace_yaml(contents, name, value):
    contents[name] = yaml.safe_dump(value, sort_keys=False, allow_unicode=True).encode("utf-8")


def change_wording(remote):
    locale = load_yaml(remote, "config/locales/en.yml")
    locale["en"]["criteria"]["0"]["description_good"]["description"] = "Updated upstream wording."
    replace_yaml(remote, "config/locales/en.yml", locale)


def generated_catalog(root):
    return json.loads(
        (root / "src/best_practices_mcp/data/catalog.json").read_text(encoding="utf-8")
    )


def prepared_result(output):
    return json.loads((output / "result.json").read_text(encoding="utf-8"))


def test_wording_refresh_regenerates_manifest_catalog_provenance_and_documentation(
    checkout, client, tmp_path
):
    before = read_tree(checkout)
    remote = remote_files(checkout)
    change_wording(remote)
    report = report_for(checkout, remote)
    output = tmp_path / "reports"
    body = prepare.prepare_update(client, report, checkout, output)
    result = prepared_result(output)
    assert result["generation_error"] is None
    assert result["ids"] == {"added": [], "removed": [], "error": None}
    assert "regenerated successfully" in body
    source = checkout / "vendor/badgeapp"
    manifest = json.loads((source / "source.json").read_text())
    assert manifest["revision"] == PRODUCTION
    assert manifest["generated_at"] == TIMESTAMP
    assert manifest["files"] == report.production_hashes
    assert all((source / name).read_bytes() == content for name, content in remote.items())
    catalog = generated_catalog(checkout)
    assert catalog["catalog"]["revision"] == PRODUCTION
    assert catalog["catalog"]["generated_at"] == TIMESTAMP
    selected = next(row for row in catalog["criteria"] if row["criterion_id"] == "description_good")
    assert selected["description"] == "Updated upstream wording."
    assert PRODUCTION in selected["source_url"]
    provenance = json.loads((checkout / "src/best_practices_mcp/data/provenance.json").read_text())
    assert provenance["files"] == manifest["files"]
    assert provenance["revision"] == PRODUCTION
    for name in prepare.DOC_PINS:
        assert (checkout / name).read_bytes() == before[name].replace(
            report.bundled_revision.encode(), PRODUCTION.encode()
        )
    managed = {
        *(f"vendor/badgeapp/{name}" for name in check.SOURCE_FILES),
        "vendor/badgeapp/source.json",
        *(f"src/best_practices_mcp/data/{name}" for name in GENERATED),
        *prepare.DOC_PINS,
    }
    after = read_tree(checkout)
    assert {name for name in before if before[name] != after[name]} <= managed
    assert (
        after["src/best_practices_mcp/criteria.py"] == before["src/best_practices_mcp/criteria.py"]
    )
    assert after["tests/test_criteria.py"] == before["tests/test_criteria.py"]
    historical = "docs/planning/initial-implementation/badgeapp-mcp-upstream-baseline.md"
    assert after[historical] == before[historical]


def test_condition_change_flows_through_generation_without_id_classification(
    checkout, client, tmp_path
):
    remote = remote_files(checkout)
    criteria = load_yaml(remote, "criteria/criteria.yml")
    criteria["0"]["Basics"]["Basic project website content"]["description_good"][
        "met_url_required"
    ] = True
    replace_yaml(remote, "criteria/criteria.yml", criteria)
    output = tmp_path / "reports"
    prepare.prepare_update(client, report_for(checkout, remote), checkout, output)
    result = prepared_result(output)
    assert result["generation_error"] is None
    assert result["ids"] == {"added": [], "removed": [], "error": None}
    criterion = next(
        row
        for row in generated_catalog(checkout)["criteria"]
        if row["criterion_id"] == "description_good"
    )
    assert criterion["met_url_required"] is True
    assert criterion["met_justification_required"] is True


@pytest.mark.parametrize(
    "name", ["docs/automation-approach.md", "docs/automation-proposals.md", "LICENSE"]
)
def test_retained_document_and_notice_changes_are_prepared(checkout, client, tmp_path, name):
    remote = remote_files(checkout)
    remote[name] += b"\nUpdated upstream text.\n"
    report = report_for(checkout, remote)
    assert report.changed == [name]
    output = tmp_path / "reports"
    prepare.prepare_update(client, report, checkout, output)
    assert prepared_result(output)["generation_error"] is None
    assert (checkout / "vendor/badgeapp" / name).read_bytes() == remote[name]
    provenance = json.loads((checkout / "src/best_practices_mcp/data/provenance.json").read_text())
    assert provenance["files"][name] == report.production_hashes[name]
    if name == "LICENSE":
        assert (
            checkout / "src/best_practices_mcp/data/BADGEAPP-LICENSE.txt"
        ).read_bytes() == remote[name]


def test_added_removed_ids_are_advisory_and_do_not_prevent_generation(checkout, client, tmp_path):
    remote = remote_files(checkout)
    criteria = load_yaml(remote, "criteria/criteria.yml")
    group = criteria["0"]["Basics"]["Basic project website content"]
    group["new_description"] = group.pop("description_good")
    replace_yaml(remote, "criteria/criteria.yml", criteria)
    locale = load_yaml(remote, "config/locales/en.yml")
    texts = locale["en"]["criteria"]["0"]
    texts["new_description"] = texts.pop("description_good")
    replace_yaml(remote, "config/locales/en.yml", locale)
    output = tmp_path / "reports"
    body = prepare.prepare_update(client, report_for(checkout, remote), checkout, output)
    result = prepared_result(output)
    assert result["generation_error"] is None
    assert result["ids"] == {
        "added": ["0/new_description"],
        "removed": ["0/description_good"],
        "error": None,
    }
    assert "0/new_description" in body
    ids = {row["criterion_id"] for row in generated_catalog(checkout)["criteria"]}
    assert "new_description" in ids
    assert "description_good" not in ids


def test_unchanged_inputs_do_not_rewrite_repository_or_fetch_commit_metadata(
    checkout, client, tmp_path
):
    before = read_tree(checkout)
    report = report_for(checkout, remote_files(checkout))
    output = tmp_path / "reports"
    assert prepare.prepare_update(client, report, checkout, output) == ""
    assert read_tree(checkout) == before
    client.api.assert_not_called()
    assert prepared_result(output)["changed"] is False


@pytest.mark.parametrize("missing_source", [False, True])
def test_same_base_and_upstream_snapshot_produce_identical_patch(
    checkout, client, tmp_path, missing_source
):
    second = tmp_path / "second"
    shutil.copytree(checkout, second)
    remote = remote_files(checkout)
    change_wording(remote)
    if missing_source:
        remote["criteria/criteria.yml"] = None
    report = report_for(checkout, remote)
    first_body = prepare.prepare_update(client, report, checkout, tmp_path / "first-report")
    second_body = prepare.prepare_update(client, report, second, tmp_path / "second-report")
    assert read_tree(checkout) == read_tree(second)
    assert first_body == second_body
    assert prepared_result(tmp_path / "first-report") == prepared_result(tmp_path / "second-report")
    if missing_source:
        assert "Retained upstream source files are missing: criteria/criteria.yml" in first_body


@pytest.mark.parametrize("name", check.SOURCE_FILES)
def test_missing_upstream_input_still_prepares_reviewable_patch(checkout, client, tmp_path, name):
    before = read_tree(checkout)
    remote = remote_files(checkout)
    remote[name] = None
    report = report_for(checkout, remote)
    output = tmp_path / "reports"
    body = prepare.prepare_update(client, report, checkout, output)
    assert "Catalog generation failed" in body
    assert prepared_result(output)["generation_error"] == (
        f"Retained upstream source files are missing: {name}"
    )
    assert not (checkout / "vendor/badgeapp" / name).exists()
    manifest = json.loads((checkout / "vendor/badgeapp/source.json").read_text())
    assert manifest["revision"] == PRODUCTION
    assert name not in manifest["files"]
    for name in GENERATED:
        path = f"src/best_practices_mcp/data/{name}"
        assert (checkout / path).read_bytes() == before[path]


def test_malformed_yaml_preserves_source_patch_and_reports_advisory_and_generation_errors(
    checkout, client, tmp_path
):
    remote = remote_files(checkout)
    remote["criteria/criteria.yml"] = b"invalid: [\n"
    output = tmp_path / "reports"
    body = prepare.prepare_update(client, report_for(checkout, remote), checkout, output)
    result = prepared_result(output)
    assert result["ids"]["error"]
    assert result["generation_error"]
    assert "Comparison unavailable" in body
    assert (checkout / "vendor/badgeapp/criteria/criteria.yml").read_bytes() == b"invalid: [\n"


def test_generation_failure_keeps_old_outputs_but_refreshes_sources_and_docs(
    checkout, client, tmp_path, monkeypatch
):
    before = read_tree(checkout)
    remote = remote_files(checkout)
    change_wording(remote)
    report = report_for(checkout, remote)
    monkeypatch.setattr(
        prepare, "catalog_content", Mock(side_effect=RuntimeError("schema changed"))
    )
    output = tmp_path / "reports"
    body = prepare.prepare_update(client, report, checkout, output)
    assert "schema changed" in body
    assert prepared_result(output)["generation_error"] == "RuntimeError: schema changed"
    assert (checkout / "vendor/badgeapp/config/locales/en.yml").read_bytes() == remote[
        "config/locales/en.yml"
    ]
    for name in GENERATED:
        path = f"src/best_practices_mcp/data/{name}"
        assert (checkout / path).read_bytes() == before[path]
    for name in prepare.DOC_PINS:
        assert (checkout / name).read_bytes() == before[name].replace(
            report.bundled_revision.encode(), PRODUCTION.encode()
        )


def test_missing_managed_document_fails_before_repository_writes(checkout, client, tmp_path):
    (checkout / prepare.DOC_PINS[0]).unlink()
    before = read_tree(checkout)
    remote = remote_files(checkout)
    change_wording(remote)
    with pytest.raises(FileNotFoundError):
        prepare.prepare_update(client, report_for(checkout, remote), checkout, tmp_path / "reports")
    assert read_tree(checkout) == before


@pytest.mark.parametrize(
    "metadata",
    [
        {"sha": "a" * 40, "committer": {"date": TIMESTAMP}},
        {"sha": PRODUCTION, "committer": {"date": "2026-11-13T15:00:00"}},
        {"sha": PRODUCTION, "committer": {"date": "not-a-date"}},
    ],
)
def test_invalid_commit_metadata_does_not_modify_repository(checkout, client, tmp_path, metadata):
    before = read_tree(checkout)
    remote = remote_files(checkout)
    change_wording(remote)
    client.api.return_value = metadata
    with pytest.raises(ValueError):
        prepare.prepare_update(client, report_for(checkout, remote), checkout, tmp_path / "reports")
    assert read_tree(checkout) == before


def test_source_timestamp_is_normalized_to_utc(client):
    client.api.return_value = {
        "sha": PRODUCTION,
        "committer": {"date": "2026-11-13T10:00:00-05:00"},
    }
    assert prepare.source_timestamp(client, PRODUCTION) == TIMESTAMP


def test_error_details_are_bounded_escaped_and_do_not_mention_users():
    escaped = prepare.error_text("<script>@maintainer</script>" + "x" * 2000)
    assert "<script>" not in escaped
    assert "@maintainer" not in escaped
    assert "&lt;script&gt;" in escaped
    assert "&#64;maintainer" in escaped
    assert escaped.count("x") < 1500
