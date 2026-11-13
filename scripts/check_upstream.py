"""Compare bundled catalog inputs with BadgeApp production; optionally sync one issue."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "ossf/best-practices-badge"
UPSTREAM_URL = f"https://github.com/{UPSTREAM}"
INPUTS = ("criteria/criteria.yml", "criteria/baseline_criteria.yml", "config/locales/en.yml")
ISSUE_MARKER = "<!-- best-practices-mcp:upstream-criteria -->"
ISSUE_TITLE = "Review upstream production criteria and locale changes"


def revision(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Expected a full upstream commit SHA")
    return value


class GitHub:
    """Paced, bounded requests; tokens are sent only to the GitHub API."""

    def __init__(self, token: str = "") -> None:
        self.token = token

    def request(self, url: str, *, data: dict | None = None, method: str = "GET") -> bytes:
        headers = {"User-Agent": "best-practices-mcp-upstream-check"}
        if url.startswith("https://api.github.com/"):
            headers.update(
                {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
            )
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            url,
            data=None if data is None else json.dumps(data).encode("utf-8"),
            headers=headers,
            method=method,
        )
        time.sleep(0.5)
        with urlopen(request, timeout=30) as response:
            if response.headers.get("X-RateLimit-Remaining") == "0":
                raise RuntimeError(
                    "GitHub API rate limit exhausted; retry after reset "
                    + response.headers.get("X-RateLimit-Reset", "(see GitHub)")
                )
            content = response.read(5_000_001)
        if len(content) > 5_000_000:
            raise ValueError("Upstream response exceeded 5 MB")
        return content

    def api(self, path: str, *, data: dict | None = None, method: str = "GET"):
        return json.loads(self.request(f"https://api.github.com{path}", data=data, method=method))

    def file_hash(self, sha: str, name: str) -> str | None:
        try:
            content = self.request(f"https://raw.githubusercontent.com/{UPSTREAM}/{sha}/{name}")
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class Report:
    bundled_revision: str
    production_revision: str
    bundled_hashes: dict[str, str]
    production_hashes: dict[str, str | None]

    @property
    def changed(self) -> list[str]:
        return [
            name for name in INPUTS if self.bundled_hashes[name] != self.production_hashes[name]
        ]


def read_baseline(source: Path) -> tuple[str, dict[str, str]]:
    manifest = json.loads((source / "source.json").read_text(encoding="utf-8"))
    if manifest["repository"] != UPSTREAM_URL:
        raise ValueError("Unexpected upstream repository in source manifest")
    sha = revision(manifest["revision"])
    hashes = {}
    for name in INPUTS:
        actual = hashlib.sha256((source / name).read_bytes()).hexdigest()
        if actual != manifest["files"][name]:
            raise ValueError(f"Bundled source hash mismatch: {name}")
        hashes[name] = actual
    return sha, hashes


def check_upstream(client: GitHub, source: Path) -> Report:
    bundled, hashes = read_baseline(source)
    ref = client.api(f"/repos/{UPSTREAM}/git/ref/heads/production")
    if ref["ref"] != "refs/heads/production" or ref["object"]["type"] != "commit":
        raise ValueError("Unexpected upstream production reference")
    production = revision(ref["object"]["sha"])
    remote = {name: client.file_hash(production, name) for name in INPUTS}
    return Report(bundled, production, hashes, remote)


def report_body(report: Report) -> str:
    lines = [
        ISSUE_MARKER,
        "# Upstream production criteria check",
        "",
        f"Bundled source: [`{report.bundled_revision}`]"
        f"({UPSTREAM_URL}/commit/{report.bundled_revision}).",
        f"Upstream production: [`{report.production_revision}`]"
        f"({UPSTREAM_URL}/commit/{report.production_revision}).",
        "",
        "This compares the upstream production branch, not an independently verified live-site "
        "deployment. All files are read at the same resolved commit.",
        "",
    ]
    if not report.changed:
        lines.append("All three monitored files match the bundled copies byte for byte.")
    else:
        lines.extend(
            [
                "Changes require review; the bundled catalog has not been updated automatically.",
                "",
                "| Changed file | Bundled source | Production source |",
                "| --- | --- | --- |",
            ]
        )
        for name in report.changed:
            before = f"[view]({UPSTREAM_URL}/blob/{report.bundled_revision}/{name})"
            after = (
                f"[view]({UPSTREAM_URL}/blob/{report.production_revision}/{name})"
                if report.production_hashes[name] is not None
                else "Missing (HTTP 404)"
            )
            lines.append(f"| `{name}` | {before} | {after} |")
        lines.extend(
            [
                "",
                "Review wording as well as IDs, levels, requirements and flags. The full English "
                "locale is monitored, so unrelated UI wording can also trigger this issue.",
                "Follow [the review and update procedure](https://github.com/"
                "reponomics/best-practices-mcp/blob/main/docs/"
                "upstream-compatibility.md#checking-for-upstream-changes).",
            ]
        )
    lines.extend(
        [
            "",
            "## Compared SHA-256 hashes",
            "",
            "| File | Bundled | Production |",
            "| --- | --- | --- |",
        ]
    )
    for name in INPUTS:
        remote = report.production_hashes[name] or "missing"
        lines.append(f"| `{name}` | `{report.bundled_hashes[name]}` | `{remote}` |")
    lines.extend(
        [
            "",
            "This issue body is maintained automatically; record review notes in comments. "
            "Repeated identical results make no issue changes. The same issue is reopened while "
            "differences remain and closed when the monitored files match.",
        ]
    )
    return "\n".join(lines) + "\n"


def find_tracking_issue(client: GitHub, repository: str) -> dict | None:
    matches = []
    page = 1
    while True:
        issues = client.api(f"/repos/{repository}/issues?state=all&per_page=100&page={page}")
        if not isinstance(issues, list):
            raise ValueError("Expected a GitHub issues list")
        matches.extend(
            item
            for item in issues
            if "pull_request" not in item and (item.get("body") or "").startswith(ISSUE_MARKER)
        )
        if len(issues) < 100:
            break
        page += 1
    if len(matches) > 1:
        raise ValueError("Multiple upstream tracking issues found; reconcile them before retrying")
    return matches[0] if matches else None


def sync_issue(client: GitHub, repository: str, report: Report) -> None:
    issue = find_tracking_issue(client, repository)
    if issue is None:
        if report.changed:
            client.api(
                f"/repos/{repository}/issues",
                data={"title": ISSUE_TITLE, "body": report_body(report)},
                method="POST",
            )
        return
    if not report.changed and issue["state"] == "closed":
        return
    state = "open" if report.changed else "closed"
    body = report_body(report)
    if issue["state"] == state and issue["body"] == body and issue["title"] == ISSUE_TITLE:
        return
    client.api(
        f"/repos/{repository}/issues/{issue['number']}",
        data={"title": ISSUE_TITLE, "body": body, "state": state},
        method="PATCH",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-issue", action="store_true", help="Sync the tracker using GITHUB_TOKEN/REPOSITORY"
    )
    args = parser.parse_args(argv)
    try:
        token = os.environ.get("GITHUB_TOKEN", "")
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        if args.update_issue and (
            not token or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        ):
            raise ValueError("Issue updates require GITHUB_TOKEN and GITHUB_REPOSITORY=owner/repo")
        client = GitHub(token)
        report = check_upstream(client, ROOT / "vendor/badgeapp")
        print(report_body(report))
        if args.update_issue:
            sync_issue(client, repository, report)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(f"Upstream check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
