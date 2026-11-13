"""Set explicit App-bot identity and advisory labels for the upstream update PR."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote

from check_upstream import GitHub, revision

BRANCH = "automation/upstream-criteria"

LABELS = {
    "upstream": "Automated update of retained BadgeApp sources and catalog",
    "upstream: criterion-ids": "Advisory: level-qualified criterion IDs were added or removed",
}


def valid_repository(repository: str) -> bool:
    return bool(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repository)
        and repository.split("/")[1] not in {".", ".."}
    )


def bot_identity(client: GitHub, slug: str) -> str:
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        raise ValueError("Expected a GitHub App slug")
    login = f"{slug}[bot]"
    user = client.api(f"/users/{quote(login, safe='')}")
    if user["login"] != login or type(user["id"]) is not int or user["id"] <= 0:
        raise ValueError("Unexpected App bot identity")
    return f"{login} <{user['id']}+{login}@users.noreply.github.com>"


def ensure_label(client: GitHub, repository: str, name: str) -> None:
    try:
        client.api(f"/repos/{repository}/labels/{quote(name, safe='')}")
    except HTTPError as exc:
        if exc.code != 404:
            raise
        client.api(
            f"/repos/{repository}/labels",
            data={"name": name, "color": "1d76db", "description": LABELS[name]},
            method="POST",
        )


def sync_labels(client: GitHub, repository: str, number: int, result: dict) -> None:
    if not valid_repository(repository) or number <= 0:
        raise ValueError("Expected a repository and positive PR number")
    advisory = "upstream: criterion-ids"
    desired = {"upstream"}
    if result["ids"]["added"] or result["ids"]["removed"]:
        desired.add(advisory)
    path = f"/repos/{repository}/issues/{number}/labels"
    current = {label["name"] for label in client.api(f"{path}?per_page=100")}
    for name in sorted(desired - current):
        ensure_label(client, repository, name)
        client.api(path, data={"labels": [name]}, method="POST")
    if advisory in current - desired:
        client.api(f"{path}/{quote(advisory, safe='')}", method="DELETE")


def delete_merged_branch(client: GitHub, repository: str, merged_head: str) -> None:
    """Delete only the reserved branch still pointing at the merged PR's head."""
    revision(merged_head)
    if not valid_repository(repository):
        raise ValueError("Expected a repository")
    try:
        ref = client.api(f"/repos/{repository}/git/ref/heads/{BRANCH}")
    except HTTPError as exc:
        if exc.code == 404:
            return
        raise
    if ref["object"]["sha"] == merged_head:
        client.api(f"/repos/{repository}/git/refs/heads/{BRANCH}", method="DELETE")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--app-slug")
    mode.add_argument("--pr-number", type=int)
    mode.add_argument("--merged-head")
    parser.add_argument("--result", type=Path, default=Path("build/upstream/result.json"))
    args = parser.parse_args()
    client = GitHub(os.environ["GITHUB_TOKEN"])
    if args.app_slug:
        identity = bot_identity(client, args.app_slug)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"identity={identity}\n")
    elif args.merged_head:
        delete_merged_branch(client, os.environ["GITHUB_REPOSITORY"], args.merged_head)
    else:
        sync_labels(
            client,
            os.environ["GITHUB_REPOSITORY"],
            args.pr_number,
            json.loads(args.result.read_text(encoding="utf-8")),
        )


if __name__ == "__main__":
    main()
