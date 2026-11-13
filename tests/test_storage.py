"""STORE fixtures use only temporary roots and controlled failure/concurrency barriers."""

import asyncio
import json
import os
import stat
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from best_practices_mcp import documents, sdk_adapter, storage
from best_practices_mcp.criteria import field_aliases
from best_practices_mcp.documents import serialize_document
from best_practices_mcp.errors import DomainError
from best_practices_mcp.sdk_adapter import result_bytes, tool_result
from best_practices_mcp.storage import DraftStore, resolve_data_root


def run(coro):
    return asyncio.run(coro)


def seed(store, document, project_id=123):
    path = store.location(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialize_document(document))
    return path


def assert_error(code, callable):
    with pytest.raises(DomainError) as exc:
        callable()
    assert exc.value.code == code


@pytest.mark.parametrize(
    ("platform", "env", "relative"),
    [
        ("darwin", {}, "Library/Application Support/bestpractices-mcp"),
        ("linux", {}, ".local/share/bestpractices-mcp"),
        ("linux", {"XDG_DATA_HOME": "relative"}, ".local/share/bestpractices-mcp"),
        ("linux", {"XDG_DATA_HOME": ""}, ".local/share/bestpractices-mcp"),
    ],
)
def test_default_roots_resolve_without_creation(tmp_path, platform, env, relative):
    assert resolve_data_root(platform=platform, environ=env, home=tmp_path) == tmp_path / relative
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("platform", "variable"), [("linux", "XDG_DATA_HOME"), ("win32", "LOCALAPPDATA")]
)
def test_absolute_platform_environment_roots(tmp_path, platform, variable):
    actual = resolve_data_root(platform=platform, environ={variable: str(tmp_path / "data")})
    assert actual == tmp_path / "data" / "bestpractices-mcp"
    assert not actual.exists()


