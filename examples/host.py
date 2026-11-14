"""Small MCP-only terminal host for public reads and explicit or stored drafts.

Files are imported/exported only at host-chosen paths. The host never opens a
browser, executes generated JavaScript, or saves BadgeApp forms.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
import sysconfig
from collections.abc import Callable
from pathlib import Path

from mcp import Client, MCPError, StdioServerParameters

READ_TOOLS = frozenset({"get_criteria", "find_project", "get_project_progress"})
BADGE_TOOLS = frozenset({"get_project_badge_status", "get_project_badge_svg"})
STORAGE_TOOLS = frozenset({"read_draft", "update_draft"})
KNOWN_UPDATE_REJECTIONS = frozenset(
    {
        "invalid_document",
        "invalid_field",
        "draft_not_found",
        "draft_read_failed",
        "draft_write_failed",
        "document_too_large",
        "response_too_large",
        "project_mismatch",
        "project_identity_unresolved",
    }
)
REGISTRATION_URL = "https://www.bestpractices.dev/en/projects/new"
CALL_TIMEOUT_SECONDS = 45
MAX_IMPORT_BYTES = 1024 * 1024
METADATA_FIELDS = ("name", "description", "license", "implementation_languages")
DOCUMENT_TOOLS = frozenset(
    {"build_draft", "validate_draft", "prepare_update_url", "prepare_update_script"}
)


class HostError(Exception):
    """A safe, actionable host compatibility or interaction failure."""


def payload_from_result(result) -> dict:
    """Use structured content, with the server's JSON text compatibility fallback."""
    payload = result.structured_content
    if payload is None:
        texts = [block.text for block in result.content if block.type == "text"]
        try:
            payload = json.loads(texts[0]) if texts else None
        except (ValueError, TypeError) as exc:
            raise HostError("The server returned unreadable JSON content.") from exc
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int:
        raise HostError("The server returned an incompatible result envelope.")
    if payload["schema_version"] != 1:
        raise HostError("This host supports domain schema_version 1 only.")
    return payload


async def discover(client: Client) -> dict:
    """Require the three implemented read tools and their advertised schemas."""
    listing = await client.list_tools()
    tools = {tool.name: tool for tool in listing.tools}
    missing = READ_TOOLS - tools.keys()
    if missing:
        raise HostError("Missing required read tools: " + ", ".join(sorted(missing)))
    for name in READ_TOOLS | ((BADGE_TOOLS | DOCUMENT_TOOLS | STORAGE_TOOLS) & tools.keys()):
        tool = tools[name]
        if not tool.input_schema or not tool.output_schema:
            raise HostError(f"Tool {name} does not advertise input and output schemas.")
    return {
        "server": client.server_info.name if client.server_info else None,
        "protocol_version": client.protocol_version,
        "tools": sorted(tools),
        "instructions": client.instructions,
    }


