"""Upstream drift detection and the single-issue lifecycle, without network access."""

import hashlib
import io
import json
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from scripts import check_upstream as check

BASE = "a" * 40
PRODUCTION = "b" * 40
REPOSITORY = "reponomics/best-practices-mcp"


@pytest.fixture
def source(tmp_path):
    hashes = {}
    for name in check.INPUTS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"criterion: original wording\n")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"revision": BASE, "repository": check.UPSTREAM_URL, "files": hashes}
    (tmp_path / "source.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(source):
    result = Mock(spec=check.GitHub)
    result.api.return_value = {
        "ref": "refs/heads/production",
        "object": {"type": "commit", "sha": PRODUCTION},
    }
    result.file_hash.side_effect = lambda sha, name: hashlib.sha256(
        (source / name).read_bytes()
    ).hexdigest()
    return result


def make_report(*, drift=True):
    hashes = dict.fromkeys(check.INPUTS, "c" * 64)
    remote = {**hashes, "config/locales/en.yml": "d" * 64} if drift else hashes.copy()
    return check.Report(BASE, PRODUCTION, hashes, remote)


def issue_for(report, *, state="open"):
    return {
        "number": 42,
        "title": check.ISSUE_TITLE,
        "body": check.report_body(report),
        "state": state,
    }


def test_changed_commit_with_identical_files_is_not_drift(source, client):
    report = check.check_upstream(client, source)
    assert report.changed == []
    assert report.bundled_revision != report.production_revision
    client.api.assert_called_once_with(f"/repos/{check.UPSTREAM}/git/ref/heads/production")
    assert [call.args for call in client.file_hash.call_args_list] == [
        (PRODUCTION, name) for name in check.INPUTS
    ]


@pytest.mark.parametrize("name", check.INPUTS)
@pytest.mark.parametrize("content", [b"criterion: original wording \n", None])
def test_each_input_detects_whitespace_changes_and_deletion(source, client, name, content):
    original = client.file_hash.side_effect
    changed_hash = hashlib.sha256(content).hexdigest() if content is not None else None
    client.file_hash.side_effect = lambda sha, path: (
        changed_hash if path == name else original(sha, path)
    )
    report = check.check_upstream(client, source)
    assert report.changed == [name]
    body = check.report_body(report)
    assert f"/blob/{BASE}/{name}" in body
    assert ("Missing (HTTP 404)" if content is None else f"/blob/{PRODUCTION}/{name}") in body


@pytest.mark.parametrize("failure", ["corrupt", "missing", "repository", "revision"])
def test_invalid_local_baseline_fails_before_network(source, client, failure):
    if failure == "corrupt":
        (source / check.INPUTS[0]).write_bytes(b"changed locally")
    elif failure == "missing":
        (source / check.INPUTS[0]).unlink()
    else:
        manifest = json.loads((source / "source.json").read_text())
        manifest[failure] = "unexpected"
        (source / "source.json").write_text(json.dumps(manifest))
    with pytest.raises((ValueError, OSError)):
        check.check_upstream(client, source)
    client.api.assert_not_called()


@pytest.mark.parametrize(
    "ref",
    [
        {},
        {"ref": "refs/heads/main", "object": {"type": "commit", "sha": PRODUCTION}},
        {"ref": "refs/heads/production", "object": {"type": "tag", "sha": PRODUCTION}},
        {"ref": "refs/heads/production", "object": {"type": "commit", "sha": "main"}},
    ],
)
def test_malformed_ref_cannot_produce_a_clean_report(source, client, ref):
    client.api.return_value = ref
    with pytest.raises((ValueError, KeyError)):
        check.check_upstream(client, source)
    client.file_hash.assert_not_called()


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_only_raw_file_404_is_a_deletion(monkeypatch, status):
    client = check.GitHub()
    request = Mock(side_effect=HTTPError("https://example.com", status, "failure", {}, None))
    monkeypatch.setattr(client, "request", request)
    if status == 404:
        assert client.file_hash(PRODUCTION, check.INPUTS[0]) is None
    else:
        with pytest.raises(HTTPError):
            client.file_hash(PRODUCTION, check.INPUTS[0])


@pytest.mark.parametrize("failure", [URLError("offline"), TimeoutError(), ValueError("bad JSON")])
def test_failed_check_never_updates_issue(monkeypatch, capsys, failure):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", REPOSITORY)
    monkeypatch.setattr(check, "check_upstream", Mock(side_effect=failure))
    update = Mock()
    monkeypatch.setattr(check, "sync_issue", update)
    assert check.main(["--update-issue"]) == 1
    update.assert_not_called()
    assert "Upstream check failed" in capsys.readouterr().err


def test_local_check_never_updates_issue_even_when_drift_detected(monkeypatch):
    monkeypatch.setattr(check, "check_upstream", Mock(return_value=make_report()))
    update = Mock()
    monkeypatch.setattr(check, "sync_issue", update)
    assert check.main([]) == 0
    update.assert_not_called()


def test_issue_mode_requires_explicit_credentials_before_network(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    probe = Mock()
    monkeypatch.setattr(check, "check_upstream", probe)
    assert check.main(["--update-issue"]) == 1
    probe.assert_not_called()


def test_clean_check_without_tracker_performs_no_write():
    client = Mock(spec=check.GitHub)
    client.api.return_value = []
    check.sync_issue(client, REPOSITORY, make_report(drift=False))
    assert len(client.api.call_args_list) == 1


def test_drift_creates_tracker_and_identical_rerun_does_not_write():
    client = Mock(spec=check.GitHub)
    client.api.return_value = []
    report = make_report()
    check.sync_issue(client, REPOSITORY, report)
    write = client.api.call_args_list[-1]
    assert write.kwargs["method"] == "POST"
    assert write.kwargs["data"]["body"].startswith(check.ISSUE_MARKER)
    client.reset_mock()
    client.api.return_value = [issue_for(report)]
    check.sync_issue(client, REPOSITORY, report)
    assert len(client.api.call_args_list) == 1


@pytest.mark.parametrize("state", ["open", "closed"])
def test_drift_updates_or_reopens_same_tracker(state):
    client = Mock(spec=check.GitHub)
    client.api.return_value = [issue_for(make_report(drift=False), state=state)]
    check.sync_issue(client, REPOSITORY, make_report())
    write = client.api.call_args_list[-1]
    assert write.args == (f"/repos/{REPOSITORY}/issues/42",)
    assert write.kwargs["method"] == "PATCH"
    assert write.kwargs["data"]["state"] == "open"


def test_no_drift_closes_tracker_once_without_comments():
    client = Mock(spec=check.GitHub)
    client.api.return_value = [issue_for(make_report())]
    report = make_report(drift=False)
    check.sync_issue(client, REPOSITORY, report)
    write = client.api.call_args_list[-1]
    assert write.kwargs["data"]["state"] == "closed"
    assert "match the bundled copies" in write.kwargs["data"]["body"]
    client.reset_mock()
    client.api.return_value = [issue_for(report, state="closed")]
    check.sync_issue(client, REPOSITORY, report)
    assert len(client.api.call_args_list) == 1


def test_finds_closed_tracker_on_later_page_and_excludes_pull_requests():
    client = Mock(spec=check.GitHub)
    issue = issue_for(make_report(), state="closed")
    client.api.side_effect = [
        [{**issue, "pull_request": {}}] + [{"body": "unrelated"}] * 99,
        [issue],
    ]
    assert check.find_tracking_issue(client, REPOSITORY) == issue
    assert "state=all" in client.api.call_args_list[0].args[0]
    assert "page=2" in client.api.call_args_list[1].args[0]


def test_duplicate_trackers_fail_without_another_issue():
    client = Mock(spec=check.GitHub)
    client.api.return_value = [issue_for(make_report()), issue_for(make_report())]
    with pytest.raises(ValueError, match="Multiple"):
        check.sync_issue(client, REPOSITORY, make_report())
    assert len(client.api.call_args_list) == 1


def test_request_paces_calls_and_does_not_send_token_to_raw_host(monkeypatch):
    requests = []

    def respond(request, *, timeout):
        assert timeout == 30
        requests.append(request)
        response = io.BytesIO(b"{}")
        response.headers = {"X-RateLimit-Remaining": "10"}
        return response

    pause = Mock()
    monkeypatch.setattr(check, "urlopen", respond)
    monkeypatch.setattr(check.time, "sleep", pause)
    client = check.GitHub("test-token")
    client.api("/example", data={"body": "test"}, method="POST")
    client.file_hash(PRODUCTION, check.INPUTS[0])
    assert requests[0].get_header("Authorization") == "Bearer test-token"
    assert json.loads(requests[0].data) == {"body": "test"}
    assert requests[1].get_header("Authorization") is None
    assert [call.args for call in pause.call_args_list] == [(0.5,), (0.5,)]


def test_exhausted_rate_limit_is_a_failure(monkeypatch):
    response = io.BytesIO(b"{}")
    response.headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "123"}
    monkeypatch.setattr(check, "urlopen", Mock(return_value=response))
    monkeypatch.setattr(check.time, "sleep", Mock())
    with pytest.raises(RuntimeError, match="rate limit exhausted.*123"):
        check.GitHub().api("/example")
