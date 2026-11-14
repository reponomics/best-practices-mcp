"""Strict domain contracts for the bounded MCP tool surface.

Models do not register tools or implement their future application behavior.
Optional inputs use the public Pydantic omission sentinel: null is not omission.
"""

from typing import Annotated, Literal, Self

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

from best_practices_mcp.documents import validate_document
from best_practices_mcp.errors import DomainError

Level = Literal["passing", "silver", "gold", "baseline-1", "baseline-2", "baseline-3"]
BadgeFamily = Literal["best_practices", "baseline"]
LEVELS: tuple[Level, ...] = ("passing", "silver", "gold", "baseline-1", "baseline-2", "baseline-3")
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]


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


class CriteriaInput(Model):
    model_config = ConfigDict(json_schema_extra={"dependentRequired": {"criterion_ids": ["level"]}})

    level: Level | MISSING = MISSING
    criterion_ids: (
        Annotated[list[str], Field(json_schema_extra={"uniqueItems": True})] | MISSING
    ) = MISSING

    @field_validator("criterion_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("criterion_ids must be distinct")
        return value

    @model_validator(mode="after")
    def filter_requires_level(self) -> Self:
        if self.criterion_ids is not MISSING and self.level is MISSING:
            raise ValueError("criterion_ids requires level")
        return self


class FindProjectInput(Model):
    query: str
    page: PositiveInt = 1


class ProjectInput(Model):
    project_id: PositiveInt


class ProgressInput(CriteriaInput, ProjectInput):
    pass


class BadgeStatusInput(ProjectInput):
    family: BadgeFamily = Field(
        default="best_practices",
        description="Badge family to observe; returned as effective family.",
    )


class BadgeSVGInput(ProjectInput):
    family: BadgeFamily = Field(
        description="Badge family whose SVG and README snippet to retrieve."
    )


class BuildDraftInput(Model):
    draft: Draft
    changes: Draft = Field(default_factory=dict)


class UpdateDraftInput(ProjectInput):
    changes: Draft


class DraftSourceInput(ProjectInput):
    level: Level
    draft: Draft | MISSING = MISSING


class PrepareURLInput(DraftSourceInput):
    override_fields: list[str] = Field(default_factory=list)


def _schema_version(value: object) -> object:
    if type(value) is not int:
        raise ValueError("schema versions must be integers")
    return value


SchemaVersion = Annotated[Literal[1], BeforeValidator(_schema_version)]


class Result(Model):
    schema_version: SchemaVersion


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
    "invalid_document",
    "invalid_field",
    "invalid_level",
    "invalid_criterion",
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
    source_url: str


class GetCriteriaResult(Result):
    level: Level | None
    levels: list[Level]
    criteria: list[Criterion]
    catalog: CatalogRef


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


class SavedCriterion(Model):
    criterion_id: str
    status_present: bool
    status: JsonValue
    justification_present: bool
    justification: JsonValue


class GetProjectProgressResult(Result):
    project: Project
    level: Level | None
    summaries: list[Summary]
    answers: Draft
    criteria: list[SavedCriterion]
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
    criterion_id: str | None
    field: str
    code: FindingCode
    requirement: str
    message: str


class Skipped(Model):
    criterion_id: str
    reason: Literal["status_absent", "status_unknown", "status_invalid", "other_level"]
    checks: list[str]


class ValidateDraftResult(Result):
    project_id: PositiveInt
    level: Level
    draft_source: DraftSource
    identity: Identity
    catalog: CatalogRef
    findings: list[Finding]
    checked_criteria: list[str]
    skipped_criteria: list[Skipped]


class TransferField(Model):
    field: str
    disposition: Literal["encoded", "outside_level", "unsupported", "invalid", "omitted"]
    reason: str
    override: bool


Outcome = Literal[
    "complete",
    "partial",
    "no_transferable_changes",
    "no_supplied_transferable_answers",
]


class ArtifactResult(Result):
    project_id: PositiveInt
    level: Level
    catalog: CatalogRef
    draft_source: DraftSource
    observation: Observation
    identity: Identity
    outcome: Outcome
    no_artifact_reason: str | None
    transfer: list[TransferField]


class URLArtifact(Model):
    url: str
    encoded_size_bytes: NonNegativeInt


class ScriptArtifact(Model):
    javascript: str
    suggested_filename: str
    instructions: str
    encoded_size_bytes: NonNegativeInt


class PrepareURLResult(ArtifactResult):
    requested_overrides: list[str]
    effective_overrides: list[str]
    artifact: URLArtifact | None


class PrepareScriptResult(ArtifactResult):
    artifact: ScriptArtifact | None
