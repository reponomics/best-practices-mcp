"""Schema inventory and argument diagnostics for the tools; never tool registration."""

from typing import Any, Literal, get_args, get_origin

from pydantic import TypeAdapter, ValidationError
from pydantic_core import ErrorDetails

from best_practices_mcp import models

INPUT_MODELS: dict[str, type[models.Model]] = {
    "get_criteria": models.CriteriaInput,
    "find_project": models.FindProjectInput,
    "get_project_status": models.ProjectInput,
    "get_project_answers": models.AnswersInput,
    "get_project_badge_svg": models.BadgeSVGInput,
    "build_draft": models.BuildDraftInput,
    "read_draft": models.ProjectInput,
    "update_draft": models.UpdateDraftInput,
    "validate_draft": models.DraftSourceInput,
    "prepare_update_url": models.PrepareURLInput,
}
OUTPUT_MODELS: dict[str, type[models.Model]] = {
    "get_criteria": models.GetCriteriaResult,
    "find_project": models.FindProjectResult,
    "get_project_status": models.GetProjectStatusResult,
    "get_project_answers": models.GetProjectAnswersResult,
    "get_project_badge_svg": models.GetProjectBadgeSVGResult,
    "build_draft": models.BuildDraftResult,
    "read_draft": models.ReadDraftResult,
    "update_draft": models.UpdateDraftResult,
    "validate_draft": models.ValidateDraftResult,
    "prepare_update_url": models.PrepareURLResult,
}


def input_schema(tool: str) -> dict[str, Any]:
    """JSON Schema for strict input shape; no future tool is registered here."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **INPUT_MODELS[tool].model_json_schema(),
    }


def output_adapter(tool: str) -> TypeAdapter[Any]:
    """Both success and structured tool errors conform to the published schema."""
    # The union is composed at run time, so it has no static type form.
    return TypeAdapter(OUTPUT_MODELS[tool] | models.ErrorResult)  # type: ignore[arg-type]


def output_schema(tool: str) -> dict[str, Any]:
    # Both union branches are objects. Declare that implied constraint explicitly
    # for the SDK's pre-2026 wire schemas, which require an object at the root.
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **output_adapter(tool).json_schema(mode="serialization"),
        "type": "object",
    }


def validate_input(tool: str, arguments: dict[str, Any]) -> models.Model:
    return INPUT_MODELS[tool].model_validate(arguments)


PROBLEMS = {
    "missing": "is required",
    "extra_forbidden": "is not an argument of this tool",
    "literal_error": "is not an allowed value",
    "int_type": "must be an integer",
    "greater_than": "must be greater than zero",
    "string_type": "must be a string",
    "bool_type": "must be true or false",
    "list_type": "must be an array",
    "dict_type": "must be an object",
}
FIELD_NAME_LIMIT = 64


def _allowed_values(annotation: object) -> list[Any]:
    """Collect the literal choices of an argument, including those of array items."""
    if get_origin(annotation) is Literal:
        return list(get_args(annotation))
    return [value for part in get_args(annotation) for value in _allowed_values(part)]


def _issue(model: type[models.Model], error: ErrorDetails) -> dict[str, Any]:
    location, kind = error["loc"], error["type"]
    if kind == "argument":
        return {"field": error["ctx"]["field"], "problem": error["ctx"]["problem"]}
    field = str(location[0])[:FIELD_NAME_LIMIT] if location else "arguments"
    definition = model.model_fields.get(field)
    item = len(location) == 2 and type(location[1]) is int
    if kind == "value_error" and len(location) == 1:
        problem = str(error["ctx"]["error"])
    elif kind in PROBLEMS and (len(location) == 1 or item):
        problem = PROBLEMS[kind]
        if item:
            problem = "has an item that " + problem
    else:
        # Nested shapes produce one error per alternative; restate the expected shape.
        issue: dict[str, Any] = {"field": field, "problem": "is invalid"}
        if definition is not None and definition.description:
            issue["expected"] = definition.description
        return issue
    issue = {"field": field, "problem": problem}
    if kind == "literal_error" and definition is not None:
        issue["allowed"] = _allowed_values(definition.annotation)
    return issue


def argument_issues(tool: str, error: ValidationError) -> list[dict[str, Any]]:
    """Describe rejected arguments by name, one issue each, without repeating their values."""
    issues: dict[str, dict[str, Any]] = {}
    for item in error.errors():
        issue = _issue(INPUT_MODELS[tool], item)
        issues.setdefault(issue["field"], issue)
    return [issues[field] for field in sorted(issues)]


def validate_output(tool: str, payload: dict[str, Any]) -> models.Result:
    result: models.Result = output_adapter(tool).validate_python(payload)
    return result
