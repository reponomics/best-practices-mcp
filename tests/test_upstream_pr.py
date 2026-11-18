"""App attribution and reserved-branch cleanup stay narrowly scoped."""

import importlib
import sys
from pathlib import Path
from unittest.mock import Mock, call
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
pr = importlib.import_module("upstream_pr")
REPOSITORY = "reponomics/best-practices-mcp"
MERGED_HEAD = "a" * 40


def http_error(status):
    return HTTPError("https://api.github.com/example", status, "failure", {}, None)


def writes(client):
    return [item for item in client.api.call_args_list if item.kwargs.get("method", "GET") != "GET"]


def test_bot_identity_uses_verified_app_login_and_numeric_user_id():
    client = Mock(spec=pr.GitHub)
    client.api.return_value = {"login": "release-buddy[bot]", "id": 123}
    assert pr.bot_identity(client, "release-buddy") == (
        "release-buddy[bot] <123+release-buddy[bot]@users.noreply.github.com>"
    )
    client.api.assert_called_once_with("/users/release-buddy%5Bbot%5D")


@pytest.mark.parametrize("slug", ["", "../other", "bot\nidentity=human", "bot[bot]", "has spaces"])
def test_invalid_app_slug_fails_before_network(slug):
    client = Mock(spec=pr.GitHub)
    with pytest.raises(ValueError, match="App slug"):
        pr.bot_identity(client, slug)
    client.api.assert_not_called()


@pytest.mark.parametrize(
    "user",
    [
        {"login": "human", "id": 123},
        {"login": "release-buddy[bot]", "id": "123"},
        {"login": "release-buddy[bot]", "id": True},
        {"login": "release-buddy[bot]", "id": 0},
        {"login": "release-buddy[bot]", "id": -1},
    ],
)
def test_unexpected_bot_identity_cannot_supply_a_commit_identity(user):
    client = Mock(spec=pr.GitHub)
    client.api.return_value = user
    with pytest.raises(ValueError, match="Unexpected App bot identity"):
        pr.bot_identity(client, "release-buddy")
    assert writes(client) == []


def test_cleanup_deletes_only_reserved_branch_at_merged_head():
    client = Mock(spec=pr.GitHub)
    client.api.return_value = {"object": {"sha": MERGED_HEAD}}
    pr.delete_merged_branch(client, REPOSITORY, MERGED_HEAD)
    assert client.api.call_args_list == [
        call(f"/repos/{REPOSITORY}/git/ref/heads/automation/upstream-criteria"),
        call(f"/repos/{REPOSITORY}/git/refs/heads/automation/upstream-criteria", method="DELETE"),
    ]


def test_cleanup_preserves_branch_reused_for_a_new_update():
    client = Mock(spec=pr.GitHub)
    client.api.return_value = {"object": {"sha": "b" * 40}}
    pr.delete_merged_branch(client, REPOSITORY, MERGED_HEAD)
    assert writes(client) == []


def test_cleanup_accepts_already_deleted_branch():
    client = Mock(spec=pr.GitHub)
    client.api.side_effect = http_error(404)
    pr.delete_merged_branch(client, REPOSITORY, MERGED_HEAD)
    assert writes(client) == []


@pytest.mark.parametrize("status", [403, 429, 500])
def test_cleanup_fetch_failure_is_not_treated_as_an_absent_branch(status):
    client = Mock(spec=pr.GitHub)
    client.api.side_effect = http_error(status)
    with pytest.raises(HTTPError):
        pr.delete_merged_branch(client, REPOSITORY, MERGED_HEAD)
    assert writes(client) == []


def test_cleanup_delete_failure_propagates():
    client = Mock(spec=pr.GitHub)
    client.api.side_effect = [{"object": {"sha": MERGED_HEAD}}, http_error(403)]
    with pytest.raises(HTTPError):
        pr.delete_merged_branch(client, REPOSITORY, MERGED_HEAD)


@pytest.mark.parametrize(("repository", "head"), [(REPOSITORY, "main"), ("../other", MERGED_HEAD)])
def test_cleanup_rejects_invalid_target_before_network(repository, head):
    client = Mock(spec=pr.GitHub)
    with pytest.raises(ValueError):
        pr.delete_merged_branch(client, repository, head)
    client.api.assert_not_called()
