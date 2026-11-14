"""Bounded, paced public BadgeApp GET transport; no cookies or remote writes."""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any
from urllib.parse import quote, urlencode
from xml.etree import ElementTree

import httpx2

from best_practices_mcp import __version__
from best_practices_mcp.documents import MAX_JSON_DEPTH, UPSTREAM_LIMIT_BYTES
from best_practices_mcp.errors import DomainError

ORIGIN = "https://www.bestpractices.dev"
MAX_ATTEMPTS = 3
OVERALL_TIMEOUT_SECONDS = 30.0
ATTEMPT_TIMEOUT_SECONDS = 10.0
REQUEST_INTERVAL_SECONDS = 1.0
RETRY_STATUSES = frozenset({429, 502, 503, 504})
TRANSIENT_ERRORS = (
    httpx2.ConnectError,
    httpx2.ReadError,
    httpx2.ConnectTimeout,
    httpx2.ReadTimeout,
)
PROJECT_PATH = re.compile(r"/projects/[1-9][0-9]*\.json\Z")
BADGE_JSON_PATH = re.compile(r"/projects/[1-9][0-9]*/(?:badge|baseline)\.json\Z")
BADGE_SVG_PATH = re.compile(r"/projects/[1-9][0-9]*/(?:badge|baseline)\.svg\Z")
SVG_LIMIT_BYTES = 1_048_576
SVG_ROOT = "{http://www.w3.org/2000/svg}svg"


@dataclass(frozen=True)
class FetchResult:
    data: Any
    source_url: str
    fetched_at: str
    headers: dict[str, str]


class _NoCookies(DefaultCookiePolicy):
    def set_ok(self, cookie, request) -> bool:
        return False

    def return_ok(self, cookie, request) -> bool:
        return False


class _Retryable(Exception):
    def __init__(self, status: int | None = None, retry_after: str | None = None):
        self.status = status
        self.retry_after = retry_after


def _unavailable() -> DomainError:
    return DomainError(
        "upstream_unavailable",
        "BadgeApp could not complete the public read within the bounded retry policy.",
        recovery="Retry the public read later.",
    )


def _invalid_response(message: str = "BadgeApp returned an invalid public response."):
    return DomainError(
        "upstream_invalid_response", message, recovery="Retry later or report drift."
    )


def _rate_limited(delay: float) -> DomainError:
    return DomainError(
        "rate_limited",
        "BadgeApp requested a delay before another public read.",
        recovery="Retry the public read after the indicated delay.",
        retry_after_seconds=max(0, math.ceil(delay)) if math.isfinite(delay) else None,
    )


def _valid_query_value(key: str, value: Any) -> bool:
    if key == "page":
        return type(value) is int and value > 0
    return type(value) is str


def _validate_parameters(params: dict) -> None:
    if set(params) - {"q", "url", "page"}:
        raise DomainError("invalid_query", "Unsupported public query parameters.")
    if "q" in params and "url" in params:
        raise DomainError("invalid_query", "Choose one public query type.")
    if any(not _valid_query_value(key, value) for key, value in params.items()):
        raise DomainError("invalid_query", "Invalid public query parameter type.")


def _validate_target(path: str, params: dict | None) -> None:
    if (
        path != "/projects.json"
        and PROJECT_PATH.fullmatch(path) is None
        and BADGE_JSON_PATH.fullmatch(path) is None
    ):
        raise DomainError("invalid_query", "Only documented public project JSON paths are allowed.")
    if params:
        if path != "/projects.json":
            raise DomainError("invalid_query", "Single-project reads accept no query parameters.")
        _validate_parameters(params)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _check_scalar(value: Any) -> None:
    if isinstance(value, str):
        value.encode("utf-8")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite JSON number")


def _check_json_values(data: Any) -> None:
    pending = [(data, 1)]
    while pending:
        value, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise ValueError("JSON nesting exceeds the server limit")
        if isinstance(value, dict):
            pending.extend((child, depth + 1) for child in value.values())
            pending.extend((key, depth + 1) for key in value)
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
        else:
            _check_scalar(value)


