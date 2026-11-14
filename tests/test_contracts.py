"""Frozen examples and schemas define the intended surface without advertising it."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import MISSING, ValidationError

from best_practices_mcp.contracts import (
    INPUT_MODELS,
    input_schema,
    output_schema,
    validate_input,
    validate_output,
)
from best_practices_mcp.models import ErrorResult

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
EXAMPLES = json.loads((FIXTURES / "examples.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("tool", INPUT_MODELS)
def test_schemas_and_examples(tool: str) -> None:
    snapshot = json.loads((FIXTURES / "schemas.json").read_text(encoding="utf-8"))[tool]
    assert input_schema(tool) == snapshot["input"]
    assert output_schema(tool) == snapshot["output"]
    assert len(snapshot["output"]["anyOf"]) == 2
    for schema in snapshot.values():
        Draft202012Validator.check_schema(schema)
    Draft202012Validator(snapshot["input"]).validate(EXAMPLES[tool]["input"])
    validate_input(tool, EXAMPLES[tool]["input"])
    for variant in ("success", "error"):
        sample = EXAMPLES[tool][variant]
        Draft202012Validator(snapshot["output"]).validate(sample)
        result = validate_output(tool, sample)
        assert result.model_dump(mode="json") == sample
        assert isinstance(result, ErrorResult) == (variant == "error")


@pytest.mark.parametrize(
    "tool",
    [
        "read_draft",
        "get_project_progress",
        "get_project_badge_status",
        "get_project_badge_svg",
        "update_draft",
        "validate_draft",
        "prepare_update_url",
        "prepare_update_script",
    ],
)
@pytest.mark.parametrize("project_id", [True, False, 0, -1, 1.0, "123", None])
def test_project_id_is_strict_positive_integer(tool: str, project_id: object) -> None:
    arguments = EXAMPLES[tool]["input"] | {"project_id": project_id}
    with pytest.raises(ValidationError):
        validate_input(tool, arguments)


@pytest.mark.parametrize("tool", INPUT_MODELS)
def test_extra_arguments_are_rejected(tool: str) -> None:
    with pytest.raises(ValidationError):
        validate_input(tool, EXAMPLES[tool]["input"] | {"unexpected": True})


@pytest.mark.parametrize("tool", ["validate_draft", "prepare_update_url", "prepare_update_script"])
def test_omitted_draft_is_not_empty_or_null(tool: str) -> None:
    base = {"project_id": 123, "level": "passing"}
    absent = validate_input(tool, base)
    assert absent.draft is MISSING
    assert "draft" not in absent.model_dump(mode="json")
    assert validate_input(tool, base | {"draft": {}}).draft == {}
    with pytest.raises(ValidationError):
        validate_input(tool, base | {"draft": None})
    with pytest.raises(SchemaValidationError):
        Draft202012Validator(input_schema(tool)).validate(base | {"draft": None})


@pytest.mark.parametrize("tool", ["get_criteria", "get_project_progress"])
def test_filter_requires_level_and_distinct_ids(tool: str) -> None:
    base = {"project_id": 123} if tool == "get_project_progress" else {}
    for extra in [
        {"criterion_ids": []},
        {"level": None},
        {"level": "passing", "criterion_ids": None},
        {"level": "passing", "criterion_ids": ["x", "x"]},
    ]:
        with pytest.raises(ValidationError):
            validate_input(tool, base | extra)
    result = validate_input(tool, base | {"level": "passing", "criterion_ids": []})
    assert result.criterion_ids == []


@pytest.mark.parametrize(
    "tool,field",
    [
        ("build_draft", "changes"),
        ("update_draft", "changes"),
        ("prepare_update_url", "override_fields"),
        ("find_project", "page"),
    ],
)
def test_optional_fields_never_treat_null_as_omission(tool: str, field: str) -> None:
    with pytest.raises(ValidationError):
        validate_input(tool, EXAMPLES[tool]["input"] | {field: None})


def test_changes_are_required_for_update_and_default_to_empty_for_build() -> None:
    with pytest.raises(ValidationError):
        validate_input("update_draft", {"project_id": 123})
    assert validate_input("build_draft", {"draft": {}}).changes == {}
    assert validate_input("update_draft", {"project_id": 123, "changes": {"extra": None}})


def test_results_reject_unknown_properties_and_missing_required_values() -> None:
    sample = EXAMPLES["get_criteria"]["success"]
    with pytest.raises(ValidationError):
        validate_output("get_criteria", sample | {"extra": True})
    with pytest.raises(ValidationError):
        validate_output("get_criteria", {k: v for k, v in sample.items() if k != "level"})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), b"bytes", "\ud800"])
def test_document_inputs_reject_non_json_values(value: object) -> None:
    with pytest.raises(ValidationError):
        validate_input("build_draft", {"draft": {"extra": value}})


def test_boolean_is_not_a_schema_version() -> None:
    with pytest.raises(ValidationError):
        validate_output(
            "get_criteria", EXAMPLES["get_criteria"]["success"] | {"schema_version": True}
        )


def test_filter_dependency_is_in_the_published_schema() -> None:
    with pytest.raises(SchemaValidationError):
        Draft202012Validator(input_schema("get_criteria")).validate({"criterion_ids": []})


def test_badge_status_default_and_svg_explicit_family() -> None:
    assert (
        validate_input("get_project_badge_status", {"project_id": 123}).family == "best_practices"
    )
    for family in (None, "passing", "baseline-2", "", 1):
        for tool in ("get_project_badge_status", "get_project_badge_svg"):
            with pytest.raises(ValidationError):
                validate_input(tool, {"project_id": 123, "family": family})
    with pytest.raises(ValidationError):
        validate_input("get_project_badge_svg", {"project_id": 123})
    with pytest.raises(SchemaValidationError):
        Draft202012Validator(input_schema("get_project_badge_svg")).validate({"project_id": 123})
