"""Bounded JSON decoding and alias normalization; no file or patch operations."""

import json
import math
from copy import deepcopy
from typing import Any

from best_practices_mcp.errors import DomainError

DOCUMENT_LIMIT_BYTES = 1_048_576
RESPONSE_LIMIT_BYTES = 16_777_216
UPSTREAM_LIMIT_BYTES = 8_388_608
MAX_JSON_DEPTH = 64


def _invalid(message: str) -> DomainError:
    return DomainError("invalid_document", message)


def _valid_string(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _invalid("JSON strings must contain valid Unicode scalar values.") from exc


def _check_value(value: Any, depth: int) -> None:
    if depth > MAX_JSON_DEPTH:
        raise _invalid(f"JSON nesting exceeds {MAX_JSON_DEPTH} levels.")
    if type(value) is str:
        _valid_string(value)
    elif type(value) is dict:
        _check_object(value, depth)
    elif type(value) is list:
        for child in value:
            _check_value(child, depth + 1)
    elif type(value) is float:
        if not math.isfinite(value):
            raise _invalid("Non-finite numbers are not JSON values.")
    elif value is not None and type(value) not in (bool, int):
        raise _invalid("Document values must use JSON types.")


def _check_object(value: dict[str, Any], depth: int) -> None:
    for key, child in value.items():
        if type(key) is not str:
            raise _invalid("Document keys must be strings.")
        _valid_string(key)
        _check_value(child, depth + 1)


def validate_document(value: Any) -> dict[str, Any]:
    """Check JSON shape/resource bounds without judging recognized answer fields."""
    if type(value) is not dict:
        raise _invalid("A draft or patch must be a JSON object.")
    _check_value(value, 1)
    _encode_document(value)
    return value


def _encode_document(document: dict[str, Any]) -> bytes:
    try:
        encoded = (
            json.dumps(
                document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            + "\n"
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise _invalid("Document cannot be serialized as UTF-8 JSON.") from exc
    if len(encoded) > DOCUMENT_LIMIT_BYTES:
        raise DomainError(
            "document_too_large",
            "Document exceeds the server's UTF-8 byte budget.",
            details={"limit_bytes": DOCUMENT_LIMIT_BYTES},
            recovery="Reduce the document or patch size and try again.",
        )
    return encoded


def serialize_document(document: dict[str, Any]) -> bytes:
    """Canonical bytes used for storage and byte-count accounting."""
    validate_document(document)
    return _encode_document(document)


def _object_from_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid("Duplicate JSON object keys are not supported.")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise _invalid("Non-finite numbers are not JSON values.")


def parse_document(raw: bytes) -> dict[str, Any]:
    """Decode bounded UTF-8 bytes, rejecting duplicate keys and invalid JSON."""
    if len(raw) > DOCUMENT_LIMIT_BYTES:
        raise DomainError(
            "document_too_large",
            "Input file exceeds the server byte budget.",
            details={"limit_bytes": DOCUMENT_LIMIT_BYTES},
        )
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_from_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise _invalid("Input is not a readable UTF-8 JSON document.") from exc
    return validate_document(value)


def normalize_document(document: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    """Normalize only explicit field aliases; preserve all unrelated JSON values.

    Base documents and patches must be normalized separately before a later patch
    operation. Equal aliases collapse; conflicts fail without changing the caller.
    """
    validate_document(document)
    normalized: dict[str, Any] = {}
    for field, value in document.items():
        canonical = aliases.get(field, field)
        if canonical in normalized and not _same_json(normalized[canonical], value):
            raise DomainError(
                "invalid_document", "Conflicting alias values.", details={"field": canonical}
            )
        normalized[canonical] = deepcopy(value)
    validate_document(normalized)
    return normalized


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _same_json(left: Any, right: Any) -> bool:
    return _canonical_json(left) == _canonical_json(right)