class ReadHost:
    """Host-owned selection state; the MCP server receives explicit IDs per call."""

    def __init__(
        self,
        client: Client,
        read: Callable[[str], str] = input,
        write: Callable[[str], None] = print,
        *,
        mode: str = "document",
    ) -> None:
        self.client = client
        self.mode = mode
        self.read = read
        self.write = write
        self.project_id: int | None = None
        self.level: str | None = None
        self.document: dict | None = None
        self.artifacts: dict[str, str] = {}

    async def ask(self, prompt: str) -> str:
        try:
            return (await asyncio.to_thread(self.read, prompt)).strip()
        except EOFError:
            return "quit"

    async def call(self, name: str, arguments: dict) -> dict | None:
        try:
            result = await self.client.call_tool(
                name, arguments, read_timeout_seconds=CALL_TIMEOUT_SECONDS
            )
        except MCPError as exc:
            self.write(f"protocol_error ({exc.code}): {exc.message}")
            self.uncertain_write(name)
            return None
        except TimeoutError:
            self.write("timeout: The call did not finish.")
            if not self.uncertain_write(name):
                self.write("Retry the read explicitly when ready.")
            return None
        except Exception:
            if not self.uncertain_write(name):
                raise
            return None
        if result.is_error:
            self.show_error(result, name=name)
            return None
        try:
            return payload_from_result(result)
        except HostError:
            if self.uncertain_write(name):
                return None
            raise

    def uncertain_write(self, name: str) -> bool:
        if name != "update_draft":
            return False
        self.artifacts.clear()
        self.write(
            "Write outcome uncertain; no retry was attempted. "
            "Use read to inspect the stored draft before deciding on another edit."
        )
        return True

    def show_error(self, result, *, name: str | None = None) -> None:
        try:
            payload = payload_from_result(result)
            error = payload.get("error", {})
            if not isinstance(error, dict):
                raise HostError("The server returned an incompatible error envelope.")
        except HostError:
            texts = [block.text for block in result.content if block.type == "text"]
            error = {"message": texts[0] if texts else "Tool execution failed."}
        self.write(f"{error.get('code', 'tool_error')}: {error.get('message', 'Read failed.')}")
        code = error.get("code")
        if name == "update_draft" and (
            not isinstance(code, str) or code not in KNOWN_UPDATE_REJECTIONS
        ):
            self.uncertain_write(name)
            return
        self.write("Recovery: " + error.get("recovery", "Inspect the request and retry."))
        if error.get("retry_after_seconds") is not None:
            self.write(f"Retry after at least {error['retry_after_seconds']} seconds.")

    def show_progress(self, result: dict) -> None:
        project = result["project"]
        self.write(f"Project {project['project_id']}: {json.dumps(project['name'])}")
        self.write("Saved public observation (not a local draft):")
        self.write(json.dumps(result, ensure_ascii=False, indent=2))

    def show_candidates(self, result: dict) -> None:
        self.write(f"Lookup page {result['page']}:")
        for candidate in result["candidates"]:
            project = candidate["project"]
            self.write(
                f"  {project['project_id']}: {json.dumps(project['name'])} "
                f"repo={json.dumps(project['repo_url'])} "
                f"homepage={json.dumps(project['homepage_url'])} "
                f"match={candidate['match_basis']}"
            )
        if not result["pagination_complete"] and result["next_page"] is None:
            self.write("More pages may exist; the upstream did not confirm a next page.")

    async def verify_selection(self, project_id: int) -> bool:
        result = await self.call("get_project_progress", {"project_id": project_id})
        if result is None:
            return False
        if result["project"]["project_id"] != project_id:
            raise HostError("The server returned a different project than the selected ID.")
        if self.project_id != project_id:
            self.clear_document()
        self.project_id = project_id
        self.write(f"Selected registered project {project_id}.")
        self.show_progress(result)
        return True

    async def empty_search(self) -> str:
        self.write("No registered project matched. No draft or form work has begun.")
        self.write(f"Register on BadgeApp if needed: {REGISTRATION_URL}")
        return await self.ask("r=repeat lookup after registration, s=new search, c=cancel: ")

    async def choose_candidate(self, result: dict) -> str:
        self.show_candidates(result)
        return await self.ask(
            "Enter a listed project ID explicitly, n=next, s=new search, c=cancel: "
        )

    async def search_pages(self, query: str) -> bool:
        """Return true only when the user requests a new search."""
        page = 1
        while True:
            result = await self.call("find_project", {"query": query, "page": page})
            if result is None:
                return False
            choice = await self.search_choice(result)
            if choice in {"c", "quit"}:
                return False
            if choice == "s":
                return True
            if choice == "r":
                continue
            if choice == "n":
                page = self.next_page(result, page)
                continue
            if await self.select_listed(choice, result):
                return False

    async def search_choice(self, result: dict) -> str:
        if not result["candidates"]:
            if result["page"] > 1:
                self.write("No further matches on this page. Earlier pages may contain matches.")
                return await self.ask("s=new search (or revisit earlier results), c=cancel: ")
            return await self.empty_search()
        return await self.choose_candidate(result)

    def next_page(self, result: dict, page: int) -> int:
        if result["pagination_complete"]:
            self.write("No next page is available for this lookup.")
            return page
        return result["next_page"] or page + 1

    async def select_listed(self, choice: str, result: dict) -> bool:
        candidates = {str(item["project"]["project_id"]) for item in result["candidates"]}
        if choice not in candidates:
            self.write("Choose an ID displayed on this page; nothing was selected.")
            return False
        return await self.verify_selection(int(choice))

    async def find(self) -> None:
        self.project_id = None
        self.level = None
        self.clear_document()
        while True:
            query = await self.ask("Project name, URL, or remembered ID (blank cancels): ")
            if not query or query == "quit":
                return
            if not await self.search_pages(query):
                return

    async def choose_level(self) -> None:
        result = await self.call("get_criteria", {})
        if result is None:
            return
        self.write("Supported levels: " + ", ".join(result["levels"]))
        choice = await self.ask("Level (blank cancels): ")
        if choice in result["levels"]:
            if self.level != choice:
                self.artifacts.clear()
            self.level = choice
            self.write(f"Selected level {choice}.")
        elif choice and choice != "quit":
            self.write("Choose a supported level; the previous level is unchanged.")

    async def progress(self) -> None:
        if self.project_id is None:
            self.write("Find and explicitly select a registered project first.")
            return
        arguments: dict = {"project_id": self.project_id}
        if self.level is not None:
            arguments["level"] = self.level
        result = await self.call("get_project_progress", arguments)
        if result is not None:
            self.show_progress(result)

    async def criteria(self) -> None:
        if self.level is None:
            self.write("Choose a level first; general criteria lookup needs no project selection.")
            return
        selected = await self.ask("Criterion IDs, comma-separated (blank means all): ")
        if selected == "quit":
            return
        arguments: dict = {"level": self.level}
        if selected:
            arguments["criterion_ids"] = [item.strip() for item in selected.split(",")]
        result = await self.call("get_criteria", arguments)
        if result is not None:
            self.write(
                "Official packaged criteria; catalog revision may differ from the live site:"
            )
            self.write(json.dumps(result, ensure_ascii=False, indent=2))

    def clear_document(self) -> None:
        self.document = None
        self.artifacts.clear()

    def ready(self, *, document: bool = True, level: bool = False) -> bool:
        if self.project_id is None:
            self.write("Find and explicitly select a registered project first.")
            return False
        if document and self.mode == "document" and self.document is None:
            self.write("Create a new document or import one first.")
            return False
        if level and self.level is None:
            self.write("Choose a level first.")
            return False
        return True

    def show_json(self, value: dict) -> None:
        self.write(json.dumps(value, ensure_ascii=False, indent=2))

    async def replace_document(self, draft, changes: dict) -> None:
        result = await self.call("build_draft", {"draft": draft, "changes": changes})
        if result is not None:
            self.document = result["draft"]
            self.artifacts.clear()
            self.write("Host document updated in memory; saved public answers are unchanged.")
            self.show_json(result)

    async def patch_document(self, changes: dict) -> None:
        if self.mode == "document":
            await self.replace_document(self.document, changes)
            return
        result = await self.call(
            "update_draft", {"project_id": self.project_id, "changes": changes}
        )
        if result is not None:
            self.artifacts.clear()
            self.write("Stored draft updated; saved BadgeApp answers are unchanged.")
            self.show_json(result)

    async def initialize_stored(self) -> None:
        if self.ready(document=False):
            await self.patch_document({})

    async def read_stored(self) -> dict | None:
        result = await self.call("read_draft", {"project_id": self.project_id})
        if result is not None:
            self.write("Server draft location: " + result["location"])
        else:
            self.write("A missing draft can be created explicitly with edit or init.")
        return result

    async def new_document(self) -> None:
        if self.ready(document=False):
            await self.replace_document({}, {})

    async def import_document(self) -> None:
        if not self.ready(document=False):
            return
        selected = await self.ask("JSON document path (blank cancels): ")
        if not selected or selected == "quit":
            return
        try:
            draft = load_document(Path(selected).expanduser())
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            self.write(f"Import failed; document unchanged: {exc}")
            return
        await self.replace_document(draft, {})

    async def edit_document(self) -> None:
        if not self.ready():
            return
        fields = await self.editable_fields()
        self.write("Writable fields: " + ", ".join(sorted(fields)))
        field = await self.ask("Field (blank cancels): ")
        if not field or field == "quit":
            return
        if field not in fields:
            self.write("Choose a displayed canonical field; select a level for criterion fields.")
            return
        # JSON import supports multiline text; an entered empty string is intentional.
        try:
            value = await asyncio.to_thread(self.read, "Text value (empty text is allowed): ")
        except EOFError:
            self.write("Input ended; document unchanged.")
            return
        await self.patch_document({field: value})

    async def editable_fields(self) -> set[str]:
        fields = set(METADATA_FIELDS)
        if self.level is not None:
            result = await self.call("get_criteria", {"level": self.level})
            if result is not None:
                for criterion in result["criteria"]:
                    fields.update((criterion["status_field"], criterion["justification_field"]))
        return fields

    async def remove_fields(self) -> None:
        if not self.ready():
            return
        selected = await self.ask("Fields to remove, comma-separated (blank cancels): ")
        if selected and selected != "quit":
            await self.patch_document(dict.fromkeys(comma_fields(selected)))

    async def show_document(self) -> None:
        if not self.ready():
            return
        if self.mode == "stored":
            result = await self.read_stored()
            if result is not None:
                self.show_json(result)
            return
        self.write("Host document (not a saved BadgeApp observation):")
        self.show_json(self.document)

    async def validate_document(self) -> None:
        if self.ready(level=True):
            result = await self.call("validate_draft", self.document_arguments(self.document))
            if result is not None:
                self.show_json(result)

    def document_arguments(self, document: dict | None) -> dict:
        arguments = {"project_id": self.project_id, "level": self.level}
        if document is not None:
            arguments["draft"] = document
        return arguments

    async def scoped_arguments(self) -> dict | None:
        selected = await self.ask(
            "Fields to propose, comma-separated (blank means whole document): "
        )
        if selected == "quit":
            return None
        if not selected:
            return self.document_arguments(self.document)
        document = self.document
        if self.mode == "stored":
            result = await self.read_stored()
            if result is None:
                return None
            document = result["draft"]
        fields = comma_fields(selected)
        unknown = set(fields) - document.keys()
        if unknown:
            self.write("Fields absent from the document: " + ", ".join(sorted(unknown)))
            return None
        # Retain identity provenance in the temporary subset; the original stays unchanged.
        retained = set(fields) | {"id", "repo_url"}
        subset = {key: value for key, value in document.items() if key in retained}
        return self.document_arguments(subset)

    async def prepare_url(self) -> None:
        await self.prepare_artifact("url")

    async def prepare_script(self) -> None:
        await self.prepare_artifact("script")

    async def prepare_artifact(self, kind: str) -> None:
        if not self.ready(level=True):
            return
        arguments = await self.scoped_arguments()
        if arguments is None:
            return
        if kind == "url":
            selected = await self.ask(
                "Exact override field names, comma-separated (blank means none): "
            )
            if selected == "quit":
                return
            arguments["override_fields"] = comma_fields(selected)
        self.artifacts.pop(kind, None)
        result = await self.call(f"prepare_update_{kind}", arguments)
        if result is not None:
            self.show_artifact(kind, result)

    def show_artifact(self, kind: str, result: dict) -> None:
        self.write("Proposal only: inspect included and excluded fields; nothing has been applied.")
        self.show_json(result)
        self.write(
            "The report describes artifact contents. "
            "Review actual field values in BadgeApp before saving."
        )
        artifact = result.get("artifact")
        if artifact is None:
            self.write("No artifact generated; inspect outcome and no_artifact_reason above.")
            return
        key = "url" if kind == "url" else "javascript"
        self.artifacts[kind] = artifact[key]
        self.write("Exact artifact (export preserves UTF-8 bytes without added newline):")
        self.write(artifact[key])
        self.write(
            "Use export to save explicitly. Review in your authenticated browser; saving is manual."
        )

    async def export_file(self) -> None:
        if not self.ready():
            return
        kind = await self.ask("Export document / url / script (blank cancels): ")
        if kind == "document":
            document = self.document
            if self.mode == "stored":
                result = await self.read_stored()
                if result is None:
                    return
                document = result["draft"]
            content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        else:
            content = self.artifacts.get(kind)
        if content is None:
            self.write("No such current artifact; generate it first.")
            return
        selected = await self.ask("Export path (blank cancels; existing files are refused): ")
        if not selected or selected == "quit":
            return
        try:
            with Path(selected).expanduser().open("xb") as stream:
                stream.write(content.encode("utf-8"))
        except OSError as exc:
            self.write(f"Export failed: {exc}")
            return
        self.write(f"Exported {kind} to {selected}.")

    async def run(self) -> None:
        self.write("Reference host. Validation is optional; artifacts never apply or save changes.")
        commands = {
            "find": self.find,
            "level": self.choose_level,
            "progress": self.progress,
            "refresh": self.progress,
            "criteria": self.criteria,
            "edit": self.edit_document,
            "remove": self.remove_fields,
            "show": self.show_document,
            "validate": self.validate_document,
            "url": self.prepare_url,
            "script": self.prepare_script,
            "export": self.export_file,
        }
        if self.mode == "stored":
            commands.update({"init": self.initialize_stored, "read": self.show_document})
        else:
            commands.update({"new": self.new_document, "import": self.import_document})
        while True:
            choice = await self.ask(
                f"[mode={self.mode}, project={self.project_id}, level={self.level}] "
                + " / ".join(commands)
                + " / quit: "
            )
            if choice == "quit":
                return
            if action := commands.get(choice):
                await action()
            else:
                self.write("Choose one of the listed commands.")