@pytest.mark.parametrize("value", ["", "relative", "~/drafts"])
def test_override_rejects_empty_relative_and_tilde(tmp_path, value):
    with pytest.raises(ValueError):
        resolve_data_root(environ={"BESTPRACTICES_DATA_DIR": value}, home=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_root_file_is_configuration_error_and_root_symlink_is_resolved(tmp_path):
    target = tmp_path / "target"
    target.write_text("untouched")
    with pytest.raises(ValueError):
        resolve_data_root(environ={"BESTPRACTICES_DATA_DIR": str(target)})
    target.unlink()
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    assert resolve_data_root(environ={"BESTPRACTICES_DATA_DIR": str(link)}) == target
    assert DraftStore(link).root == target


@pytest.mark.parametrize("env", [{}, {"LOCALAPPDATA": ""}, {"LOCALAPPDATA": "relative"}])
def test_invalid_windows_default_fails_without_guessing(env):
    with pytest.raises(ValueError):
        resolve_data_root(platform="win32", environ=env)


@pytest.mark.parametrize("failure", [OSError, RuntimeError])
def test_unresolvable_root_is_configuration_error(tmp_path, monkeypatch, failure):
    def fail_resolve(path):
        raise failure("private filesystem detail")

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    with pytest.raises(ValueError, match="could not be resolved") as exc:
        resolve_data_root(environ={"BESTPRACTICES_DATA_DIR": str(tmp_path / "drafts")})
    assert isinstance(exc.value.__cause__, failure)
    assert "private" not in str(exc.value)
    assert list(tmp_path.iterdir()) == []


def test_missing_read_no_creation_first_empty_update_and_restart(tmp_path):
    root = tmp_path / "new"
    store = DraftStore(root)
    assert_error("draft_not_found", lambda: run(store.read(123)))
    assert not root.exists()
    created = run(store.update(123, {}))
    assert created["created"] is True
    assert created["applied_patch"] == {}
    assert created["identity"]["association"] == "storage_key"
    path = root / "projects" / "123" / ".bestpractices.json"
    assert created["location"] == str(path)
    assert path.read_bytes() == b"{}\n"
    before = path.stat().st_mtime_ns
    assert run(store.update(123, {}))["created"] is False
    assert path.stat().st_mtime_ns == before
    assert run(DraftStore(root).read(123))["draft"] == {}


def test_complete_read_preserves_unknown_and_invalid_values_with_diagnostics(tmp_path):
    store = DraftStore(tmp_path)
    original = {"extra": {"a": [True, None]}, "name": 4, "description_good_status": "invalid"}
    seed(store, original)
    result = run(store.read(123))
    assert result["draft"] == original
    assert [x["code"] for x in result["issues"]] == [
        "invalid_status",
        "unknown_field",
        "invalid_type",
    ]
    assert result["serialized_size_bytes"] == len(serialize_document(original))
    assert result["identity"] == {
        "association": "storage_key",
        "id_check": "absent",
        "repo_check": "not_checked",
    }
    assert json.loads(tool_result("read_draft", result).content[0].text)["draft"] == original


def test_patch_repair_aliases_unknown_preservation_and_removals(tmp_path):
    store = DraftStore(tmp_path)
    alias, canonical = next(iter(field_aliases().items()))
    value = "Met" if canonical.endswith("_status") else "explanation"
    seed(store, {"extra": {"a": [True, None]}, "name": False, alias: value})
    result = run(store.update(123, {"name": "fixed", alias: None}))
    assert result["applied_patch"] == {"name": "fixed", canonical: None}
    assert "draft" not in result
    assert run(store.read(123))["draft"] == {"name": "fixed", "extra": {"a": [True, None]}}
    run(store.update(123, {"extra": None}))
    assert run(store.read(123))["draft"] == {"name": "fixed"}


@pytest.mark.parametrize(
    "document,code",
    [({"id": 456}, "project_mismatch"), ({"id": None}, "project_identity_unresolved")],
)
def test_source_identity_cannot_be_erased_to_repair_wrong_project(tmp_path, document, code):
    store = DraftStore(tmp_path)
    path = seed(store, document)
    before = path.read_bytes()
    assert_error(code, lambda: run(store.read(123)))
    assert_error(code, lambda: run(store.update(123, {"id": None, "name": "new"})))
    assert path.read_bytes() == before


@pytest.mark.parametrize("raw", [b"{", b"[]", b'{"name":"a","name":"b"}', b'{"x":NaN}'])
def test_invalid_existing_json_never_becomes_empty(tmp_path, raw):
    store = DraftStore(tmp_path)
    path = seed(store, {})
    path.write_bytes(raw)
    assert_error("invalid_document", lambda: run(store.update(123, {"name": "new"})))
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "changes", [{"unknown": "no"}, {"name": False}, {"description_good_status": "met"}]
)
def test_invalid_patch_preserves_file_and_absent_root(tmp_path, changes):
    store = DraftStore(tmp_path / "existing")
    path = seed(store, {"name": "old"})
    before = path.read_bytes()
    assert_error("invalid_field", lambda: run(store.update(123, changes)))
    assert path.read_bytes() == before
    other = DraftStore(tmp_path / "absent")
    assert_error("invalid_field", lambda: run(other.update(123, changes)))
    assert not other.root.exists()


def test_oversized_input_and_combined_output_are_never_truncated(tmp_path, monkeypatch):
    store = DraftStore(tmp_path)
    path = seed(store, {"name": "a" * 35})
    before = path.read_bytes()
    monkeypatch.setattr(documents, "DOCUMENT_LIMIT_BYTES", 60)
    assert_error("document_too_large", lambda: run(store.update(123, {"description": "b" * 35})))
    assert path.read_bytes() == before
    path.write_bytes(b" " * 61)
    assert_error("document_too_large", lambda: run(store.read(123)))


def test_actual_read_envelope_boundary_includes_unicode_diagnostics_and_long_path(
    tmp_path, monkeypatch
):
    store = DraftStore(tmp_path / ("long" * 30))
    original = {"unknown": {"雪": ['\\"\n' * 20]}, "name": "before"}
    path = seed(store, original)
    candidate = {**original, "name": 'after 雪\\"'}
    payload = store._read_payload(123, candidate)
    limit = len(result_bytes(tool_result("read_draft", payload)))
    before = path.read_bytes()
    monkeypatch.setattr(sdk_adapter, "RESPONSE_LIMIT_BYTES", limit - 1)
    assert_error("response_too_large", lambda: run(store.update(123, {"name": candidate["name"]})))
    assert path.read_bytes() == before
    monkeypatch.setattr(sdk_adapter, "RESPONSE_LIMIT_BYTES", limit)
    run(store.update(123, {"name": candidate["name"]}))
    read = run(store.read(123))
    assert read["draft"] == candidate
    assert len(result_bytes(tool_result("read_draft", read))) == limit


