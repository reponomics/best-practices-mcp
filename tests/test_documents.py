"""Structural parsing is independent of fields, persistence and future patch policy."""

import sys

import pytest

from best_practices_mcp.documents import (
    DOCUMENT_LIMIT_BYTES,
    MAX_JSON_DEPTH,
    normalize_document,
    parse_document,
    serialize_document,
    validate_document,
)
from best_practices_mcp.errors import DomainError


@pytest.mark.parametrize(
    "raw",
    [
        b'{"x":1,"x":2}',
        b'{"outer":{"x":1,"x":1}}',
        b"[]",
        b"null",
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1e999}',
        b'{"x":"\\ud800"}',
        b"\xff",
        b"{",
    ],
)
def test_unreadable_or_non_json_input_fails(raw: bytes) -> None:
    with pytest.raises(DomainError) as error:
        parse_document(raw)
    assert error.value.code == "invalid_document"


def test_unknown_json_values_and_deliberately_empty_values_survive() -> None:
    document = {"extra": {"list": [None, False, 1, 1.5]}, "description": "", "x_status": "?"}
    assert parse_document(serialize_document(document)) == document


def test_serialization_and_utf8_bytes_are_exact() -> None:
    assert serialize_document({"z": "雪", "a": '"\n'}) == '{"a":"\\"\\n","z":"雪"}\n'.encode()


def test_byte_budget_includes_newline_and_utf8() -> None:
    overhead = len(serialize_document({"x": ""}))
    accepted = {"x": "a" * (DOCUMENT_LIMIT_BYTES - overhead)}
    assert len(serialize_document(accepted)) == DOCUMENT_LIMIT_BYTES
    assert parse_document(serialize_document(accepted)) == accepted
    with pytest.raises(DomainError) as error:
        serialize_document({"x": accepted["x"] + "a"})
    assert error.value.code == "document_too_large"
    with pytest.raises(DomainError) as error:
        parse_document(b" " * (DOCUMENT_LIMIT_BYTES + 1))
    assert error.value.code == "document_too_large"


def test_nesting_budget_is_checked_for_memory_and_file_inputs() -> None:
    value = 1
    for _ in range(MAX_JSON_DEPTH):
        value = [value]
    with pytest.raises(DomainError) as error:
        validate_document({"extra": value})
    assert error.value.code == "invalid_document"
    with pytest.raises(DomainError):
        parse_document(b'{"x":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}")


def test_aliases_normalize_without_mutation_and_only_by_explicit_mapping() -> None:
    aliases = {"DISPLAY_status": "canonical_status"}
    original = {"DISPLAY_status": "Met", "unknown": {"x": [1]}, "display_status": "?"}
    result = normalize_document(original, aliases)
    assert result == {"canonical_status": "Met", "unknown": {"x": [1]}, "display_status": "?"}
    result["unknown"]["x"].append(2)
    assert original["unknown"]["x"] == [1]
    assert original["DISPLAY_status"] == "Met"


def test_equal_aliases_collapse_but_conflicts_fail_and_patch_normalizes_separately() -> None:
    aliases = {"DISPLAY_status": "canonical_status"}
    assert normalize_document({"DISPLAY_status": "Met", "canonical_status": "Met"}, aliases) == {
        "canonical_status": "Met"
    }
    with pytest.raises(DomainError) as error:
        normalize_document({"DISPLAY_status": "Met", "canonical_status": "Unmet"}, aliases)
    assert error.value.details == {"field": "canonical_status"}
    assert normalize_document({"DISPLAY_status": None}, aliases) == {"canonical_status": None}
    assert normalize_document({"canonical_status": "Met"}, aliases) != normalize_document(
        {"DISPLAY_status": "Unmet"}, aliases
    )


def test_type_distinct_alias_values_do_not_compare_as_equal() -> None:
    with pytest.raises(DomainError):
        normalize_document({"a": True, "canonical": 1}, {"a": "canonical"})


def test_input_objects_with_non_string_keys_are_rejected() -> None:
    with pytest.raises(DomainError):
        validate_document({1: "value"})


def test_unserializable_integer_is_reported_as_invalid_document() -> None:
    previous_limit = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(640)
        with pytest.raises(DomainError) as error:
            serialize_document({"value": 10**640})
        assert error.value.code == "invalid_document"
        assert isinstance(error.value.__cause__, ValueError)
    finally:
        sys.set_int_max_str_digits(previous_limit)
