"""Portable JSON-kind declarations preserve arbitrary JSON without weakening runtime checks."""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import TypeAdapter, ValidationError

from best_practices_mcp.contracts import (
    INPUT_MODELS,
    input_schema,
    output_schema,
    validate_input,
    validate_output,
)
from best_practices_mcp.models import JsonValue

EXAMPLES = json.loads(
    (Path(__file__).parent / "fixtures/contracts/examples.json").read_text(encoding="utf-8")
)
JSON_VALUES = [None, True, False, 42, -3.25, "雪", [], {}, {"mixed": [None, False, 7, {"x": []}]}]


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_json_schema_accepts_every_json_kind_and_rejects_non_json(mode):
    adapter = TypeAdapter(JsonValue)
    schema = adapter.json_schema(mode=mode)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for value in JSON_VALUES:
        validator.validate(value)
        assert adapter.dump_json(adapter.validate_python(value)).decode() == json.dumps(
            value, ensure_ascii=False, separators=(",", ":")
        )
    # An empty schema incorrectly accepts these Python instances as well as JSON.
    for value in (object(), b"bytes", (1, 2), {1, 2}):
        with pytest.raises(SchemaValidationError):
            validator.validate(value)
        with pytest.raises(ValidationError):
            adapter.validate_python(value)


@pytest.mark.parametrize("tool", INPUT_MODELS)
def test_each_output_schema_preserves_arbitrary_error_details(tool):
    payload = copy.deepcopy(EXAMPLES[tool]["error"])
    payload["error"]["details"] = {"values": JSON_VALUES}
    Draft202012Validator(output_schema(tool)).validate(payload)
    assert validate_output(tool, payload).model_dump(mode="json") == payload


@pytest.mark.parametrize(
    "tool, field",
    [
        ("build_draft", "draft"),
        ("build_draft", "changes"),
        ("update_draft", "changes"),
        ("validate_draft", "draft"),
        ("prepare_update_url", "draft"),
    ],
)
def test_document_input_schemas_preserve_nested_unfamiliar_json(tool, field):
    arguments = copy.deepcopy(EXAMPLES[tool]["input"])
    arguments[field] = {"unfamiliar": JSON_VALUES}
    Draft202012Validator(input_schema(tool)).validate(arguments)
    assert validate_input(tool, arguments).model_dump(mode="json")[field] == arguments[field]


@pytest.mark.parametrize("value", JSON_VALUES)
def test_progress_preserves_unexpected_saved_values(value):
    payload = copy.deepcopy(EXAMPLES["get_project_answers"]["success"])
    payload["answers"] = {"description_good_status": value}
    Draft202012Validator(output_schema("get_project_answers")).validate(payload)
    assert validate_output("get_project_answers", payload).model_dump(mode="json") == payload


@pytest.mark.parametrize("value", [float("nan"), float("inf"), b"bytes", (1,), {1: "bad key"}])
def test_runtime_document_constraints_remain_stricter_than_wire_json_types(value):
    with pytest.raises(ValidationError):
        validate_input("build_draft", {"draft": {"unfamiliar": value}})
