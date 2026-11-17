"""Fuzz proposal URLs from valid documents without contacting BadgeApp."""

import sys
from urllib.parse import parse_qs, urlsplit

import atheris

from best_practices_mcp.documents import parse_document, serialize_document
from best_practices_mcp.proposals import prepare_update_url

JUSTIFICATION = "description_good_justification"
OBSERVATION = {
    "project_id": 123,
    "source_url": "https://www.bestpractices.dev/projects/123.json",
    "fetched_at": "2026-11-17T00:00:00Z",
    "attribution": None,
    "license": None,
}


def test_one_input(data: bytes) -> None:
    # Decode every input to usable text so mutations always reach URL generation.
    text = data.decode("utf-8", errors="replace")
    original = {
        "description_good_status": "Met",
        JUSTIFICATION: text,
        "description": text[::-1],
    }
    encoded = serialize_document(original)
    draft = parse_document(encoded)
    result = prepare_update_url(123, "passing", draft, {}, OBSERVATION, [JUSTIFICATION])
    assert result["outcome"] == "complete"
    artifact = result["artifact"]
    parts = urlsplit(artifact["url"])
    assert (parts.scheme, parts.netloc, parts.path, parts.fragment) == (
        "https",
        "www.bestpractices.dev",
        "/en/projects/123/passing/edit",
        "",
    )
    expected = {key: [value] for key, value in original.items()}
    expected["overrides"] = [JUSTIFICATION]
    assert parse_qs(parts.query, keep_blank_values=True, strict_parsing=True) == expected
    assert artifact["encoded_size_bytes"] == len(artifact["url"].encode("utf-8"))
    assert serialize_document(draft) == encoded
    reordered = dict(reversed(draft.items()))
    assert prepare_update_url(123, "passing", reordered, {}, OBSERVATION, [JUSTIFICATION]) == result


if __name__ == "__main__":
    # Include URL helpers already imported by Python/Atheris before this module.
    atheris.instrument_all()
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
