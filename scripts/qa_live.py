"""Opt-in live QA of the tools and resources against a project's current saved answers.

This is the tool half of docs/testing/live-browser-qa.md. It assigns the runbook's roles to
whichever criteria meet their conditions when it runs, so it does not depend on an application
staying partly complete; a condition that no criterion meets is reported as unexercised. It makes
paced public GETs through the server, stores a draft only in a temporary directory, and opens no
URL: the report lists each proposal URL with what a signed-in person should see on the form.
"""

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from mcp import Client, MCPError, StdioServerParameters
from mcp.types import TextResourceContents

TOOLS = [
    "build_draft",
    "find_project",
    "get_criteria",
    "get_project_answers",
    "get_project_badge_svg",
    "get_project_status",
    "prepare_update_url",
    "read_draft",
    "update_draft",
    "validate_draft",
]
LEVELS = ["baseline-1", "baseline-2", "baseline-3", "gold", "passing", "silver"]
TEMPLATES = [
    "criteria://{level}/{criterion_id}",
    "project://{project_id}/{level}",
    "project://{project_id}/{level}/{category}",
]
KNOWN_STATUSES = ("Met", "Unmet", "N/A")
RESET_WARNING = "unknown_status_reset_unsupported"
TIMEOUT_SECONDS = 300

# Role: its name in the runbook, then what the form should show after URL A.
ROLES = {
    "A": ("blocked pair", "the saved status and justification are both kept"),
    "B": ("status override", "the status is unchanged and the justification is replaced"),
    "C": ("blank pair", "the status becomes Unmet and the justification is filled"),
    "D": ("retained wording", "the saved justification is kept"),
    "E": ("clear wording", "the justification is empty"),
    "F": ("matching values", "the status and justification are unchanged"),
}
ROLE_A_AFTER_STATUS_OVERRIDE = "the status and justification are both replaced"
NO_CANDIDATE = "no criterion currently meets its condition"


class QAFailure(RuntimeError):
    """A call returned something the remaining checks cannot continue from."""


class Run:
    """The checks, calls and proposal URLs of one client session."""

    def __init__(self, client: Client, project_id: int, level: str) -> None:
        self.client = client
        self.project_id = project_id
        self.level = level
        self.checks: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.urls: list[dict[str, Any]] = []

    def check(self, name: str, passed: bool, detail: str = "") -> None:
        result = "passed" if passed else "failed"
        self.checks.append({"check": name, "result": result, "detail": detail})

    def unexercised(self, name: str, reason: str = NO_CANDIDATE) -> None:
        self.checks.append({"check": name, "result": "unexercised", "detail": reason})

    async def call(
        self, tool: str, arguments: dict[str, Any], expect_error: bool = False
    ) -> dict[str, Any]:
        result = await self.client.call_tool(tool, arguments)
        data = result.structured_content
        self.calls.append(
            {"tool": tool, "arguments": arguments, "is_error": result.is_error, "result": data}
        )
        if not isinstance(data, dict) or result.is_error != expect_error:
            code = data.get("error", {}).get("code") if isinstance(data, dict) else None
            raise QAFailure(f"{tool} returned an unexpected result (error code: {code}).")
        return data

    async def read(self, uri: str) -> str:
        [content] = (await self.client.read_resource(uri)).contents
        if not isinstance(content, TextResourceContents):
            raise QAFailure(f"{uri} did not return text content.")
        self.calls.append(
            {"resource": uri, "mime_type": content.mime_type, "characters": len(content.text)}
        )
        return content.text

    async def prepare(
        self, section: str, draft: dict[str, Any], overrides: dict[str, Any]
    ) -> dict[str, Any]:
        arguments = {"project_id": self.project_id, "section": section, "draft": draft}
        return await self.call("prepare_update_url", arguments | {"overrides": overrides})