def comma_fields(value: str) -> list[str]:
    return [field.strip() for field in value.split(",") if field.strip()]


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_document(path: Path):
    with path.open("rb") as stream:
        encoded = stream.read(MAX_IMPORT_BYTES + 1)
    if len(encoded) > MAX_IMPORT_BYTES:
        raise ValueError("JSON import exceeds the 1 MiB host limit.")
    document = json.loads(
        encoded.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant
    )
    # The decoder accepts exponent overflow and escaped lone surrogates. Reject
    # both before handing the document to the SDK's JSON/UTF-8 transport.
    json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return document


def reject_constant(value: str):
    raise ValueError(f"Non-JSON numeric constant: {value}")


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "--discover", action="store_true", help="Print discovery and exit without reads"
    )
    cli.add_argument(
        "--server-command", help="Shell-quoted executable and arguments; executed without a shell"
    )
    cli.add_argument("--mode", choices=("document", "stored"), default="document")
    cli.add_argument(
        "--data-dir", type=Path, help="Absolute storage override passed only to server"
    )
    return cli


def server_parameters(args: argparse.Namespace) -> StdioServerParameters:
    suffix = ".exe" if sys.platform == "win32" else ""
    executable = str(Path(sysconfig.get_path("scripts")) / f"bestpractices-mcp{suffix}")
    command = shlex.split(args.server_command) if args.server_command else [executable]
    if not command:
        raise HostError("--server-command must name an executable.")
    if args.data_dir is not None and not args.data_dir.is_absolute():
        raise HostError("--data-dir must be an absolute path.")
    env = {"BESTPRACTICES_DATA_DIR": str(args.data_dir)} if args.data_dir is not None else None
    return StdioServerParameters(command=command[0], args=command[1:], env=env)


