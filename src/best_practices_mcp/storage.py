"""Optional project-keyed storage with atomic visibility and process-local guards.

Separate processes and external editors are not coordinated. Cancellation can make
an update's outcome uncertain to its caller; read the draft rather than retrying.
"""

import asyncio
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import anyio

from best_practices_mcp import documents
from best_practices_mcp.documents import parse_document, serialize_document
from best_practices_mcp.drafts import (
    build_draft,
    check_identity,
    normalize_draft,
    structural_issues,
)
from best_practices_mcp.errors import DomainError
from best_practices_mcp.sdk_adapter import tool_result


def _absolute_directory(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("The draft data directory must be an absolute path.")
    try:
        resolved = path.resolve()
        if resolved.exists() and not resolved.is_dir():
            raise ValueError("The draft data directory must be a directory.")
        return resolved
    except (OSError, RuntimeError) as exc:
        raise ValueError("The draft data directory could not be resolved.") from exc


def resolve_data_root(
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve platform/override configuration once, without creating storage."""
    env = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else home
    if "BESTPRACTICES_DATA_DIR" in env:
        return _absolute_directory(Path(env["BESTPRACTICES_DATA_DIR"]))
    if platform == "darwin":
        root = home / "Library" / "Application Support"
    elif platform == "win32":
        value = env.get("LOCALAPPDATA", "")
        if not value:
            raise ValueError("LOCALAPPDATA is required for the default draft data directory.")
        root = Path(value)
    else:
        data_home = Path(env.get("XDG_DATA_HOME", ""))
        root = data_home if data_home.is_absolute() else home / ".local" / "share"
    return _absolute_directory(root / "bestpractices-mcp")


def _storage_error(code: str, project_id: int) -> DomainError:
    reading = code == "draft_read_failed"
    return DomainError(
        code,
        "The stored draft could not be read."
        if reading
        else "The stored draft could not be written.",
        details={"project_id": project_id},
        recovery=(
            "Check the configured storage path, permissions, and regular-file layout. "
            "After an uncertain update, read the draft before deciding on another patch."
        ),
    )


def _existing(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _require_kind(path: Path, *, directory: bool) -> os.stat_result | None:
    info = _existing(path)
    if info is None:
        return None
    correct = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    # Windows junctions can have directory mode despite redirecting elsewhere.
    # An explicitly selected root is resolved first; managed paths cannot redirect.
    reparse_tag: int = getattr(info, "st_reparse_tag", 0)
    if not correct or reparse_tag:
        raise OSError("Unsafe storage path type.")
    return info


def _storage_identity(project_id: int, draft: dict[str, Any]) -> dict[str, Any]:
    identity = check_identity(project_id, draft)
    return {**identity, "association": "storage_key"}


class DraftStore:
    """Complete reads and guarded patches; only update creates directories/files."""

    def __init__(self, root: Path) -> None:
        self.root = _absolute_directory(Path(root))
        self._guards: dict[int, asyncio.Lock] = {}

    def location(self, project_id: int) -> Path:
        """Compute the canonical destination without filesystem mutation."""
        check_identity(project_id, {})
        return self.root / "projects" / str(project_id) / ".bestpractices.json"

    def _check_layout(self, path: Path) -> os.stat_result | None:
        _require_kind(self.root, directory=True)
        _require_kind(path.parent.parent, directory=True)
        _require_kind(path.parent, directory=True)
        return _require_kind(path, directory=False)

    def _stored_projects(self) -> list[int]:
        projects = self.root / "projects"
        try:
            if _require_kind(projects, directory=True) is None:
                return []
            names = os.listdir(projects)
        except OSError:
            return []
        found = []
        for name in names:
            # Only the canonical decimal directory that location() would use.
            if not re.fullmatch(r"[1-9][0-9]{0,17}", name):
                continue
            try:
                if self._check_layout(self.location(int(name))) is not None:
                    found.append(int(name))
            except OSError:
                continue
        return sorted(found)

    async def project_ids(self) -> list[int]:
        """List projects that have a draft file, without reading or creating anything."""
        return await asyncio.to_thread(self._stored_projects)

    def _load(self, project_id: int) -> dict[str, Any] | None:
        path = self.location(project_id)
        try:
            if self._check_layout(path) is None:
                return None
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            with os.fdopen(os.open(path, flags), "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise OSError("Stored draft is not a regular file.")
                raw = stream.read(documents.DOCUMENT_LIMIT_BYTES + 1)
        except OSError as exc:
            raise _storage_error("draft_read_failed", project_id) from exc
        draft = normalize_draft(parse_document(raw))
        _storage_identity(project_id, draft)
        return draft

    def _read_payload(self, project_id: int, draft: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "project_id": project_id,
            "draft": draft,
            "location": str(self.location(project_id)),
            "issues": structural_issues(draft),
            "serialized_size_bytes": len(serialize_document(draft)),
            "identity": _storage_identity(project_id, draft),
        }

    async def read(self, project_id: int) -> dict[str, Any]:
        """Return the whole normalized document, including diagnostic-only values."""
        draft = await asyncio.to_thread(self._load, project_id)
        if draft is None:
            raise DomainError(
                "draft_not_found",
                "No draft is stored for this project.",
                details={"project_id": project_id},
                recovery="Initialize it with update_draft, or supply an explicit draft document.",
            )
        result = self._read_payload(project_id, draft)
        tool_result("read_draft", result)
        return result

    def _prepare_update(
        self, project_id: int, source: dict[str, Any] | None, patch: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        original = {} if source is None else source
        # Source identity is checked before a patch can remove provenance.
        _storage_identity(project_id, original)
        built = build_draft(original, patch)
        candidate = built["draft"]
        prospective_read = self._read_payload(project_id, candidate)
        result = {
            "schema_version": 1,
            "project_id": project_id,
            "applied_patch": patch,
            "created": source is None,
            "location": prospective_read["location"],
            "issues": built["issues"],
            "serialized_size_bytes": built["serialized_size_bytes"],
            "identity": prospective_read["identity"],
        }
        # Actual SDK wire envelopes include diagnostics, location and JSON text fallback.
        tool_result("read_draft", prospective_read)
        tool_result("update_draft", result)
        return candidate, result

    def _create_directories(self, path: Path) -> None:
        self._check_layout(path)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        for directory in (path.parent.parent, path.parent):
            directory.mkdir(mode=0o700, exist_ok=True)
            _require_kind(directory, directory=True)

    def _atomic_replace(self, project_id: int, raw: bytes) -> None:
        path = self.location(project_id)
        temporary = None
        try:
            self._create_directories(path)
            existing = self._check_layout(path)
            if sys.platform == "win32" and existing is not None:
                if not existing.st_mode & stat.S_IWRITE:
                    # Windows cannot replace a read-only destination. Reject before
                    # creating a read-only temporary file that cannot be unlinked.
                    raise PermissionError("Stored draft is read-only.")
            mode = 0o600 if existing is None else stat.S_IMODE(existing.st_mode)
            fd, name = tempfile.mkstemp(prefix=".bestpractices-", suffix=".tmp", dir=path.parent)
            temporary = Path(name)
            with os.fdopen(fd, "wb") as stream:
                if hasattr(os, "fchmod"):
                    os.fchmod(stream.fileno(), mode)
                else:
                    os.chmod(temporary, mode)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            self._check_layout(path)
            os.replace(temporary, path)
            temporary = None  # Commit succeeded; no cleanup syscall may fail afterward.
        except OSError as exc:
            raise _storage_error("draft_write_failed", project_id) from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as exc:
                    raise _storage_error("draft_write_failed", project_id) from exc

    async def _finish_replace(self, project_id: int, raw: bytes) -> None:
        """Keep the guard until bounded replacement/cleanup finishes despite cancellation."""
        operation = asyncio.create_task(asyncio.to_thread(self._atomic_replace, project_id, raw))
        cancelled = False
        # The SDK uses AnyIO cancellation scopes; shield level-triggered cancellation
        # as well as direct asyncio Task.cancel() calls.
        with anyio.CancelScope(shield=True):
            while not operation.done():
                try:
                    await asyncio.shield(operation)
                except asyncio.CancelledError:
                    cancelled = True
        # Retrieve worker exceptions even when the caller was cancelled.
        operation.result()
        if cancelled:
            raise asyncio.CancelledError

    async def update(self, project_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        """Apply a patch once; never retry a failed or uncertain mutation."""
        self.location(project_id)
        patch = normalize_draft(changes)
        guard = self._guards.setdefault(project_id, asyncio.Lock())
        async with guard:
            source = await asyncio.to_thread(self._load, project_id)
            candidate, result = self._prepare_update(project_id, source, patch)
            if source is None or candidate != source:
                await self._finish_replace(project_id, serialize_document(candidate))
            return result