def _decode_json(body: bytes) -> Any:
    try:
        data = json.loads(
            body.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        _check_json_values(data)
        return data
    except (ValueError, UnicodeError, RecursionError) as error:
        raise _invalid_response() from error


def _decode_svg(body: bytes) -> str:
    """Validate an inert SVG artifact without expanding declarations or altering bytes."""
    try:
        text = body.decode("utf-8")
        # Reject declarations before XML parsing, including internal/external entities.
        # This deliberately also rejects declaration-looking text inside comments.
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
            raise ValueError("SVG declarations are unsupported")
        if ElementTree.fromstring(text).tag != SVG_ROOT:
            raise ValueError("Expected an SVG root in the SVG namespace")
        return text
    except (ValueError, UnicodeError, ElementTree.ParseError) as error:
        raise _invalid_response("BadgeApp did not return a valid UTF-8 SVG document.") from error


class BadgeAppHTTP:
    """One lifespan-owned client and limiter, shared by every public tool call."""

    def __init__(
        self,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._clock, self._sleep, self._utcnow = clock, sleep, utcnow
        self._lock = asyncio.Lock()
        self._next_start = 0.0
        self._cooldown_until = 0.0
        self._client = httpx2.AsyncClient(
            transport=transport,
            trust_env=False,
            auth=None,
            cookies=CookieJar(policy=_NoCookies()),
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": f"bestpractices-mcp/{__version__}",
            },
            timeout=httpx2.Timeout(ATTEMPT_TIMEOUT_SECONDS, connect=5.0),
        )

    async def __aenter__(self) -> BadgeAppHTTP:
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._client.__aexit__(*exc_info)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _wait_for_start(self, deadline: float) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                if now >= deadline:
                    raise _unavailable()
                target = max(self._next_start, self._cooldown_until)
                if target >= deadline:
                    if self._cooldown_until >= deadline:
                        raise _rate_limited(self._cooldown_until - now)
                    raise _unavailable()
                if target <= now:
                    self._next_start = now + REQUEST_INTERVAL_SECONDS
                    return
                await self._sleep(target - now)

    def _retry_delay(self, value: str | None) -> float | None:
        if value is None:
            return None
        if re.fullmatch(r"[0-9]+", value.strip()):
            try:
                return float(value.strip())
            except (ValueError, OverflowError):
                return None
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            return max(0.0, (date - self._utcnow()).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None

    def _update_cooldown(self, failure: _Retryable, deadline: float) -> float:
        delay = self._retry_delay(failure.retry_after)
        if delay is not None:
            self._cooldown_until = max(self._cooldown_until, self._clock() + delay)
        cooldown = max(0.0, self._cooldown_until - self._clock())
        if self._cooldown_until >= deadline:
            raise _rate_limited(cooldown)
        return cooldown

    async def _wait_for_retry(self, attempts: int, deadline: float) -> None:
        backoff = float(attempts)
        if self._clock() + backoff >= deadline:
            raise _unavailable()
        await self._sleep(backoff)

    async def _read_body(self, response: httpx2.Response, limit: int | None = None) -> bytes:
        limit = UPSTREAM_LIMIT_BYTES if limit is None else limit
        body = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=65_536):
            if len(body) + len(chunk) > limit:
                raise _invalid_response(
                    "BadgeApp's decoded response exceeds the server byte limit."
                )
            body.extend(chunk)
        return bytes(body)

    def _check_response(self, response: httpx2.Response, *, svg: bool = False) -> None:
        status = response.status_code
        if status in RETRY_STATUSES:
            raise _Retryable(status, response.headers.get("retry-after"))
        if status == 404 and any(
            pattern.fullmatch(response.url.path)
            for pattern in (PROJECT_PATH, BADGE_JSON_PATH, BADGE_SVG_PATH)
        ):
            raise DomainError(
                "project_not_found",
                "BadgeApp did not find the requested public project.",
                details={"source_url": str(response.url), "fetched_at": self._utcnow().isoformat()},
                recovery="Verify the registered project identifier or repeat discovery.",
            )
        if status != 200:
            raise _invalid_response("BadgeApp returned an unexpected HTTP status.")
        media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if svg:
            if media_type != "image/svg+xml":
                raise _invalid_response("BadgeApp did not return SVG content.")
        elif media_type != "application/json" and not media_type.endswith("+json"):
            raise _invalid_response("BadgeApp did not return JSON content.")

    async def _attempt(
        self, path: str, params: dict | None, deadline: float, *, svg: bool = False
    ) -> FetchResult:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise _unavailable()
        url = ORIGIN + path
        if params:
            url += "?" + urlencode(sorted(params.items()), quote_via=quote)
        headers = {"Accept": "image/svg+xml"} if svg else None
        try:
            async with asyncio.timeout(min(ATTEMPT_TIMEOUT_SECONDS, remaining)):
                async with self._client.stream("GET", url, headers=headers) as response:
                    self._check_response(response, svg=svg)
                    body = await self._read_body(response, SVG_LIMIT_BYTES if svg else None)
                    data = _decode_svg(body) if svg else _decode_json(body)
                    if self._clock() >= deadline:
                        raise _unavailable()
                    return FetchResult(
                        data, str(response.url), self._utcnow().isoformat(), dict(response.headers)
                    )
        except (*TRANSIENT_ERRORS, TimeoutError) as error:
            raise _Retryable() from error
        except (httpx2.DecodingError, httpx2.RemoteProtocolError) as error:
            raise _invalid_response() from error
        except httpx2.HTTPError as error:
            raise _unavailable() from error

    async def get_json(self, path: str, params: dict | None = None) -> FetchResult:
        """Read only fixed-origin project resources; returned failures contain no body text."""
        _validate_target(path, params)
        return await self._get(path, params)

    async def get_svg(self, path: str) -> FetchResult:
        """Read a bounded SVG badge as inert UTF-8 text, never rendering or executing it."""
        if BADGE_SVG_PATH.fullmatch(path) is None:
            raise DomainError(
                "invalid_query", "Only documented public badge SVG paths are allowed."
            )
        return await self._get(path, None, svg=True)

    async def _get(self, path: str, params: dict | None, *, svg: bool = False) -> FetchResult:
        deadline = self._clock() + OVERALL_TIMEOUT_SECONDS
        try:
            async with asyncio.timeout(OVERALL_TIMEOUT_SECONDS):
                attempts = 0
                while True:
                    await self._wait_for_start(deadline)
                    try:
                        return await self._attempt(path, params, deadline, svg=svg)
                    except _Retryable as failure:
                        attempts += 1
                        # Retain Retry-After even when this call cannot retry again.
                        cooldown = self._update_cooldown(failure, deadline)
                        if attempts >= MAX_ATTEMPTS:
                            if failure.status == 429:
                                raise _rate_limited(cooldown)
                            raise _unavailable()
                        await self._wait_for_retry(attempts, deadline)
        except TimeoutError as error:
            raise _unavailable() from error