def select_roles(
    answers: dict[str, Any], criteria: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Assign criteria to the runbook's roles and unknown-reset cases from the saved answers.

    Roles A, B, D, E and F each need a different criterion with a saved status and justification;
    C needs one with neither. The reset cases need a saved status with and without a
    justification. A role is None when no criterion meets its condition.
    """
    worded: list[dict[str, Any]] = []
    bare: list[dict[str, Any]] = []
    blank: list[dict[str, Any]] = []
    for criterion in criteria:
        status = answers.get(criterion["status_field"])
        justified = bool((answers.get(criterion["justification_field"]) or "").strip())
        if status in KNOWN_STATUSES:
            (worded if justified else bare).append(criterion)
        elif status == "?" and not justified:
            blank.append(criterion)
    pool = iter(worded)
    roles = {role: next(pool, None) for role in "ABDEF"}
    roles["C"] = blank[0] if blank else None
    resets = {"with a justification": next(iter(worded), None)}
    resets["without a justification"] = next(iter(bare), None)
    return roles, resets


def proposal(
    roles: dict[str, Any], answers: dict[str, Any], text: str
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Return the fields supplied for the assigned roles, URL A's overrides and URL B's addition."""
    changes: dict[str, Any] = {}
    overrides: list[str] = []
    added: list[str] = []
    fields = {
        role: (criterion["status_field"], criterion["justification_field"])
        for role, criterion in roles.items()
        if criterion
    }
    if "A" in fields:
        status, justification = fields["A"]
        changes |= {status: _other_status(answers[status]), justification: text}
        overrides.append(justification)
        added.append(status)
    if "B" in fields:
        status, justification = fields["B"]
        changes |= {status: answers[status], justification: text}
        overrides.append(status)
    if "C" in fields:
        status, justification = fields["C"]
        changes |= {status: "Unmet", justification: text}
    if "D" in fields:
        changes[fields["D"][1]] = text
    if "E" in fields:
        changes[fields["E"][1]] = ""
        overrides.append(fields["E"][1])
    if "F" in fields:
        status, justification = fields["F"]
        changes |= {status: answers[status], justification: answers[justification]}
    return changes, overrides, added


def _other_status(saved: str) -> str:
    return "Unmet" if saved == "Met" else "Met"


def category_slug(category: str) -> str:
    """The category segment of a resource URI, as the server's resource module documents it."""
    return category.lower().replace(" ", "-")


def decoded(url: str) -> tuple[str, dict[str, Any]]:
    parts = urlsplit(url)
    return parts.path, dict(parse_qsl(parts.query, keep_blank_values=True))


def reset_warning_fields(result: dict[str, Any]) -> list[str]:
    warnings = [w for w in result["warnings"] if w["code"] == RESET_WARNING]
    return sorted(field for warning in warnings for field in warning["fields"])


def check_url(
    run: Run,
    name: str,
    result: dict[str, Any],
    draft: dict[str, Any],
    overridden: list[str],
    expect: list[str],
) -> None:
    """Compare a prepare_update_url result with the draft it was given and record its URL.

    `overridden` lists the fields expected in effective_overrides; the query parameter is their
    sorted names, or "*" when the request was for every field.
    """
    artifact = result["artifact"]
    if artifact is None:
        run.check(f"{name}: a URL is returned", False, str(result["no_artifact_reason"]))
        return
    path, query = decoded(artifact["url"])
    parameter = query.pop("overrides", None)
    section = "choose" if result["section"] == "choose_section" else result["section"]
    excluded = sorted(row["field"] for row in result["transfer"] if row["disposition"] != "encoded")
    run.check(
        f"{name}: every supplied field is encoded",
        result["outcome"] == "complete" and not excluded,
        ", ".join(excluded),
    )
    run.check(
        f"{name}: the decoded query equals the draft",
        query == draft and path == f"/en/projects/{run.project_id}/{section}/edit",
        path,
    )
    wildcard = result["overrides"]["mode"] == "all"
    expected_parameter = "*" if wildcard else ",".join(sorted(overridden)) or None
    run.check(
        f"{name}: only the requested overrides are sent",
        parameter == expected_parameter
        and sorted(result["effective_overrides"]) == sorted(overridden),
        parameter or "",
    )
    run.urls.append({"name": name, "url": artifact["url"], "expect": expect})


async def check_reads(run: Run) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    tools = sorted(tool.name for tool in (await run.client.list_tools()).tools)
    run.check("tools/list returns the ten tools", tools == TOOLS, ", ".join(tools))
    status = await run.call("get_project_status", {"project_id": run.project_id})
    reported = sorted(entry["level"] for entry in status["levels"])
    run.check("get_project_status reports the six levels", reported == LEVELS)
    saved = await run.call(
        "get_project_answers", {"project_id": run.project_id, "level": run.level}
    )
    full = await run.call("get_criteria", {"level": run.level, "detail": "full"})
    answers, criteria = saved["answers"], full["criteria"]
    statuses = [field for field in answers if field.endswith("_status")]
    run.check(
        "get_project_answers returns a status for every criterion of the level",
        not saved["statuses_not_retrieved"]
        and len(statuses) == len(criteria) == saved["level_criterion_count"],
        f"{len(statuses)} of {len(criteria)}",
    )
    refused = await run.call(
        "get_project_answers", {"project_id": run.project_id, "level": "bronze"}, expect_error=True
    )
    issues = refused["error"]["details"].get("issues", [])
    run.check(
        "an unknown level is refused with the allowed values",
        refused["error"]["code"] == "invalid_arguments"
        and [sorted(issue.get("allowed", [])) for issue in issues] == [LEVELS],
    )
    return status["project"], answers, criteria


async def check_proposals(
    run: Run, roles: dict[str, Any], answers: dict[str, Any], text: str
) -> dict[str, Any]:
    """Runbook section 1: one document, URL A, then URL B with role A's status overridden."""
    for role, criterion in roles.items():
        if criterion is None:
            run.unexercised(f"role {role} ({ROLES[role][0]})")
    changes, overrides, added = proposal(roles, answers, text)
    if not changes:
        return {}
    built = await run.call("build_draft", {"draft": {}, "changes": changes})
    draft: dict[str, Any] = built["draft"]
    run.check("build_draft returns the supplied fields unchanged", draft == changes)
    expect = [
        f"{role} `{criterion['criterion_id']}`: {ROLES[role][1]}"
        for role, criterion in sorted(roles.items())
        if criterion
    ]
    mode = {"mode": "fields", "fields": overrides} if overrides else {"mode": "none"}
    check_url(run, "URL A", await run.prepare(run.level, draft, mode), draft, overrides, expect)
    if added:
        both = overrides + added
        result = await run.prepare(run.level, draft, {"mode": "fields", "fields": both})
        expect = [f"A `{roles['A']['criterion_id']}`: {ROLE_A_AFTER_STATUS_OVERRIDE}"]
        check_url(run, "URL B", result, draft, both, [*expect, "other roles: as for URL A"])
    return draft


async def check_chooser(run: Run, draft: dict[str, Any]) -> None:
    """Runbook section 2, case 1: a mixed-level document through the section chooser."""
    other = "passing" if run.level.startswith("baseline") else "baseline-1"
    index = await run.call("get_criteria", {"level": other})
    foreign = f"{index['criteria'][0]['criterion_id']}_status"
    mixed = draft | {foreign: "Met"}
    result = await run.prepare("choose_section", mixed, {"mode": "all"})
    expect = [
        "the chooser page lists the badge sections",
        f"choosing {run.level} keeps every proposal and the wildcard override",
        "every supplied value for that section replaces the saved one",
    ]
    check_url(run, "Chooser URL", result, mixed, list(mixed), expect)
    [row] = [row for row in result["transfer"] if row["field"] == foreign]
    run.check(
        "Chooser URL: a field of another level names that level",
        other in row["applicable_levels"],
        ", ".join(row["applicable_levels"]),
    )


async def check_resets(run: Run, resets: dict[str, Any], answers: dict[str, Any]) -> None:
    """Runbook section 2, cases 2 and 3: proposals to reset a saved status to "?"."""
    for condition, criterion in resets.items():
        if criterion is None:
            run.unexercised(f"unknown reset of a saved status {condition}")
    chosen = [criterion for criterion in resets.values() if criterion]
    if not chosen:
        return
    fields = [criterion["status_field"] for criterion in chosen]
    reset = dict.fromkeys(fields, "?")
    kept = ["each saved status is kept; the reset is not applied"]
    cases: tuple[tuple[str, dict[str, Any], dict[str, Any], list[str]], ...] = (
        ("Reset URL, named overrides", reset, {"mode": "fields", "fields": fields}, fields),
        ("Reset URL, override all", reset, {"mode": "all"}, fields),
        ("Reset URL, no override", {fields[0]: "?"}, {"mode": "none"}, []),
    )
    for name, draft, overrides, overridden in cases:
        result = await run.prepare(run.level, draft, overrides)
        check_url(run, name, result, draft, overridden, kept)
        run.check(
            f"{name}: the reset warning names the fields",
            reset_warning_fields(result) == sorted(draft),
        )
    validated = await run.call(
        "validate_draft", {"project_id": run.project_id, "section": run.level, "draft": reset}
    )
    skipped = sorted(
        entry["criterion_id"]
        for entry in validated["skipped_criteria"]
        if entry["reason"] == "status_unknown"
    )
    run.check(
        "validate_draft gives the same warning and skips the unknown statuses",
        reset_warning_fields(validated) == sorted(reset)
        and skipped == sorted(criterion["criterion_id"] for criterion in chosen)
        and not validated["findings"],
    )
    control = {field: _other_status(answers[field]) for field in fields}
    result = await run.prepare(run.level, control, {"mode": "fields", "fields": fields})
    changed = ["each status changes to the proposed value (positive control for the resets)"]
    check_url(run, "Control URL", result, control, fields, changed)


async def check_resources(
    run: Run, answers: dict[str, Any], criteria: list[dict[str, Any]]
) -> None:
    """Resource listing and documents, and their agreement with the tools' results."""
    client, level, project_id = run.client, run.level, run.project_id
    summary = (await run.call("get_criteria", {}))["levels"]
    levels = {entry["level"] for entry in summary}
    fixed = {"criteria://levels", "guide://repository-file"}
    fixed |= {f"criteria://{name}" for name in levels}
    fixed |= {
        f"criteria://{entry['level']}/{category_slug(category)}"
        for entry in summary
        for category in entry["categories"]
    }
    listed = {str(resource.uri) for resource in (await client.list_resources()).resources}
    run.check(
        "resources/list holds the criteria documents and the guide, and no project yet",
        listed == fixed,
        f"{len(listed)} listed, {len(fixed)} expected",
    )
    templates = (await client.list_resource_templates()).resource_templates
    run.check(
        "resources/templates/list holds the three templates",
        sorted(template.uri_template for template in templates) == TEMPLATES,
    )

    sample = criteria[0]
    slug = category_slug(sample["category"])
    overview = await run.read("criteria://levels")
    documents = [
        await run.read(uri)
        for uri in (
            f"criteria://{level}",
            f"criteria://{level}/{slug}",
            f"criteria://{level}/{sample['criterion_id']}",
        )
    ]
    run.check(
        "criteria documents name the level and the sampled criterion",
        f"criteria://{level}" in overview
        and all(sample["criterion_id"] in document for document in documents),
    )
    guide = await run.read("guide://repository-file")
    run.check("the repository-file guide is readable", ".bestpractices.json" in guide)

    def heading(criterion: dict[str, Any]) -> str:
        status = answers.get(criterion["status_field"])
        label = "unanswered (?)" if status == "?" else status
        return f"## {criterion['criterion_id']} ({criterion['requirement']}): {label}"

    lines = (await run.read(f"project://{project_id}/{level}")).splitlines()
    differing = [c["criterion_id"] for c in criteria if heading(c) not in lines]
    run.check(
        "the project document shows the status get_project_answers returned for every criterion",
        not differing,
        ", ".join(differing),
    )
    in_category = [heading(c) for c in criteria if c["category"] == sample["category"]]
    lines = (await run.read(f"project://{project_id}/{level}/{slug}")).splitlines()
    run.check(
        "the project category document holds that category's criteria and no others",
        [line for line in lines if line.startswith("## ")] == in_category,
    )
    for uri in ("criteria://bronze", f"project://{project_id}/{level}/no-such-category"):
        try:
            await client.read_resource(uri)
            refused = False
        except MCPError:
            refused = True
        run.check(f"reading {uri} is refused", refused)

    stored = await run.call("update_draft", {"project_id": project_id, "changes": {}})
    relisted = await client.list_resources(cache_mode="refresh")
    added = {str(resource.uri) for resource in relisted.resources} - listed
    run.check(
        "a stored draft adds the project's level documents to resources/list",
        stored["created"] and added == {f"project://{project_id}/{name}" for name in levels},
        f"{len(added)} added",
    )


async def qualify(server: list[str], project_id: int, level: str) -> dict[str, Any]:
    """Run every check against one server process and return the report."""
    roles: dict[str, Any] = {}
    resets: dict[str, Any] = {}
    answers: dict[str, Any] = {}
    project: dict[str, Any] = {"project_id": project_id, "name": None}
    with tempfile.TemporaryDirectory() as root:
        parameters = StdioServerParameters(
            command=server[0], args=server[1:], env={"BESTPRACTICES_DATA_DIR": root}
        )
        async with (
            asyncio.timeout(TIMEOUT_SECONDS),
            Client(parameters, read_timeout_seconds=60) as client,
        ):
            run = Run(client, project_id, level)
            identity, protocol = client.server_info, client.protocol_version
            # Record a failure as a check so the client closes before anything is reported.
            try:
                project, answers, criteria = await check_reads(run)
                roles, resets = select_roles(answers, criteria)
                repository = project["repo_url"] or project["homepage_url"] or "https://example.org"
                text = f"  QA preview only — not saved. {repository}?q=a&x=2#qa  "
                draft = await check_proposals(run, roles, answers, text)
                await check_chooser(run, draft)
                await check_resets(run, resets, answers)
                await check_resources(run, answers, criteria)
            except (QAFailure, MCPError) as error:
                run.check("the run completed", False, str(error))
    return {
        "project": project,
        "level": level,
        "server": f"{identity.name} {identity.version}" if identity else "unidentified",
        "protocol": protocol,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "roles": {role: _saved(criterion, answers) for role, criterion in sorted(roles.items())},
        "resets": {
            condition: _saved(criterion, answers) for condition, criterion in resets.items()
        },
        "checks": run.checks,
        "urls": run.urls,
        "calls": run.calls,
    }


def _saved(criterion: dict[str, Any] | None, answers: dict[str, Any]) -> dict[str, Any] | None:
    if criterion is None:
        return None
    return {
        "criterion_id": criterion["criterion_id"],
        "status": answers[criterion["status_field"]],
        "justification_characters": len(answers.get(criterion["justification_field"]) or ""),
    }


def render(report: dict[str, Any]) -> str:
    """Format a report as Markdown: checks, the criteria chosen, then the browser steps."""
    project = report["project"]
    lines = [
        f"# Live QA: project {project['project_id']} ({project['name']}), {report['level']}",
        "",
        f"Server {report['server']}, protocol {report['protocol']}, run at {report['run_at']}.",
        "",
        "## Checks",
        "",
        "| Check | Result | Detail |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {c['check']} | {c['result']} | {c['detail']} |" for c in report["checks"]]
    lines += ["", "## Criteria chosen from the saved answers", ""]
    lines += [
        "| Use | Criterion | Saved status | Saved justification |",
        "| --- | --- | --- | --- |",
    ]
    uses = {f"{role}: {ROLES[role][0]}": saved for role, saved in report["roles"].items()}
    uses |= {f"reset {condition}": saved for condition, saved in report["resets"].items()}
    for use, saved in uses.items():
        if saved is None:
            lines.append(f"| {use} | none | | |")
            continue
        size = f"{saved['justification_characters']} characters"
        lines.append(f"| {use} | `{saved['criterion_id']}` | {saved['status']} | {size} |")
    lines += [
        "",
        "## Browser steps",
        "",
        "Sign in as an editor of the project and record the plain edit page first. Open each URL "
        "exactly as printed, compare the named criteria, and leave without saving. Newly applied "
        "justification text is shown without its leading and trailing spaces.",
    ]
    for entry in report["urls"]:
        lines += ["", f"### {entry['name']}", "", f"<{entry['url']}>", ""]
        lines += [f"- {expectation}" for expectation in entry["expect"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--level", choices=LEVELS, required=True)
    parser.add_argument(
        "--server",
        help="server executable to qualify, for example an installed bestpractices-mcp; "
        "defaults to this checkout's package",
    )
    parser.add_argument(
        "--output-dir", type=Path, help="write report.md and calls.json to this directory"
    )
    args = parser.parse_args()
    if args.project_id <= 0:
        parser.error("project-id must be positive")
    server = [args.server] if args.server else [sys.executable, "-m", "best_practices_mcp"]
    try:
        report = asyncio.run(qualify(server, args.project_id, args.level))
    except TimeoutError:
        print(f"Live QA did not finish within {TIMEOUT_SECONDS} seconds.", file=sys.stderr)
        raise SystemExit(1) from None
    text = render(report)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "report.md").write_text(text, encoding="utf-8")
        calls = json.dumps(report["calls"], indent=2, ensure_ascii=False)
        (args.output_dir / "calls.json").write_text(calls + "\n", encoding="utf-8")
    print(text, end="")
    if any(check["result"] == "failed" for check in report["checks"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