def test_noop_still_enforces_prospective_full_read_size(tmp_path, monkeypatch):
    store = DraftStore(tmp_path)
    path = seed(store, {"unknown": list(range(100))})
    before = path.read_bytes()
    size = len(
        result_bytes(
            tool_result("read_draft", store._read_payload(123, {"unknown": list(range(100))}))
        )
    )
    monkeypatch.setattr(sdk_adapter, "RESPONSE_LIMIT_BYTES", size - 1)
    assert_error("response_too_large", lambda: run(store.update(123, {})))
    assert path.read_bytes() == before


def test_update_envelope_is_checked_before_any_commit(tmp_path, monkeypatch):
    store = DraftStore(tmp_path)
    original = {"name": "old"}
    path = seed(store, original)
    changes = {"unrecognized-removal-" + str(i): None for i in range(100)}
    changes["name"] = "new"
    before = path.read_bytes()
    read_size = len(
        result_bytes(tool_result("read_draft", store._read_payload(123, {"name": "new"})))
    )
    monkeypatch.setattr(sdk_adapter, "RESPONSE_LIMIT_BYTES", read_size + 100)
    assert_error("response_too_large", lambda: run(store.update(123, changes)))
    assert path.read_bytes() == before


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits differ from Windows ACL semantics")
def test_new_owner_only_and_existing_permissions_preserved(tmp_path):
    store = DraftStore(tmp_path / "new")
    run(store.update(123, {"name": "one"}))
    path = store.location(123)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.chmod(0o640)
    run(store.update(123, {"name": "two"}))
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


@pytest.mark.parametrize("part", ["projects", "project", "draft"])
def test_managed_symlinks_rejected_without_touching_target(tmp_path, part):
    target = tmp_path / "outside"
    target.mkdir()
    sentinel = target / "sentinel"
    sentinel.write_text("untouched")
    store = DraftStore(tmp_path / "root")
    store.root.mkdir()
    path = store.location(123)
    if part == "projects":
        (store.root / "projects").symlink_to(target, target_is_directory=True)
    elif part == "project":
        (store.root / "projects").mkdir()
        path.parent.symlink_to(target, target_is_directory=True)
    else:
        path.parent.mkdir(parents=True)
        path.symlink_to(sentinel)
    assert_error("draft_read_failed", lambda: run(store.read(123)))
    assert_error("draft_read_failed", lambda: run(store.update(123, {"name": "new"})))
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    assert list(target.iterdir()) == [sentinel]


def test_nonregular_draft_is_rejected(tmp_path):
    store = DraftStore(tmp_path)
    path = store.location(123)
    path.mkdir(parents=True)
    assert_error("draft_read_failed", lambda: run(store.read(123)))
    assert_error("draft_read_failed", lambda: run(store.update(123, {})))


def test_permission_failure_mapped_without_echoing_content(tmp_path, monkeypatch):
    store = DraftStore(tmp_path)
    path = seed(store, {"description": "private"})
    original_open = storage.os.open

    def denied(target, *args, **kwargs):
        if Path(target) == path:
            raise PermissionError("private system detail")
        return original_open(target, *args, **kwargs)

    monkeypatch.setattr(storage.os, "open", denied)
    with pytest.raises(DomainError) as exc:
        run(store.read(123))
    assert exc.value.code == "draft_read_failed"
    assert "private" not in str(exc.value.to_payload())


