"""Document changes preserve input data and enforce the bounded writable surface."""

from copy import deepcopy

import pytest

from best_practices_mcp.contracts import validate_output
from best_practices_mcp.criteria import field_aliases
from best_practices_mcp.documents import DOCUMENT_LIMIT_BYTES, serialize_document
from best_practices_mcp.drafts import (
    METADATA_FIELDS,
    build_draft,
    check_identity,
    field_definitions,
    normalize_draft,
    structural_issues,
)
from best_practices_mcp.errors import DomainError


def test_patch_repair_and_preservation_are_atomic() -> None:
    original = {"description_good_status": False, "extra": {"x": [None, True]}, "id": 8}
    before = deepcopy(original)
    result = build_draft(original, {"description_good_status": "Met", "name": "雪"})
    validate_output("build_draft", result)
    assert original == before
    assert result["draft"] == {**original, "description_good_status": "Met", "name": "雪"}
    assert result["issues"][0]["field"] == "extra"
    assert result["serialized_size_bytes"] == len(serialize_document(result["draft"]))
    result["draft"]["extra"]["x"].append(3)
    assert original == before


@pytest.mark.parametrize("field", ["extra", "id", "repo_url"])
def test_unknown_and_provenance_assignments_fail_even_if_present(field: str) -> None:
    original = {field: "existing"}
    with pytest.raises(DomainError) as error:
        build_draft(original, {field: "replacement"})
    assert error.value.code == "invalid_field"
    assert original == {field: "existing"}
    assert build_draft(original, {field: None})["draft"] == {}
    assert build_draft({}, {field: None})["draft"] == {}


def test_alias_patch_can_replace_canonical_base_but_conflicts_cannot_be_repaired() -> None:
    alias, canonical = next(iter(field_aliases().items()))
    assert build_draft({canonical: "Met"}, {alias: "Unmet"})["draft"] == {canonical: "Unmet"}
    with pytest.raises(DomainError):
        build_draft({canonical: "Met", alias: "Unmet"}, {canonical: None})
    with pytest.raises(DomainError):
        build_draft({}, {canonical: "Met", alias: "Unmet"})
    assert normalize_draft({canonical: "Met", alias: "Met"}) == {canonical: "Met"}


@pytest.mark.parametrize("value", [None, False, 1, {}, [], "met", ""])
def test_invalid_recognized_base_requires_repair(value: object) -> None:
    with pytest.raises(DomainError):
        build_draft({"description_good_status": value})
    assert (
        build_draft({"description_good_status": value}, {"description_good_status": None})["draft"]
        == {}
    )


def test_empty_writable_strings_and_all_statuses_are_preserved() -> None:
    for status in ("Met", "Unmet", "N/A", "?"):
        document = {
            **dict.fromkeys(METADATA_FIELDS, ""),
            "description_good_status": status,
            "description_good_justification": "",
        }
        assert build_draft(document)["draft"] == document
    assert set(METADATA_FIELDS) <= field_definitions().keys()


def test_structural_issues_sorted_and_do_not_echo_values() -> None:
    issues = structural_issues({"z": "secret", "name": [], "description_good_status": "secret"})
    assert [issue["field"] for issue in issues] == ["description_good_status", "name", "z"]
    assert "secret" not in str(issues)


def test_combined_document_budget_is_enforced_after_patch() -> None:
    original = {"description": "a" * (DOCUMENT_LIMIT_BYTES // 2)}
    with pytest.raises(DomainError) as error:
        build_draft(original, {"name": "b" * (DOCUMENT_LIMIT_BYTES // 2)})
    assert error.value.code == "document_too_large"
    assert "name" not in original


@pytest.mark.parametrize("identity", [None, True, 0, -1, "8", 8.0])
def test_invalid_id_is_unresolved(identity: object) -> None:
    with pytest.raises(DomainError) as error:
        check_identity(8, {"id": identity})
    assert error.value.code == "project_identity_unresolved"


@pytest.mark.parametrize("project_id", [None, True, 0, -1, "8", 8.0])
@pytest.mark.parametrize("draft", [{}, {"id": 8}])
def test_invalid_requested_id_cannot_establish_association(project_id, draft) -> None:
    with pytest.raises(DomainError, match="Project ID must be a positive integer") as error:
        check_identity(project_id, draft)
    assert error.value.code == "project_identity_unresolved"


def test_identity_association_and_id_mismatch() -> None:
    assert check_identity(8, {}) == {
        "association": "explicit_target",
        "id_check": "absent",
        "repo_check": "not_checked",
    }
    assert check_identity(8, {"id": 8})["association"] == "document_provenance"
    assert check_identity(8, {"repo_url": None})["repo_check"] == "not_checked"
    assert check_identity(8, {}, check_repo=True)["repo_check"] == "absent"
    with pytest.raises(DomainError) as error:
        check_identity(8, {"id": 9})
    assert error.value.code == "project_mismatch"


@pytest.mark.parametrize(
    "url", ["HTTPS://EXAMPLE.COM:443/Org/Repo?q=x#f", "https://example.com/Org/Repo?q=x#f"]
)
def test_repository_comparison_normalizes_only_documented_parts(url: str) -> None:
    assert (
        check_identity(
            8,
            {"repo_url": url},
            record={"repo_url": "https://example.com/Org/Repo?q=x#f"},
            check_repo=True,
        )["repo_check"]
        == "matched"
    )


@pytest.mark.parametrize(
    "suffix", ["/org/Repo", "/Org/Repo/", "/Org/Repo.git", "/Org/Repo?q=1", "/Org/%52epo"]
)
def test_repository_distinctions_remain_mismatches(suffix: str) -> None:
    with pytest.raises(DomainError) as error:
        check_identity(
            8,
            {"repo_url": "https://example.com" + suffix},
            record={"repo_url": "https://example.com/Org/Repo"},
            check_repo=True,
        )
    assert error.value.code == "project_mismatch"


@pytest.mark.parametrize(
    "url",
    [
        None,
        1,
        "relative",
        "\x00https://example.com/x",
        "\x01https://example.com/x",
        "https://example.com/\x1fx",
        "ftp://example.com/x",
        "https://u:p@example.com/x",
        "https://example.com:bad/x",
        "https://[bad",
        "https://example.com/ bad",
    ],
)
def test_unusable_repository_provenance_is_unresolved(url: object) -> None:
    with pytest.raises(DomainError) as error:
        check_identity(
            8, {"repo_url": url}, record={"repo_url": "https://example.com/x"}, check_repo=True
        )
    assert error.value.code == "project_identity_unresolved"


def test_missing_upstream_repository_is_unresolved() -> None:
    with pytest.raises(DomainError) as error:
        check_identity(8, {"repo_url": "https://example.com/x"}, record={}, check_repo=True)
    assert error.value.code == "project_identity_unresolved"
