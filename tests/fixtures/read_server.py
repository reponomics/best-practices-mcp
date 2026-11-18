"""Offline test server: production handlers with an injected HTTP transport.

This file is never imported by the installed CLI and accepts no origin override.
"""

import asyncio
import re

import httpx2

from best_practices_mcp.http import BadgeAppHTTP
from best_practices_mcp.server import create_server

PROJECTS = {
    123: {
        "id": 123,
        "name": "Fixture Alpha",
        "repo_url": "https://code.example.org/alpha",
        "homepage_url": "https://example.org/alpha",
        "description_good_status": "Met",
        "description_good_justification": "https://example.org/alpha explains the project.",
        "badge_percentage_0": 100,
        "badge_percentage_1": 12,
        "badge_level": "passing",
        "achieved_passing_at": "2026-10-01T09:00:00.000Z",
        "lost_passing_at": None,
        "updated_at": "2026-11-13T12:34:56.000Z",
        "project_entry_attribution": "Synthetic fixture; no real project data.",
        "project_entry_license": "CC-BY-3.0+",
    },
    456: {
        "id": 456,
        "name": "Fixture Beta",
        "repo_url": "https://code.example.org/beta",
        "homepage_url": "https://example.org/beta",
        "description_good_status": "Unmet",
        "badge_percentage_0": 10,
        "project_entry_attribution": "Synthetic fixture; no real project data.",
        "project_entry_license": "CC-BY-3.0+",
    },
}


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

    async def sleep(self, seconds):
        self.value += seconds
        await asyncio.sleep(0)


def search_response(request):
    query = request.url.params.get("q") or request.url.params.get("url")
    page = request.url.params.get("page", "1")
    if query == "unavailable":
        return httpx2.Response(503)
    if query == "rate-limited":
        return httpx2.Response(429, headers={"Retry-After": "60"})
    if query == "missing" or (query == "pages" and page != "1"):
        return httpx2.Response(200, json=[])
    if query in {"ambiguous", "pages"}:
        return httpx2.Response(200, json=[PROJECTS[123], PROJECTS[456]])
    return httpx2.Response(200, json=[PROJECTS[123]])


def respond(request):
    assert request.method == "GET"
    assert request.url.host == "www.bestpractices.dev"
    if request.url.path == "/projects.json":
        return search_response(request)
    badge = re.fullmatch(r"/projects/([1-9][0-9]*)/(badge|baseline)\.svg", request.url.path)
    if badge:
        return badge_response(*badge.groups())
    project_id = int(request.url.path.rsplit("/", 1)[-1].removesuffix(".json"))
    if project_id in PROJECTS:
        return httpx2.Response(200, json=PROJECTS[project_id])
    return httpx2.Response(404, json={"error": "not found"})


def badge_response(identifier, family):
    project_id = int(identifier)
    if project_id not in PROJECTS:
        return httpx2.Response(404)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg"><text>{family} 雪</text></svg>\n'
    return httpx2.Response(200, text=svg, headers={"Content-Type": "image/svg+xml"})


def factory():
    clock = FakeClock()
    return BadgeAppHTTP(transport=httpx2.MockTransport(respond), clock=clock.now, sleep=clock.sleep)


if __name__ == "__main__":
    create_server(http_factory=factory).run(transport="stdio")