def test_opened_nonregular_file_is_rejected_and_closed(tmp_path, monkeypatch):
    store = DraftStore(tmp_path)
    path = seed(store, {"name": "before"})
    before = path.read_bytes()
    descriptors = []
    original_fstat = storage.os.fstat
    draft_inode = path.stat().st_ino

    def nonregular_info(fd):
        info = original_fstat(fd)
        if info.st_ino == draft_inode:
            descriptors.append(fd)
            return os.stat_result((stat.S_IFIFO, *tuple(info)[1:]))
        return info

    # Model a path changing type between layout inspection and descriptor validation.
    monkeypatch.setattr(storage.os, "fstat", nonregular_info)
    with pytest.raises(DomainError) as exc:
        run(store.read(123))
    assert exc.value.code == "draft_read_failed"
    assert str(exc.value.__cause__) == "Stored draft is not a regular file."
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        original_fstat(descriptors[0])
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_pre_replace_failure_preserves_old_file_and_cleans_temp(tmp_path, monkeypatch, failure):
    store = DraftStore(tmp_path)
    path = seed(store, {"name": "before"})
    before = path.read_bytes()

    def fail(*args):
        raise PermissionError("injected")

    monkeypatch.setattr(storage.os, failure, fail)
    assert_error("draft_write_failed", lambda: run(store.update(123, {"name": "after"})))
    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


def test_failed_first_creation_leaves_no_draft_or_temp(tmp_path, monkeypatch):
    store = DraftStore(tmp_path / "new")

    def fail(*args):
        raise OSError("injected")

    monkeypatch.setattr(storage.os, "replace", fail)
    assert_error("draft_write_failed", lambda: run(store.update(123, {})))
    assert not store.location(123).exists()
    assert list(store.location(123).parent.iterdir()) == []


def test_failed_cleanup_is_reported_without_changing_destination(tmp_path, monkeypatch):
    store = DraftStore(tmp_path)
    path = seed(store, {"name": "before"})
    before = path.read_bytes()
    cleanup_attempts = []
    original_unlink = Path.unlink

    def fail_sync(fd):
        raise OSError("injected sync failure")

    def fail_cleanup(target, **kwargs):
        cleanup_attempts.append(target)
        raise PermissionError("private cleanup detail")

    monkeypatch.setattr(storage.os, "fsync", fail_sync)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    try:
        with pytest.raises(DomainError) as exc:
            run(store.update(123, {"name": "after"}))
        assert exc.value.code == "draft_write_failed"
        assert isinstance(exc.value.__cause__, PermissionError)
        assert "private" not in str(exc.value.to_payload())
        assert path.read_bytes() == before
        assert len(cleanup_attempts) == 1
        temporary = cleanup_attempts[0]
        assert temporary.parent == path.parent
        assert temporary.name.startswith(".bestpractices-")
        assert temporary.suffix == ".tmp"
        assert temporary.exists()
    finally:
        for temporary in cleanup_attempts:
            original_unlink(temporary, missing_ok=True)


async def wait_thread_event(event):
    assert await asyncio.to_thread(event.wait, 5), "controlled worker did not reach barrier"


@pytest.mark.parametrize("existing", [False, True])
def test_overlapping_disjoint_patches_and_first_creation_preserve_both(tmp_path, existing):
    store = DraftStore(tmp_path)
    if existing:
        seed(store, {"name": "baseline"})
    entered, release = threading.Event(), threading.Event()
    original = store._atomic_replace

    def delayed(project_id, raw):
        entered.set()
        assert release.wait(5)
        original(project_id, raw)

    store._atomic_replace = delayed

    async def exercise():
        first = asyncio.create_task(store.update(123, {"name": "one"}))
        await wait_thread_event(entered)
        second = asyncio.create_task(store.update(123, {"description": "two"}))
        await asyncio.sleep(0)
        assert not second.done()
        release.set()
        results = await asyncio.gather(first, second)
        assert sum(x["created"] for x in results) == int(not existing)
        assert (await store.read(123))["draft"] == {"name": "one", "description": "two"}

    run(exercise())


