"""Fuzz bounded document decoding and canonical round trips; no file or network I/O."""

import sys

import atheris

with atheris.instrument_imports():
    from best_practices_mcp.documents import parse_document, serialize_document
    from best_practices_mcp.errors import DomainError


@atheris.instrument_func
def test_one_input(data: bytes) -> None:
    try:
        document = parse_document(data)
    except DomainError as error:
        assert error.code in {"invalid_document", "document_too_large"}
        return

    # Once accepted, serialization and reparsing must succeed, not be swallowed.
    canonical = serialize_document(document)
    assert serialize_document(parse_document(canonical)) == canonical
    assert serialize_document(dict(reversed(document.items()))) == canonical


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
