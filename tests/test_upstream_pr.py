"""App attribution, advisory labels and reserved-branch cleanup stay narrowly scoped."""

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
NUMBER = 42
MERGED_HEAD = "a" * 40
LABEL_PATH = f"/repos/{REPOSITORY}/issues/{NUMBER}/labels"
ADVISORY = "upstream: criterion-ids"
ENCODED_ADVISORY = "upstream%3A%20criterion-ids"


def http_error(status):
    return HTTPError("https://api.github.com/example", status, "failure", {}, None)


def result(*, added=(), removed=(), error=None):
    return {"ids": {"added": list(added), "removed": list(removed), "error": error}}


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


def test_existing_label_metadata_is_not_overwritten():
    client = Mock(spec=pr.GitHub)
    client.api.return_value = {"name": "upstream", "color": "custom", "description": "human"}
    pr.ensure_label(client, REPOSITORY, "upstream")
    assert writes(client) == []


def test_missing_advisory_label_is_created_with_its_explanation():
    client = Mock(spec=pr.GitHub)
    client.api.side_effect = [http_error(404), {"name": ADVISORY}]
    pr.ensure_label(client, REPOSITORY, ADVISORY)
    assert writes(client) == [
        call(
            f"/repos/{REPOSITORY}/labels",
            data={"name": ADVISORY, "color": "1d76db", "description": pr.LABELS[ADVISORY]},
            method="POST",
        )
    ]
    assert client.api.call_args_list[0].args == (f"/repos/{REPOSITORY}/labels/{ENCODED_ADVISORY}",)


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_label_fetch_failure_does_not_attempt_creation(status):
    client = Mock(spec=pr.GitHub)
    client.api.side_effect = http_error(status)
    with pytest.raises(HTTPError) as raised:
        pr.ensure_label(client, REPOSITORY, "upstream")
    assert raised.value.code == status
    assert writes(client) == []


@pytest.mark.parametrize("changes", [result(added=["gold/new"]), result(removed=["gold/old"])])
def test_id_changes_add_advisory_without_replacing_human_labels(changes):
    client = Mock(spec=pr.GitHub)
    client.api.side_effect = [
        [{"name": "upstream"}, {"name": "reviewed-by-maintainer"}],
        {"name": ADVISORY},
        [],
    ]
    pr.sync_labels(client, REPOSITORY, NUMBER, changes)
    assert writes(client) == [call(LABEL_PATH, data={"labels": [ADVISORY]}, method="POST")]


@pytest.mark.parametrize("changes", [result(), result(error="Cannot parse new schema")])
def test_current_diff_without_known_id_changes_removes_only_stale_advisory(changes):
    client = Mock(spec=pr.GitHub)
    client.api.return_value = [
        {"name": "upstream"},
        {"name": ADVISORY},
        {"name": "maintainer-notes"},
    ]
    pr.sync_labels(client, REPOSITORY, NUMBER, changes)
    assert writes(client) == [call(f"{LABEL_PATH}/{ENCODED_ADVISORY}", method="DELETE")]


def test_general_upstream_label_is_added_even_when_id_comparison_is_unavailable():
    client = Mock(spec=pr.GitHub)
    client.api.side_effect = [[{"name": "needs-manual-fix"}], {"name": "upstream"}, []]
    pr.sync_labels(client, REPOSITORY, NUMBER, result(error="New source structure"))
    assert writes(client) == [call(LABEL_PATH, data={"labels": ["upstream"]}, method="POST")]


@pytest.mark.parametrize(
    ("changes", "labels"),
    [(result(), ["upstream", "manual"]), (result(added=["silver/new"]), ["upstream", ADVISORY])],
)
def test_identical_label_state_does_not_write(changes, labels):
    client = Mock(spec=pr.GitHub)
    client.api.return_value = [{"name": name} for name in labels]
    pr.sync_labels(client, REPOSITORY, NUMBER, changes)
    assert writes(client) == []
    assert client.api.call_count == 1


@pytest.mark.parametrize(("repository", "number"), [("../other", NUMBER), (REPOSITORY, 0)])
def test_invalid_label_target_fails_before_network(repository, number):
    client = Mock(spec=pr.GitHub)
    with pytest.raises(ValueError):
        pr.sync_labels(client, repository, number, result())
    client.api.assert_not_called()


def test_label_write_failure_propagates():
    client = Mock(spec=pr.GitHub)
    client.api.side_effect = [[], {"name": "upstream"}, http_error(403)]
    with pytest.raises(HTTPError):
        pr.sync_labels(client, REPOSITORY, NUMBER, result())


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
