"""Resolve the App-bot commit identity and delete the merged upstream update branch."""

from __future__ import annotations

import argparse
import os
import re
from urllib.error import HTTPError
from urllib.parse import quote

from check_upstream import GitHub, revision

BRANCH = "automation/upstream-criteria"


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
    mode.add_argument("--merged-head")
    args = parser.parse_args()
    client = GitHub(os.environ["GITHUB_TOKEN"])
    if args.app_slug:
        identity = bot_identity(client, args.app_slug)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"identity={identity}\n")
    else:
        delete_merged_branch(client, os.environ["GITHUB_REPOSITORY"], args.merged_head)


if __name__ == "__main__":
    main()