async def main(args: argparse.Namespace) -> None:
    async with Client(server_parameters(args), read_timeout_seconds=CALL_TIMEOUT_SECONDS) as client:
        info = await discover(client)
        if args.discover:
            print(json.dumps(info, indent=2))
            return
        print(f"Connected to {info['server']} using MCP {info['protocol_version']}.")
        required = DOCUMENT_TOOLS | (STORAGE_TOOLS if args.mode == "stored" else set())
        missing = required - set(info["tools"])
        if missing:
            raise HostError("Missing required workflow tools: " + ", ".join(sorted(missing)))
        if args.mode == "stored":
            print("Stored mode: project-keyed server files; edit can create without a prior read.")
            print("Avoid simultaneous writers from other servers or editors using the same root.")
        else:
            print("Document mode: local memory with explicit host file import/export.")
        await ReadHost(client, mode=args.mode).run()


def entrypoint() -> None:
    # Piped Windows streams otherwise use the locale code page, corrupting exact
    # Unicode answers and artifacts before/after the UTF-8 MCP connection.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    try:
        asyncio.run(main(parser().parse_args()))
    except (HostError, ValueError, OSError) as exc:
        print(f"Host error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
    except Exception as exc:
        print(
            f"MCP connection failed ({type(exc).__name__}). Check the server command and retry.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    entrypoint()
