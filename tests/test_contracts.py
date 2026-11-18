"""Frozen examples and schemas define the intended surface without advertising it."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import MISSING, ValidationError

from best_practices_mcp.contracts import (
    INPUT_MODELS,
    argument_issues,
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
        "get_project_status",
        "get_project_answers",
        "get_project_badge_svg",
        "update_draft",
        "validate_draft",
        "prepare_update_url",
    ],
)
@pytest.mark.parametrize("project_id", [True, False, 0, -1, 1.5, "12a", "-3", " 3", "", None])
def test_project_id_must_identify_a_positive_integer(tool: str, project_id: object) -> None:
    arguments = EXAMPLES[tool]["input"] | {"project_id": project_id}
    with pytest.raises(ValidationError):
        validate_input(tool, arguments)


@pytest.mark.parametrize("project_id", [123, 123.0, "123", "0123"])
def test_integer_valued_identifiers_are_accepted(project_id: object) -> None:
    assert validate_input("read_draft", {"project_id": project_id}).project_id == 123
    found = validate_input("find_project", {"query": "example", "page": project_id})
    assert found.page == 123 and type(found.page) is int
    # The published schema keeps the canonical integer form.
    assert input_schema("read_draft")["properties"]["project_id"]["type"] == "integer"


@pytest.mark.parametrize("tool", INPUT_MODELS)
@pytest.mark.parametrize("value", [True, None])
def test_extra_arguments_are_rejected(tool: str, value: object) -> None:
    with pytest.raises(ValidationError) as error:
        validate_input(tool, EXAMPLES[tool]["input"] | {"unexpected": value})
    assert argument_issues(tool, error.value) == [
        {"field": "unexpected", "problem": "is not an argument of this tool"}
    ]


@pytest.mark.parametrize("tool", ["validate_draft", "prepare_update_url"])
def test_omitted_draft_is_not_empty_or_null(tool: str) -> None:
    base = {"project_id": 123, "section": "passing"}
    absent = validate_input(tool, base)
    assert absent.draft is MISSING
    assert "draft" not in absent.model_dump(mode="json")
    assert validate_input(tool, base | {"draft": {}}).draft == {}
    with pytest.raises(ValidationError):
        validate_input(tool, base | {"draft": None})
    with pytest.raises(SchemaValidationError):
        Draft202012Validator(input_schema(tool)).validate(base | {"draft": None})


@pytest.mark.parametrize("tool", ["get_criteria", "get_project_answers"])
def test_filter_requires_level_and_distinct_ids(tool: str) -> None:
    base: dict[str, Any] = {"project_id": 123} if tool == "get_project_answers" else {}
    rejected: list[dict[str, Any]] = [
        {"criterion_ids": []},
        {"level": None, "criterion_ids": []},
        {"level": "passing", "criterion_ids": ["x", "x"]},
    ]
    for extra in rejected:
        with pytest.raises(ValidationError):
            validate_input(tool, base | extra)
    result = validate_input(tool, base | {"level": "passing", "criterion_ids": []})
    assert result.criterion_ids == []
    unfiltered = validate_input(tool, base | {"level": "passing", "criterion_ids": None})
    assert unfiltered.criterion_ids is MISSING


def test_level_is_optional_for_criteria_and_required_for_answers() -> None:
    assert validate_input("get_criteria", {"level": None}).level is MISSING
    for arguments in ({"project_id": 123}, {"project_id": 123, "level": None}):
        assert issues("get_project_answers", arguments) == [
            {"field": "level", "problem": "is required"}
        ]
    assert input_schema("get_project_answers")["required"] == ["project_id", "level"]
    assert list(input_schema("get_project_status")["properties"]) == ["project_id"]


def test_criteria_selection_rules() -> None:
    for arguments in [
        {"category": "Security"},
        {"detail": "full"},
        {"level": "passing", "category": "Security", "criterion_ids": ["x"]},
        {"level": "passing", "detail": "summary"},
        {"level": "passing", "category": 3},
    ]:
        with pytest.raises(ValidationError):
            validate_input("get_criteria", arguments)
    chosen = validate_input(
        "get_criteria", {"level": "passing", "category": "Security", "detail": "full"}
    )
    assert chosen.model_dump() == {"level": "passing", "category": "Security", "detail": "full"}
    with pytest.raises(SchemaValidationError):
        Draft202012Validator(input_schema("get_criteria")).validate({"detail": "index"})


def test_answer_filter_rules() -> None:
    base: dict[str, Any] = {"project_id": 123, "level": "passing"}
    rejected: list[dict[str, Any]] = [
        {"statuses": ["met"]},
        {"statuses": ["absent"]},
        {"statuses": ["Met", "Met"]},
        {"statuses": "Met"},
        {"include_justifications": "false"},
    ]
    for extra in rejected:
        with pytest.raises(ValidationError):
            validate_input("get_project_answers", base | extra)
    chosen = validate_input(
        "get_project_answers",
        base | {"statuses": ["?", "Unmet"], "include_justifications": False},
    )
    assert chosen.statuses == ["?", "Unmet"] and chosen.include_justifications is False
    assert validate_input("get_project_answers", base).include_justifications is True


@pytest.mark.parametrize(
    "tool,field",
    [
        ("build_draft", "changes"),
        ("prepare_update_url", "overrides"),
        ("find_project", "page"),
        ("get_project_answers", "criterion_ids"),
        ("get_project_answers", "statuses"),
    ],
)
def test_null_optional_arguments_are_omitted(tool: str, field: str) -> None:
    omitted = {key: value for key, value in EXAMPLES[tool]["input"].items() if key != field}
    assert validate_input(tool, omitted | {field: None}) == validate_input(tool, omitted)
    # The published schema keeps the canonical form, which has no null.
    with pytest.raises(SchemaValidationError):
        Draft202012Validator(input_schema(tool)).validate(omitted | {field: None})


@pytest.mark.parametrize(
    "tool,field",
    [
        ("update_draft", "changes"),
        ("build_draft", "draft"),
        ("find_project", "query"),
        ("validate_draft", "section"),
        ("get_project_badge_svg", "family"),
    ],
)
def test_null_required_arguments_are_missing(tool: str, field: str) -> None:
    with pytest.raises(ValidationError) as error:
        validate_input(tool, EXAMPLES[tool]["input"] | {field: None})
    assert argument_issues(tool, error.value) == [{"field": field, "problem": "is required"}]


def issues(tool: str, arguments: dict) -> list[dict]:
    with pytest.raises(ValidationError) as error:
        validate_input(tool, arguments)
    return argument_issues(tool, error.value)


def test_argument_issues_name_each_argument_and_its_allowed_values() -> None:
    assert issues("get_criteria", {"level": "bronze", "detail": "summary", "extra": 1}) == [
        {"field": "detail", "problem": "is not an allowed value", "allowed": ["index", "full"]},
        {"field": "extra", "problem": "is not an argument of this tool"},
        {
            "field": "level",
            "problem": "is not an allowed value",
            "allowed": ["passing", "silver", "gold", "baseline-1", "baseline-2", "baseline-3"],
        },
    ]
    assert issues("get_criteria", {"criterion_ids": ["x"]}) == [
        {"field": "criterion_ids", "problem": "requires level"}
    ]
    assert issues("get_criteria", {"level": "gold", "category": "x", "criterion_ids": []}) == [
        {"field": "category", "problem": "cannot be combined with criterion_ids"}
    ]
    assert issues(
        "get_project_answers",
        {"project_id": True, "level": "passing", "statuses": ["Met", "met"], "criterion_ids": [1]},
    ) == [
        {"field": "criterion_ids", "problem": "has an item that must be a string"},
        {"field": "project_id", "problem": "must be an integer"},
        {
            "field": "statuses",
            "problem": "has an item that is not an allowed value",
            "allowed": ["Met", "Unmet", "N/A", "?"],
        },
    ]
    assert issues("find_project", {"query": 3, "page": 0}) == [
        {"field": "page", "problem": "must be greater than zero"},
        {"field": "query", "problem": "must be a string"},
    ]
    wrong_type = {"project_id": 1, "level": "gold", "include_justifications": 1}
    assert issues("get_project_answers", wrong_type) == [
        {"field": "include_justifications", "problem": "must be true or false"}
    ]


def test_argument_issues_explain_documents_and_nested_shapes() -> None:
    base = {"project_id": 123, "section": "passing"}
    assert issues("validate_draft", base | {"draft": None}) == [
        {
            "field": "draft",
            "problem": (
                "must not be null; omit it to use the stored draft, or pass {} for an empty one"
            ),
        }
    ]
    assert issues("build_draft", {"draft": [], "changes": {"x": float("nan")}}) == [
        {"field": "changes", "problem": "Non-finite numbers are not JSON values."},
        {"field": "draft", "problem": "A draft or patch must be a JSON object."},
    ]
    [nested] = issues("prepare_update_url", base | {"overrides": {"mode": "fields"}})
    assert nested["field"] == "overrides" and nested["problem"] == "is invalid"
    assert (
        nested["expected"]
        == INPUT_MODELS["prepare_update_url"].model_fields["overrides"].description
    )
    assert '{"mode":"fields","fields":[...]}' in nested["expected"]
    assert issues("build_draft", {"draft": {}, "x" * 200: 1}) == [
        {"field": "x" * 64, "problem": "is not an argument of this tool"}
    ]
    assert issues("read_draft", ["project_id", 123]) == [
        {"field": "arguments", "problem": "is invalid"}
    ]


def test_argument_issues_never_repeat_supplied_values() -> None:
    secret = "do-not-repeat-this-value"
    arguments = {
        "project_id": secret,
        "section": secret,
        "draft": secret,
        "overrides": {"mode": secret, "fields": [secret]},
    }
    assert secret not in json.dumps(issues("prepare_update_url", arguments))


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


def test_badge_svg_requires_an_explicit_family() -> None:
    for family in ("passing", "baseline-2", "", 1):
        with pytest.raises(ValidationError):
            validate_input("get_project_badge_svg", {"project_id": 123, "family": family})
    with pytest.raises(ValidationError):
        validate_input("get_project_badge_svg", {"project_id": 123})
    with pytest.raises(SchemaValidationError):
        Draft202012Validator(input_schema("get_project_badge_svg")).validate({"project_id": 123})


@pytest.mark.parametrize("tool", ["validate_draft", "prepare_update_url"])
def test_section_selection_is_explicit_and_old_level_is_rejected(tool):
    base = {"project_id": 123, "draft": {}}
    for extra in ({}, {"level": "passing"}, {"section": None}, {"section": "choose"}):
        with pytest.raises(ValidationError):
            validate_input(tool, base | extra)
    assert validate_input(tool, base | {"section": "choose_section"}).section == "choose_section"
    for version in (1, True):
        with pytest.raises(ValidationError):
            validate_output(tool, EXAMPLES[tool]["success"] | {"schema_version": version})


@pytest.mark.parametrize(
    "overrides",
    [
        "*",
        {},
        {"mode": "fields", "fields": []},
        {"mode": "all", "fields": ["name"]},
        {"mode": "none", "fields": []},
    ],
)
def test_override_intent_rejects_ambiguous_or_contradictory_shapes(overrides):
    arguments = EXAMPLES["prepare_update_url"]["input"] | {"overrides": overrides}
    with pytest.raises(ValidationError):
        validate_input("prepare_update_url", arguments)
    with pytest.raises(SchemaValidationError):
        Draft202012Validator(input_schema("prepare_update_url")).validate(arguments)
