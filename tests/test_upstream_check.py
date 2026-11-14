"""Upstream source comparison is byte-exact and read-only unless preparation is requested."""

import hashlib
import importlib
import io
import json
import sys
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from scripts import check_upstream as check

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
prepare = importlib.import_module("prepare_upstream")
BASE = "a" * 40
PRODUCTION = "b" * 40


@pytest.fixture
def source(tmp_path):
    hashes = {}
    for name in check.SOURCE_FILES:
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
    result.source_file.side_effect = lambda sha, name: (source / name).read_bytes()
    return result


def test_changed_commit_with_identical_files_is_not_drift(source, client):
    report = check.check_upstream(client, source)
    assert report.changed == []
    assert report.bundled_revision != report.production_revision
    client.api.assert_called_once_with(f"/repos/{check.UPSTREAM}/git/ref/heads/production")
    assert [call.args for call in client.source_file.call_args_list] == [
        (PRODUCTION, name) for name in check.SOURCE_FILES
    ]
    assert "match the bundled copies byte for byte" in check.report_body(report)


@pytest.mark.parametrize("name", check.SOURCE_FILES)
@pytest.mark.parametrize("content", [b"criterion: original wording \n", None])
def test_each_source_detects_whitespace_changes_and_deletion(source, client, name, content):
    original = client.source_file.side_effect
    client.source_file.side_effect = lambda sha, path: (
        content if path == name else original(sha, path)
    )
    report = check.check_upstream(client, source)
    assert report.changed == [name]
    assert report.production_hashes[name] == (
        hashlib.sha256(content).hexdigest() if content is not None else None
    )
    body = check.report_body(report)
    assert f"/blob/{BASE}/{name}" in body
    assert ("Missing (HTTP 404)" if content is None else f"/blob/{PRODUCTION}/{name}") in body


@pytest.mark.parametrize("failure", ["corrupt", "missing", "repository", "revision", "paths"])
def test_invalid_local_baseline_fails_before_network(source, client, failure):
    if failure == "corrupt":
        (source / check.SOURCE_FILES[-1]).write_bytes(b"changed locally")
    elif failure == "missing":
        (source / check.SOURCE_FILES[-1]).unlink()
    else:
        manifest = json.loads((source / "source.json").read_text())
        if failure == "paths":
            manifest["files"]["../unmanaged"] = "c" * 64
        else:
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
    client.source_file.assert_not_called()


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_only_raw_file_404_is_a_deletion(monkeypatch, status):
    client = check.GitHub()
    request = Mock(side_effect=HTTPError("https://example.com", status, "failure", {}, None))
    monkeypatch.setattr(client, "request", request)
    if status == 404:
        assert client.source_file(PRODUCTION, check.INPUTS[0]) is None
    else:
        with pytest.raises(HTTPError):
            client.source_file(PRODUCTION, check.INPUTS[0])


@pytest.mark.parametrize("failure", [URLError("offline"), TimeoutError(), ValueError("bad JSON")])
def test_failed_check_never_prepares_patch(monkeypatch, capsys, failure):
    monkeypatch.setattr(check, "check_upstream", Mock(side_effect=failure))
    update = Mock()
    monkeypatch.setattr(prepare, "prepare_update", update)
    assert check.main(["--prepare-update"]) == 1
    update.assert_not_called()
    assert "Upstream check failed" in capsys.readouterr().err


def test_late_source_fetch_failure_never_prepares_partial_update(source, client, monkeypatch):
    client.source_file.side_effect = [b"first input", b"second input", URLError("offline")]
    monkeypatch.setattr(check, "ROOT", source.parent)
    monkeypatch.setattr(check, "GitHub", Mock(return_value=client))
    baseline = Mock(return_value=(BASE, dict.fromkeys(check.SOURCE_FILES, "c" * 64)))
    monkeypatch.setattr(check, "read_baseline", baseline)
    update = Mock()
    monkeypatch.setattr(prepare, "prepare_update", update)
    assert check.main(["--prepare-update"]) == 1
    update.assert_not_called()


def test_local_check_does_not_prepare_even_when_drift_detected(
    source, client, monkeypatch, tmp_path
):
    client.source_file.side_effect = lambda sha, name: b"new content"
    report = check.check_upstream(client, source)
    monkeypatch.setattr(check, "check_upstream", Mock(return_value=report))
    update = Mock()
    monkeypatch.setattr(prepare, "prepare_update", update)
    output = tmp_path / "reports"
    assert check.main(["--output-dir", str(output)]) == 0
    update.assert_not_called()
    assert not output.exists()


@pytest.mark.parametrize("generation_error", [None, "Upstream schema changed"])
def test_prepare_cli_writes_review_body_and_reports_generation_failure_without_aborting(
    source, client, monkeypatch, tmp_path, generation_error
):
    report = check.check_upstream(client, source)
    monkeypatch.setattr(check, "check_upstream", Mock(return_value=report))
    output = tmp_path / "reports"
    workflow_output = tmp_path / "workflow-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(workflow_output))

    def update(*args):
        output.mkdir()
        (output / "result.json").write_text(json.dumps({"generation_error": generation_error}))
        return "\nPreparation details.\n"

    monkeypatch.setattr(prepare, "prepare_update", update)
    assert check.main(["--prepare-update", "--output-dir", str(output)]) == 0
    body = (output / "pr.md").read_text(encoding="utf-8")
    assert "Preparation details." in body
    assert PRODUCTION in body
    expected = "true" if generation_error is not None else "false"
    assert workflow_output.read_text(encoding="utf-8") == f"generation-failed={expected}\n"


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
    client.api("/example")
    assert client.source_file(PRODUCTION, check.INPUTS[0]) == b"{}"
    assert requests[0].get_header("Authorization") == "Bearer test-token"
    assert requests[1].get_header("Authorization") is None
    assert [call.args for call in pause.call_args_list] == [(0.5,), (0.5,)]


def test_exhausted_rate_limit_is_a_failure(monkeypatch):
    response = io.BytesIO(b"{}")
    response.headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "123"}
    monkeypatch.setattr(check, "urlopen", Mock(return_value=response))
    monkeypatch.setattr(check.time, "sleep", Mock())
    with pytest.raises(RuntimeError, match="rate limit exhausted.*123"):
        check.GitHub().api("/example")


def test_oversized_response_is_rejected(monkeypatch):
    response = io.BytesIO(b"x" * 5_000_001)
    response.headers = {}
    monkeypatch.setattr(check, "urlopen", Mock(return_value=response))
    monkeypatch.setattr(check.time, "sleep", Mock())
    with pytest.raises(ValueError, match="exceeded"):
        check.GitHub().source_file(PRODUCTION, check.INPUTS[0])
