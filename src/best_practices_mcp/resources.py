"""MCP resources: criteria and a project's saved answers as Markdown for a person to attach.

Tools return structured data that a model selects and filters. These resources carry the
same catalog and public-record reads as documents addressed by URI, which a host can offer
in a picker:

    criteria://levels                         the six levels and their categories
    criteria://{level}                        one level, criterion text without details
    criteria://{level}/{category}             one category in full (listed for every pair)
    criteria://{level}/{criterion_id}         one criterion in full (template)
    project://{project_id}/{level}            saved answers beside each criterion (template;
                                              listed for projects with a stored draft)
    project://{project_id}/{level}/{category} the same for one category (template)
    guide://repository-file                   how BadgeApp uses a repository's
                                              .bestpractices.json, kept out of the instructions

Claude Code attaches an @-mentioned resource only when it is listed, so the level documents
of projects with a stored draft are added to the list; a project ID cannot be enumerated
otherwise.

Category segments are slugs: "Change Control" is "change-control".

Upstream criterion text is HTML written for the BadgeApp form. Documents convert its
small tag set to Markdown and turn same-page anchors into criterion URIs; the tools
keep returning the text unchanged.
"""

import html
import json
import re
from functools import partial
from importlib.resources import files
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ResourceError
from mcp.types import Resource

from best_practices_mcp.criteria import (
    catalog_levels,
    catalog_reference,
    criterion_definitions,
    level_summary,
)
from best_practices_mcp.drafts import VALID_STATUSES
from best_practices_mcp.errors import DomainError

MARKDOWN = "text/markdown"


def category_slug(category: str) -> str:
    return category.lower().replace(" ", "-")


INLINE_MARKS = {"tt": "`", "em": "*", "i": "*", "strong": "**"}
LIST_BLOCK = re.compile(r"\s*<(ul|ol)>(.*?)</\1>\s*", re.DOTALL)
LINK = re.compile(r'<a\s+href="([^"]*)"\s*>(.*?)</a>', re.DOTALL)


def _list(match: re.Match) -> str:
    items = [" ".join(item.split()) for item in match[2].replace("</li>", "").split("<li>")[1:]]
    marks = [f"{number}." if match[1] == "ol" else "-" for number in range(1, len(items) + 1)]
    return "\n\n" + "\n".join(f"{mark} {item}" for mark, item in zip(marks, items)) + "\n\n"


def _link(level: str, match: re.Match) -> str:
    target, text = match[1], " ".join(match[2].split())
    if target.startswith("#"):
        # An anchor on the BadgeApp form names another criterion of the same level.
        return f"{text} (`criteria://{level}/{target[1:]}`)"
    return f"[{text}]({target})"


def markdown_text(text: str, level: str) -> str:
    """Convert upstream's HTML tags to Markdown without changing the wording."""
    text = LIST_BLOCK.sub(_list, text)
    text = re.sub(r"(\s*<br>\s*)+", "\n\n", text)
    for tag, mark in INLINE_MARKS.items():
        text = re.sub(rf"<{tag}>(.*?)</{tag}>", rf"{mark}\1{mark}", text, flags=re.DOTALL)
    text = LINK.sub(lambda match: _link(level, match), text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text)).strip()


def _level_title(level: str) -> str:
    return level.replace("-", " level ").capitalize()


def _rules(criterion: dict) -> str:
    """State the status rules that the validator applies to this criterion."""
    if not criterion["na_allowed"]:
        not_applicable = "N/A is not allowed."
    elif criterion["na_justification_required"]:
        not_applicable = "N/A is allowed and requires a justification."
    else:
        not_applicable = "N/A is allowed without a justification."
    if criterion["met_url_required"]:
        met = "Met requires a justification that contains a URL."
    elif criterion["met_justification_required"]:
        met = "Met requires a justification."
    else:
        met = "Met does not require a justification."
    return f"{met} {not_applicable}"


def _criterion_section(criterion: dict, *, heading: str, details: bool) -> list[str]:
    level = criterion["level"]
    lines = [
        f"{heading} {criterion['criterion_id']} ({criterion['requirement']})",
        "",
        markdown_text(criterion["description"], level),
    ]
    if details:
        if criterion["details"]:
            lines += ["", markdown_text(criterion["details"], level)]
        lines += [
            "",
            f"Draft fields: `{criterion['status_field']}`, `{criterion['justification_field']}`. "
            + _rules(criterion),
        ]
    return [*lines, ""]


def _source_line() -> str:
    return f"Source: OpenSSF Best Practices criteria at revision {catalog_reference()['revision']}."


