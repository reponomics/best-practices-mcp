"""Strict domain contracts for the bounded MCP tool surface.

Models do not register tools or implement their application behavior. Results are
strict. Tool arguments accept two documented variations of their published schema:
a null optional argument counts as omitted, and identifiers may arrive as
integer-valued numbers or decimal strings.
"""

import re
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    MISSING,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    field_validator,
    model_validator,
)
from pydantic import (
    JsonValue as PydanticJsonValue,
)
from pydantic_core import PydanticCustomError

from best_practices_mcp.documents import validate_document
from best_practices_mcp.errors import DomainError

Level = Literal["passing", "silver", "gold", "baseline-1", "baseline-2", "baseline-3"]
Section = Literal[
    "passing", "silver", "gold", "baseline-1", "baseline-2", "baseline-3", "choose_section"
]
BadgeFamily = Literal["best_practices", "baseline"]
Detail = Literal["index", "full"]
StatusFilter = Literal["Met", "Unmet", "N/A", "?", "absent"]
LEVELS: tuple[Level, ...] = ("passing", "silver", "gold", "baseline-1", "baseline-2", "baseline-3")
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]


def _integer_argument(value: object) -> object:
    """Convert 123.0 and "123" to 123; Booleans and other values stay invalid."""
    if type(value) is float and value.is_integer():
        return int(value)
    if type(value) is str and re.fullmatch(r"[0-9]{1,18}", value):
        return int(value)
    return value


PositiveIntArgument = Annotated[PositiveInt, BeforeValidator(_integer_argument)]


def argument_error(field: str, problem: str) -> PydanticCustomError:
    """Name the argument responsible for a rule that spans several arguments."""
    return PydanticCustomError(
        "argument", "{field} {problem}", {"field": field, "problem": problem}
    )


def _json_document(value: object) -> object:
    try:
        return validate_document(value)
    except DomainError as exc:
        raise ValueError(exc.message) from exc


# Pydantic's JsonValue validates recursively but publishes an empty schema. Enumerate
# the JSON kinds without narrowing preserved values or adding recursive client schemas.
# Collections intentionally admit arbitrary JSON children, as the contract requires.
JsonValue = Annotated[
    PydanticJsonValue,
    WithJsonSchema(
        {
            "anyOf": [
                {"type": "null"},
                {"type": "boolean"},
                {"type": "number"},
                {"type": "string"},
                {"type": "array"},
                {"type": "object", "additionalProperties": True},
            ]
        }
    ),
]