def test_same_field_serial_outcome_and_other_projects_are_independent(tmp_path):
    store = DraftStore(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = store._atomic_replace

    def delayed(project_id, raw):
        if project_id == 123:
            entered.set()
            assert release.wait(5)
        original(project_id, raw)

    store._atomic_replace = delayed

    async def exercise():
        first = asyncio.create_task(store.update(123, {"name": "one"}))
        await wait_thread_event(entered)
        second = asyncio.create_task(store.update(123, {"name": "two"}))
        independent = await asyncio.wait_for(store.update(456, {"name": "other"}), 2)
        assert independent["created"]
        assert not first.done() and not second.done()
        release.set()
        await asyncio.gather(first, second)
        assert (await store.read(123))["draft"] == {"name": "two"}
        assert (await store.read(456))["draft"] == {"name": "other"}

    run(exercise())


def test_read_during_replacement_sees_complete_before_then_after(tmp_path, monkeypatch):
    store = DraftStore(tmp_path)
    seed(store, {"description": "a" * 10000})
    entered, release = threading.Event(), threading.Event()
    original = storage.os.replace

    def delayed(source, target):
        entered.set()
        assert release.wait(5)
        original(source, target)

    monkeypatch.setattr(storage.os, "replace", delayed)

    async def exercise():
        writer = asyncio.create_task(store.update(123, {"description": "b" * 20000}))
        await wait_thread_event(entered)
        assert (await store.read(123))["draft"] == {"description": "a" * 10000}
        release.set()
        await writer
        assert (await store.read(123))["draft"] == {"description": "b" * 20000}

    run(exercise())


def test_cancellation_during_replace_keeps_guard_until_worker_finishes(tmp_path, monkeypatch):
    store = DraftStore(tmp_path)
    seed(store, {"name": "before"})
    entered, release = threading.Event(), threading.Event()
    original = storage.os.replace
    replacements = []

    def delayed(source, target):
        entered.set()
        assert release.wait(5)
        original(source, target)
        replacements.append(str(target))

    monkeypatch.setattr(storage.os, "replace", delayed)

    async def exercise():
        writer = asyncio.create_task(store.update(123, {"name": "after"}))
        await wait_thread_event(entered)
        writer.cancel()
        following = asyncio.create_task(store.update(123, {"description": "following"}))
        await asyncio.sleep(0.01)
        assert not writer.done() and not following.done()
        writer.cancel()  # repeated cancellation must still not abandon replacement/cleanup
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await writer
        await following
        assert (await store.read(123))["draft"] == {"name": "after", "description": "following"}

    run(exercise())
    assert len(replacements) == 2
    assert list(store.location(123).parent.iterdir()) == [store.location(123)]


def test_cancelled_waiter_does_not_write_or_strand_guard(tmp_path):
    store = DraftStore(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = store._atomic_replace

    def delayed(project_id, raw):
        entered.set()
        assert release.wait(5)
        original(project_id, raw)

    store._atomic_replace = delayed

    async def exercise():
        first = asyncio.create_task(store.update(123, {"name": "first"}))
        await wait_thread_event(entered)
        waiter = asyncio.create_task(store.update(123, {"name": "cancelled"}))
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        release.set()
        await first
        await store.update(123, {"description": "subsequent"})
        assert (await store.read(123))["draft"] == {"name": "first", "description": "subsequent"}

    run(exercise())


def test_sdk_style_cancel_scope_cannot_release_guard_before_replace(tmp_path, monkeypatch):
    import anyio

    store = DraftStore(tmp_path)
    seed(store, {"name": "before"})
    entered, release = threading.Event(), threading.Event()
    original = storage.os.replace

    def delayed(source, target):
        entered.set()
        assert release.wait(5)
        original(source, target)

    monkeypatch.setattr(storage.os, "replace", delayed)

    async def exercise():
        scope = anyio.CancelScope()
        finished = asyncio.Event()

        async def scoped_writer():
            with scope:
                await store.update(123, {"name": "after"})
            finished.set()

        writer = asyncio.create_task(scoped_writer())
        await wait_thread_event(entered)
        scope.cancel()
        following = asyncio.create_task(store.update(123, {"description": "following"}))
        await asyncio.sleep(0.01)
        assert not finished.is_set() and not following.done()
        release.set()
        await asyncio.gather(writer, following)
        assert (await store.read(123))["draft"] == {"name": "after", "description": "following"}

    run(exercise())


def test_successful_commit_performs_no_cleanup_syscall(tmp_path, monkeypatch):
    store = DraftStore(tmp_path)
    seed(store, {"name": "before"})

    def fail_unlink(*args, **kwargs):
        raise PermissionError("cleanup should not run after successful replace")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    result = run(store.update(123, {"name": "after"}))
    assert result["created"] is False
    assert run(store.read(123))["draft"] == {"name": "after"}


def test_windows_readonly_destination_rejected_before_temp_creation(tmp_path, monkeypatch):
    store = DraftStore(tmp_path)
    path = seed(store, {"name": "before"})
    before = path.read_bytes()
    path.chmod(stat.S_IREAD)
    monkeypatch.setattr(storage.sys, "platform", "win32")
    try:
        assert_error("draft_write_failed", lambda: run(store.update(123, {"name": "after"})))
        assert path.read_bytes() == before
        assert not path.stat().st_mode & stat.S_IWRITE
        assert list(path.parent.iterdir()) == [path]
    finally:
        path.chmod(stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.parametrize("existing", [False, True])
def test_windows_writable_destination_and_path_chmod_fallback(tmp_path, monkeypatch, existing):
    store = DraftStore(tmp_path)
    path = store.location(123)
    expected_mode = 0o600
    if existing:
        seed(store, {"name": "before"})
        expected_mode = stat.S_IMODE(path.stat().st_mode)
    original_chmod = storage.os.chmod
    chmod_calls = []

    def record_chmod(target, mode):
        chmod_calls.append((target, mode))
        original_chmod(target, mode)

    monkeypatch.setattr(storage, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.delattr(storage.os, "fchmod", raising=False)
    monkeypatch.setattr(storage.os, "chmod", record_chmod)
    result = run(store.update(123, {"name": "after"}))
    assert result["created"] is (not existing)
    assert run(store.read(123))["draft"] == {"name": "after"}
    assert len(chmod_calls) == 1
    temporary, mode = chmod_calls[0]
    assert temporary.parent == path.parent
    assert temporary.suffix == ".tmp"
    assert mode == expected_mode
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("part", ["projects", "project", "draft"])
def test_managed_windows_reparse_points_rejected(tmp_path, monkeypatch, part):
    store = DraftStore(tmp_path / "root")
    path = seed(store, {"name": "before"})
    before = path.read_bytes()
    redirected = {"projects": path.parent.parent, "project": path.parent, "draft": path}[part]
    existing = storage._existing

    def reparse_info(candidate):
        info = existing(candidate)
        if candidate == redirected:
            return SimpleNamespace(
                st_mode=info.st_mode,
                st_reparse_tag=0xA0000003,  # Windows IO_REPARSE_TAG_MOUNT_POINT
            )
        return info

    monkeypatch.setattr(storage, "_existing", reparse_info)
    assert_error("draft_read_failed", lambda: run(store.read(123)))
    assert_error("draft_read_failed", lambda: run(store.update(123, {"name": "after"})))
    assert path.read_bytes() == before


@pytest.mark.skipif(os.name != "nt", reason="Native Windows directory-junction semantics")
def test_native_windows_junction_rejected_but_explicit_root_resolves(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    root_alias = tmp_path / "root-alias"
    subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(root_alias), str(target)],
        check=True,
        capture_output=True,
        timeout=10,
    )
    store = DraftStore(root_alias)
    assert store.root == target.resolve()
    run(store.update(123, {"name": "root is allowed"}))
    assert run(store.read(123))["draft"] == {"name": "root is allowed"}

    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel"
    sentinel.write_bytes(b"untouched")
    blocked = DraftStore(tmp_path / "blocked")
    blocked.root.mkdir()
    junction = blocked.root / "projects"
    subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(external)],
        check=True,
        capture_output=True,
        timeout=10,
    )
    assert_error("draft_read_failed", lambda: run(blocked.read(123)))
    assert_error("draft_read_failed", lambda: run(blocked.update(123, {"name": "denied"})))
    assert list(external.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"untouched"