def _by_category(criteria: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for criterion in criteria:
        groups.setdefault(criterion["category"], []).append(criterion)
    return dict(sorted(groups.items()))


def levels_document() -> str:
    lines = ["# OpenSSF Best Practices badge levels", "", _source_line(), ""]
    for level in catalog_levels():
        summary = level_summary(level)
        lines += [f"## {level} ({summary['criterion_count']} criteria)", ""]
        lines += [
            f"- {category}: `criteria://{level}/{category_slug(category)}`"
            for category in summary["categories"]
        ]
        lines.append("")
    return "\n".join(lines)


def level_document(level: str) -> str:
    criteria = criterion_definitions(level)
    lines = [
        f"# {_level_title(level)} criteria",
        "",
        f"{len(criteria)} criteria. Details and status rules are in the category resources, "
        f"for example `criteria://{level}/{category_slug(criteria[0]['category'])}`.",
        _source_line(),
        "",
    ]
    for category, members in _by_category(criteria).items():
        lines += [f"## {category}", ""]
        for criterion in members:
            lines += _criterion_section(criterion, heading="###", details=False)
    return "\n".join(lines)


def category_document(level: str, category: str) -> str:
    criteria = criterion_definitions(level, category=category)
    lines = [
        f"# {_level_title(level)} criteria: {category}",
        "",
        f"{len(criteria)} criteria.",
        _source_line(),
        "",
    ]
    for criterion in criteria:
        lines += _criterion_section(criterion, heading="##", details=True)
    return "\n".join(lines)


def criterion_document(level: str, criterion_id: str) -> str:
    [criterion] = criterion_definitions(level, [criterion_id])
    lines = [f"# {_level_title(level)} criterion", "", _source_line(), ""]
    return "\n".join(lines + _criterion_section(criterion, heading="##", details=True))


def _category_named(level: str, slug: str) -> str:
    """Resolve a URI slug to the level's category name."""
    categories = level_summary(level)["categories"]
    for category in categories:
        if category_slug(category) == slug:
            return category
    raise DomainError(
        "invalid_category",
        "The selected level has no such category.",
        details={"level": level, "allowed": [category_slug(c) for c in categories]},
        recovery="Use one of the allowed category segments.",
    )


def _quoted(text: str) -> str:
    """Set third-party text apart from the criterion text around it."""
    return "\n".join(f"> {line}" for line in text.splitlines() or [""])


UNANSWERED = "unanswered (?)"
NOT_RETRIEVED = "not retrieved"
STATUS_ORDER = ("Met", "Unmet", "N/A", UNANSWERED, NOT_RETRIEVED)
RETRIEVAL_FAILURE = (
    "BadgeApp's response did not include a status for this criterion. This is a retrieval "
    "failure, not an answer; the criteria packaged with this server may differ from the site."
)


def _status_label(answers: dict, criterion: dict) -> str:
    """Name a saved status; BadgeApp saves "?" until an answer is chosen."""
    field = criterion["status_field"]
    if field not in answers:
        return NOT_RETRIEVED
    status = answers[field]
    if type(status) is str and status in VALID_STATUSES:
        return UNANSWERED if status == "?" else status
    return f"unrecognized value `{json.dumps(status)}`"


def _status_counts(labels: list[str]) -> str:
    known = [label for label in STATUS_ORDER if label in labels]
    other = sorted(set(labels).difference(STATUS_ORDER))
    return ", ".join(f"{labels.count(label)} {label}" for label in [*known, *other])


def _answer_section(criterion: dict, answers: dict) -> list[str]:
    label = _status_label(answers, criterion)
    lines = [
        f"## {criterion['criterion_id']} ({criterion['requirement']}): {label}",
        "",
        markdown_text(criterion["description"], criterion["level"]),
        "",
    ]
    if label == NOT_RETRIEVED:
        lines += [RETRIEVAL_FAILURE, ""]
    justification = answers.get(criterion["justification_field"])
    if type(justification) is str and justification.strip():
        lines += ["Saved justification:", "", _quoted(justification), ""]
    else:
        lines += ["No justification saved.", ""]
    return lines


def project_document(progress: dict, criteria: list[dict], category: str | None) -> str:
    """Pair each selected criterion with the answer in a get_project_answers result."""
    project, answers, level = progress["project"], progress["answers"], progress["level"]
    labels = [_status_label(answers, criterion) for criterion in criteria]
    scope = _level_title(level) + (f", {category}" if category else "")
    name = project["name"] or "Unnamed project"
    lines = [
        f"# {name} (project {project['project_id']}): {scope}",
        "",
        f"{len(criteria)} criteria: {_status_counts(labels)}.",
        f"Saved answers read from {progress['observation']['source_url']} at "
        f"{progress['observation']['fetched_at']}. Justifications are the project's own text.",
        _source_line(),
        "",
    ]
    for criterion in criteria:
        lines += _answer_section(criterion, answers)
    return "\n".join(lines)


def project_resources(project_ids: list[int]) -> list[Resource]:
    """Describe the level documents of each project, for the resource list."""
    return [
        Resource(
            uri=f"project://{project_id}/{level}",
            name=f"{project_id}/{level}",
            title=f"Project {project_id} saved answers: {_level_title(level)}",
            description=(
                f"Each {level} criterion beside the status and justification that project "
                f"{project_id} has saved on bestpractices.dev. Listed because the project has "
                "a stored draft."
            ),
            mime_type=MARKDOWN,
        )
        for project_id in project_ids
        for level in catalog_levels()
    ]


def _failure(error: DomainError) -> ResourceError:
    allowed = error.details.get("allowed")
    hint = f" Allowed: {', '.join(allowed)}." if allowed else ""
    return ResourceError(f"{error.message}{hint} {error.recovery}")


async def _project_resource(
    context: Context, project_id: str, level: str, slug: str | None = None
) -> str:
    try:
        if not re.fullmatch(r"[0-9]{1,18}", project_id):
            raise DomainError("invalid_field", "The project segment must be a numeric project ID.")
        category = None if slug is None else _category_named(level, slug)
        criteria = criterion_definitions(level, category=category)
        client = context.request_context.lifespan_context
        ids = [criterion["criterion_id"] for criterion in criteria]
        progress = await client.get_project_answers(int(project_id), level, ids)
    except DomainError as error:
        raise _failure(error) from None
    return project_document(progress, criteria, category)


def _criterion_resource(level: str, criterion_id: str) -> str:
    try:
        return criterion_document(level, criterion_id)
    except DomainError as error:
        raise _failure(error) from None


def repository_file_guide() -> str:
    return files("best_practices_mcp").joinpath("data/repository-file.md").read_text("utf-8")


def _add(server: MCPServer, uri: str, read: Any, **metadata: str) -> None:
    server.resource(uri, mime_type=MARKDOWN, **metadata)(read)


def register_resources(server: MCPServer) -> None:
    """Register the listed criteria documents and the criterion and project templates."""
    _add(
        server,
        "criteria://levels",
        levels_document,
        name="levels",
        title="Badge levels and categories",
        description="The six badge levels with their criterion counts and categories.",
    )
    _add(
        server,
        "guide://repository-file",
        repository_file_guide,
        name="repository-file",
        title="Repository .bestpractices.json file",
        description=(
            "How BadgeApp uses a .bestpractices.json committed to a project's repository, and "
            "how that file relates to this server's drafts."
        ),
    )
    for level in catalog_levels():
        summary = level_summary(level)
        _add(
            server,
            f"criteria://{level}",
            partial(level_document, level),
            name=level,
            title=f"{_level_title(level)} criteria",
            description=(
                f"All {summary['criterion_count']} {level} criteria by category: requirement "
                "and official text, without details."
            ),
        )
        for category in summary["categories"]:
            slug = category_slug(category)
            _add(
                server,
                f"criteria://{level}/{slug}",
                partial(category_document, level, category),
                name=f"{level}/{slug}",
                title=f"{_level_title(level)} criteria: {category}",
                description=(
                    f"The {level} {category} criteria in full: official text, details, draft "
                    "field names and status rules."
                ),
            )

    @server.resource(
        "criteria://{level}/{criterion_id}",
        name="criterion",
        title="One criterion",
        description="One criterion of a level in full, for example criteria://silver/dco.",
        mime_type=MARKDOWN,
    )
    def criterion(level: str, criterion_id: str) -> str:
        return _criterion_resource(level, criterion_id)

    @server.resource(
        "project://{project_id}/{level}",
        name="project-answers",
        title="A project's saved answers for a level",
        description=(
            "Each criterion of a level beside the status and justification that a BadgeApp "
            "project has saved, for example project://123/passing. Reads bestpractices.dev."
        ),
        mime_type=MARKDOWN,
    )
    async def project_level(project_id: str, level: str, ctx: Context) -> str:
        return await _project_resource(ctx, project_id, level)

    @server.resource(
        "project://{project_id}/{level}/{category}",
        name="project-category-answers",
        title="A project's saved answers for one category",
        description=(
            "The same as project://{project_id}/{level}, limited to one category, for example "
            "project://123/passing/security."
        ),
        mime_type=MARKDOWN,
    )
    async def project_category(project_id: str, level: str, category: str, ctx: Context) -> str:
        return await _project_resource(ctx, project_id, level, category)