Draft = Annotated[dict[str, JsonValue], BeforeValidator(_json_document)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Input(Model):
    """Tool arguments; a null optional argument is treated as omitted."""

    null_is_invalid: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def omit_null_arguments(cls, data: object) -> object:
        if type(data) is not dict:
            return data
        return {
            key: value
            for key, value in data.items()
            if value is not None or key in cls.null_is_invalid
        }


def _distinct(value: list) -> list:
    if len(value) != len(set(value)):
        raise ValueError("items must be distinct")
    return value


class CriterionScope(Input):
    level: Level | MISSING = Field(
        default=MISSING, description="Badge level whose criteria to select."
    )
    criterion_ids: (
        Annotated[list[str], Field(json_schema_extra={"uniqueItems": True})] | MISSING
    ) = Field(
        default=MISSING,
        description=(
            "Criterion IDs within level, as listed by get_criteria. Omit to select every "
            "criterion of the level."
        ),
    )

    requires_level: ClassVar[tuple[str, ...]] = ("criterion_ids",)

    @field_validator("criterion_ids")
    @classmethod
    def distinct_ids(cls, value: list[str]) -> list[str]:
        return _distinct(value)

    @model_validator(mode="after")
    def filters_require_level(self) -> Self:
        if self.level is MISSING:
            for field in self.requires_level:
                if field in self.model_fields_set:
                    raise argument_error(field, "requires level")
        return self


class CriteriaInput(CriterionScope):
    model_config = ConfigDict(
        json_schema_extra={
            "dependentRequired": {
                "criterion_ids": ["level"],
                "category": ["level"],
                "detail": ["level"],
            }
        }
    )

    category: str | MISSING = Field(
        default=MISSING,
        description=(
            "Return only one category of the level, such as Security. The level index lists "
            "each level's categories. Cannot be combined with criterion_ids."
        ),
    )
    detail: Detail | MISSING = Field(
        default=MISSING,
        description=(
            "index returns each criterion's ID, category and requirement; full adds the "
            "official text, field names and justification rules. Defaults to full when "
            "criterion_ids is given, otherwise index."
        ),
    )

    requires_level: ClassVar[tuple[str, ...]] = ("criterion_ids", "category", "detail")

    @model_validator(mode="after")
    def one_selection(self) -> Self:
        if self.category is not MISSING and self.criterion_ids is not MISSING:
            raise argument_error("category", "cannot be combined with criterion_ids")
        return self


class FindProjectInput(Input):
    query: str = Field(
        description=(
            "A project ID, the project's exact repository or homepage URL, or search text."
        )
    )
    page: PositiveIntArgument = Field(
        default=1, description="Result page, starting at 1. Use next_page from the last result."
    )


class ProjectInput(Input):
    project_id: PositiveIntArgument = Field(
        description="BadgeApp project ID, as returned by find_project."
    )


class ProgressInput(CriterionScope, ProjectInput):
    model_config = ConfigDict(
        json_schema_extra={"dependentRequired": {"criterion_ids": ["level"], "statuses": ["level"]}}
    )

    statuses: (
        Annotated[list[StatusFilter], Field(json_schema_extra={"uniqueItems": True})] | MISSING
    ) = Field(
        default=MISSING,
        description=(
            "Return only criteria whose saved status is one of these. absent selects "
            "criteria with no saved status."
        ),
    )
    include_justifications: bool = Field(
        default=True, description="Set false to return statuses without justification text."
    )

    requires_level: ClassVar[tuple[str, ...]] = ("criterion_ids", "statuses")

    @field_validator("statuses")
    @classmethod
    def distinct_statuses(cls, value: list[str]) -> list[str]:
        return _distinct(value)


class BadgeStatusInput(ProjectInput):
    family: BadgeFamily = Field(
        default="best_practices",
        description="Badge family to observe; returned as effective family.",
    )


class BadgeSVGInput(ProjectInput):
    family: BadgeFamily = Field(
        description="Badge family whose SVG and README snippet to retrieve."
    )


DRAFT_FORMAT = (
    'A flat JSON object in draft format: "<criterion_id>_status" is "Met", "Unmet", "N/A" '
    'or "?"; "<criterion_id>_justification" is text; name, description, license and '
    "implementation_languages are project metadata."
)
CHANGES = f"Fields to set. {DRAFT_FORMAT} A null value removes the field."


class BuildDraftInput(Input):
    draft: Draft = Field(description="The document to change; {} starts an empty one.")
    changes: Draft = Field(default_factory=dict, description=CHANGES)


class UpdateDraftInput(ProjectInput):
    changes: Draft = Field(description=CHANGES)


class DraftSourceInput(ProjectInput):
    null_is_invalid: ClassVar[frozenset[str]] = frozenset({"draft"})

    section: Section = Field(
        description="Badge level, or choose_section for human selection in BadgeApp."
    )
    draft: Draft | MISSING = Field(
        default=MISSING,
        description=(
            "A complete draft to use instead of the stored one. Omit it to use the draft "
            "saved by update_draft. " + DRAFT_FORMAT
        ),
    )

    @field_validator("draft", mode="before")
    @classmethod
    def explicit_draft(cls, value: object) -> object:
        if value is None:
            raise ValueError(
                "must not be null; omit it to use the stored draft, or pass {} for an empty one"
            )
        return value


class NoOverrides(Model):
    mode: Literal["none"]


class AllOverrides(Model):
    mode: Literal["all"]


class FieldOverrides(Model):
    mode: Literal["fields"]
    fields: list[str] = Field(min_length=1, description="Canonical supplied field names.")


Overrides = NoOverrides | AllOverrides | FieldOverrides


class PrepareURLInput(DraftSourceInput):
    overrides: Overrides = Field(
        default_factory=lambda: NoOverrides(mode="none"),
        description=(
            '{"mode":"none"} proposes values only where BadgeApp has no answer; '
            '{"mode":"all"} also replaces saved answers for every supplied field; '
            '{"mode":"fields","fields":[...]} replaces saved answers only for the named fields.'
        ),
    )


def _schema_version(value: object) -> object:
    if type(value) is not int:
        raise ValueError("schema versions must be integers")
    return value


SchemaVersion = Annotated[Literal[1], BeforeValidator(_schema_version)]


class Result(Model):
    schema_version: SchemaVersion


class ResultV2(Model):
    """Success payloads whose interface changed after the first published version."""

    schema_version: Annotated[Literal[2], BeforeValidator(_schema_version)]


class CatalogRef(Model):
    revision: str
    source_url: str
    generated_at: str
    format_version: SchemaVersion


class Observation(Model):
    project_id: PositiveInt
    source_url: str
    fetched_at: str
    attribution: str | None
    license: str | None


class SearchObservation(Model):
    source_url: str
    fetched_at: str


class Project(Model):
    project_id: PositiveInt
    name: str | None
    repo_url: str | None
    homepage_url: str | None


class DraftSource(Model):
    kind: Literal["explicit", "stored"]
    location: str | None


class StructuralIssue(Model):
    field: str
    code: Literal["unknown_field", "invalid_type", "invalid_status"]
    message: str


class Identity(Model):
    association: Literal["storage_key", "document_provenance", "explicit_target"]
    id_check: Literal["matched", "absent"]
    repo_check: Literal["matched", "absent", "not_checked"]


ErrorCode = Literal[
    "invalid_arguments",
    "invalid_document",
    "invalid_field",
    "invalid_level",
    "invalid_criterion",
    "invalid_category",
    "invalid_query",
    "invalid_override",
    "draft_not_found",
    "draft_read_failed",
    "draft_write_failed",
    "document_too_large",
    "response_too_large",
    "project_not_found",
    "project_mismatch",
    "project_identity_unresolved",
    "upstream_unavailable",
    "upstream_invalid_response",
    "rate_limited",
    "internal_error",
]


class Error(Model):
    code: ErrorCode
    message: str
    details: dict[str, JsonValue]
    recovery: str
    retry_after_seconds: NonNegativeInt | None


class ErrorResult(Result):
    error: Error


class Criterion(Model):
    criterion_id: str
    level: Level
    description: str
    details: str | None
    category: str | None
    requirement: str | None
    status_field: str
    justification_field: str
    aliases: list[str]
    na_allowed: bool = Field(
        description=(
            "Whether N/A is permitted, including when implied by required N/A justification."
        )
    )
    na_justification_required: bool = Field(
        description="Whether N/A requires justification; implies na_allowed."
    )
    met_justification_required: bool = Field(
        description="Whether Met requires justification, including when a URL is required."
    )
    met_url_required: bool = Field(
        description=(
            "Whether Met requires a URL in its justification; implies met_justification_required."
        )
    )


class CriterionSummary(Model):
    criterion_id: str
    category: str | None
    requirement: str | None


class LevelSummary(Model):
    level: Level
    criterion_count: NonNegativeInt
    categories: list[str]


class CriteriaCatalogRef(CatalogRef):
    text_source_url: str = Field(description="Source of the description and details text.")


class GetCriteriaResult(ResultV2):
    level: Level | None
    detail: Detail | None = Field(description="Form of the criteria rows; null without a level.")
    levels: list[LevelSummary] = Field(
        description="Every level when no level is selected, otherwise the selected level."
    )
    criteria: list[Criterion] | list[CriterionSummary]
    catalog: CriteriaCatalogRef


class Candidate(Model):
    project: Project
    match_basis: Literal["id", "repo_url", "homepage_url", "url_query", "text"]


class FindProjectResult(Result):
    query: str
    query_kind: Literal["id", "url", "text"]
    page: PositiveInt
    candidates: list[Candidate]
    next_page: PositiveInt | None
    pagination_complete: bool
    observation: SearchObservation


class Summary(Model):
    level: Level
    upstream_percentage: float | int | None


class SummaryMetadata(Model):
    badge_level: JsonValue | MISSING = MISSING
    tiered_percentage: JsonValue | MISSING = MISSING
    baseline_tiered_percentage: JsonValue | MISSING = MISSING


class GetProjectProgressResult(ResultV2):
    project: Project
    level: Level | None
    summaries: list[Summary]
    answers: Draft = Field(
        description=(
            "Saved fields of the matching criteria, in draft format. A criterion with nothing "
            "saved has no fields here."
        )
    )
    criterion_ids: list[str] = Field(
        description="Criteria that matched the filters, including those with nothing saved."
    )
    level_criterion_count: NonNegativeInt | None = Field(
        description="Number of criteria in the selected level; null without a level."
    )
    observation: Observation
    catalog: CatalogRef
    summary_metadata: SummaryMetadata


class BadgeProject(Model):
    project_id: PositiveInt
    name: str | None


class BadgeObservation(Model):
    source_url: str
    fetched_at: str
    service_attribution: str
    project_entry_attribution: None
    project_entry_license: None


class BadgeProgress(Model):
    field: Literal["tiered_percentage", "badge_percentage"]
    value: float | int | None
    level: Literal["baseline-1"] | None


class GetProjectBadgeStatusResult(Result):
    project: BadgeProject
    family: BadgeFamily
    badge_level: str | None
    badge_state: Literal["earned", "in_progress", "unrecognized", "unknown"]
    progress: BadgeProgress
    updated_at: str | None
    updated_at_status: Literal["valid", "missing", "invalid"]
    observation: BadgeObservation
    caveats: list[str]


class SVGArtifact(Model):
    svg: str
    media_type: Literal["image/svg+xml"]
    suggested_filename: str
    encoded_size_bytes: NonNegativeInt


class GetProjectBadgeSVGResult(Result):
    project_id: PositiveInt
    family: BadgeFamily
    image_url: str
    project_url: str
    markdown: str
    artifact: SVGArtifact
    observation: BadgeObservation
    caveats: list[str]


class BuildDraftResult(Result):
    draft: Draft
    issues: list[StructuralIssue]
    serialized_size_bytes: NonNegativeInt


class ReadDraftResult(BuildDraftResult):
    project_id: PositiveInt
    location: str
    identity: Identity


class UpdateDraftResult(Result):
    project_id: PositiveInt
    applied_patch: Draft
    created: bool
    location: str
    issues: list[StructuralIssue]
    serialized_size_bytes: NonNegativeInt
    identity: Identity


FindingCode = Literal[
    "invalid_type",
    "invalid_status",
    "unknown_field",
    "na_not_allowed",
    "missing_required_justification",
    "missing_required_url",
]


class Finding(Model):
    level: Level | None
    criterion_id: str | None
    field: str
    code: FindingCode
    requirement: str
    message: str


class Skipped(Model):
    level: Level
    criterion_id: str
    reason: Literal["status_absent", "status_unknown", "status_invalid", "other_level"]
    checks: list[str]


class CompatibilityWarning(Model):
    code: Literal["unknown_status_reset_unsupported"]
    fields: list[str]
    message: str
    observed_on: str


class CriterionRef(Model):
    level: Level
    criterion_id: str


class ValidateDraftResult(ResultV2):
    project_id: PositiveInt
    section: Section
    draft_source: DraftSource
    identity: Identity
    catalog: CatalogRef
    findings: list[Finding]
    checked_criteria: list[CriterionRef]
    skipped_criteria: list[Skipped]
    warnings: list[CompatibilityWarning]


class LevelRestriction(Model):
    level: Level
    reason: str


class TransferField(Model):
    field: str
    disposition: Literal["encoded", "outside_level", "unsupported", "invalid", "omitted"]
    reason: str
    override: bool
    applicable_levels: list[Level]
    restrictions: list[LevelRestriction]


Outcome = Literal[
    "complete",
    "partial",
    "no_transferable_changes",
    "no_supplied_transferable_answers",
]


class ArtifactResult(ResultV2):
    project_id: PositiveInt
    section: Section
    catalog: CatalogRef
    draft_source: DraftSource
    observation: Observation
    identity: Identity
    warnings: list[CompatibilityWarning]
    outcome: Outcome
    no_artifact_reason: str | None
    transfer: list[TransferField]


class URLArtifact(Model):
    url: str
    encoded_size_bytes: NonNegativeInt


class PrepareURLResult(ArtifactResult):
    overrides: Overrides
    effective_overrides: list[str]
    artifact: URLArtifact | None
