"""Schema inventory for implemented and planned tools; never tool registration."""

from pydantic import TypeAdapter

from best_practices_mcp import models

INPUT_MODELS: dict[str, type[models.Model]] = {
    "get_criteria": models.CriteriaInput,
    "find_project": models.FindProjectInput,
    "get_project_progress": models.ProgressInput,
    "get_project_badge_status": models.BadgeStatusInput,
    "get_project_badge_svg": models.BadgeSVGInput,
    "build_draft": models.BuildDraftInput,
    "read_draft": models.ProjectInput,
    "update_draft": models.UpdateDraftInput,
    "validate_draft": models.DraftSourceInput,
    "prepare_update_url": models.PrepareURLInput,
    "prepare_update_script": models.DraftSourceInput,
}
OUTPUT_MODELS: dict[str, type[models.Result]] = {
    "get_criteria": models.GetCriteriaResult,
    "find_project": models.FindProjectResult,
    "get_project_progress": models.GetProjectProgressResult,
    "get_project_badge_status": models.GetProjectBadgeStatusResult,
    "get_project_badge_svg": models.GetProjectBadgeSVGResult,
    "build_draft": models.BuildDraftResult,
    "read_draft": models.ReadDraftResult,
    "update_draft": models.UpdateDraftResult,
    "validate_draft": models.ValidateDraftResult,
    "prepare_update_url": models.PrepareURLResult,
    "prepare_update_script": models.PrepareScriptResult,
}


def input_schema(tool: str) -> dict:
    """JSON Schema for strict input shape; no future tool is registered here."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **INPUT_MODELS[tool].model_json_schema(),
    }


def output_adapter(tool: str) -> TypeAdapter:
    """Both success and structured tool errors conform to the published schema."""
    return TypeAdapter(OUTPUT_MODELS[tool] | models.ErrorResult)


def output_schema(tool: str) -> dict:
    # Both union branches are objects. Declare that implied constraint explicitly
    # for the SDK's pre-2026 wire schemas, which require an object at the root.
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **output_adapter(tool).json_schema(mode="serialization"),
        "type": "object",
    }


def validate_input(tool: str, arguments: dict) -> models.Model:
    return INPUT_MODELS[tool].model_validate(arguments)


def validate_output(tool: str, payload: dict) -> models.Result:
    return output_adapter(tool).validate_python(payload)
