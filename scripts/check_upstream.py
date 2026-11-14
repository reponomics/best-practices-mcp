"""Compare bundled BadgeApp sources with production; optionally prepare a PR patch."""

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
SOURCE_FILES = (*INPUTS, "docs/automation-approach.md", "docs/automation-proposals.md", "LICENSE")


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
        content = self.request(f"https://api.github.com{path}", data=data, method=method)
        return json.loads(content) if content else None

    def source_file(self, sha: str, name: str) -> bytes | None:
        try:
            return self.request(f"https://raw.githubusercontent.com/{UPSTREAM}/{sha}/{name}")
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise


@dataclass(frozen=True)
class Report:
    bundled_revision: str
    production_revision: str
    bundled_hashes: dict[str, str]
    production_files: dict[str, bytes | None]

    @property
    def production_hashes(self) -> dict[str, str | None]:
        return {
            name: None if content is None else hashlib.sha256(content).hexdigest()
            for name, content in self.production_files.items()
        }

    @property
    def changed(self) -> list[str]:
        remote = self.production_hashes
        return [name for name in SOURCE_FILES if self.bundled_hashes[name] != remote[name]]


def read_baseline(source: Path) -> tuple[str, dict[str, str]]:
    manifest = json.loads((source / "source.json").read_text(encoding="utf-8"))
    if manifest["repository"] != UPSTREAM_URL or set(manifest["files"]) != set(SOURCE_FILES):
        raise ValueError("Unexpected upstream repository or retained source paths")
    sha = revision(manifest["revision"])
    hashes = {}
    for name in SOURCE_FILES:
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
    remote = {name: client.source_file(production, name) for name in SOURCE_FILES}
    return Report(bundled, production, hashes, remote)


def report_body(report: Report) -> str:
    lines = [
        "# Upstream production source update",
        "",
        f"Bundled source: [`{report.bundled_revision}`]"
        f"({UPSTREAM_URL}/commit/{report.bundled_revision}).",
        f"Upstream production: [`{report.production_revision}`]"
        f"({UPSTREAM_URL}/commit/{report.production_revision}).",
        "",
        "This compares the upstream production branch, not an independently verified live-site "
        "deployment. All retained sources are read at the same resolved commit.",
        "",
    ]
    if not report.changed:
        lines.append("All retained source files match the bundled copies byte for byte.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "Review the source and generated changes together. Labels are advisory; all updates "
            "require maintainer review and passing CI. No runtime code is changed automatically.",
            "",
            "| Changed file | Bundled source | Production source |",
            "| --- | --- | --- |",
        ]
    )
    for name in report.changed:
        before = f"[view]({UPSTREAM_URL}/blob/{report.bundled_revision}/{name})"
        after = (
            f"[view]({UPSTREAM_URL}/blob/{report.production_revision}/{name})"
            if report.production_files[name] is not None
            else "Missing (HTTP 404)"
        )
        lines.append(f"| `{name}` | {before} | {after} |")
    lines.extend(
        [
            "",
            "Follow [the review and update procedure](https://github.com/"
            "reponomics/best-practices-mcp/blob/main/docs/"
            "upstream-compatibility.md#checking-for-upstream-changes).",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepare-update", action="store_true", help="Refresh local sources, catalog and doc pins"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/upstream")
    args = parser.parse_args(argv)
    try:
        client = GitHub(os.environ.get("GITHUB_TOKEN", ""))
        report = check_upstream(client, ROOT / "vendor/badgeapp")
        body = report_body(report)
        if args.prepare_update:
            from prepare_upstream import prepare_update

            body += prepare_update(client, report, ROOT, args.output_dir)
        print(body)
        if args.prepare_update:
            (args.output_dir / "pr.md").write_text(body, encoding="utf-8")
            result = json.loads((args.output_dir / "result.json").read_text(encoding="utf-8"))
            if output := os.environ.get("GITHUB_OUTPUT"):
                with open(output, "a", encoding="utf-8") as stream:
                    failed = str(result["generation_error"] is not None).lower()
                    stream.write(f"generation-failed={failed}\n")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(f"Upstream check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
