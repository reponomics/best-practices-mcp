"""Deterministic public-read transport fixtures; no production requests."""

import asyncio
import gzip
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx2
import pytest

from best_practices_mcp import http
from best_practices_mcp.errors import DomainError
from best_practices_mcp.http import ORIGIN, BadgeAppHTTP


class Clock:
    def __init__(self):
        self.time = 0.0
        self.delays = []

    def __call__(self):
        return self.time

    async def sleep(self, delay):
        self.delays.append(delay)
        self.time += delay
        await asyncio.sleep(0)

    def utcnow(self):
        return datetime(2026, 11, 9, tzinfo=UTC) + timedelta(seconds=self.time)


def client(handler, clock=None):
    clock = clock or Clock()
    return BadgeAppHTTP(
        transport=httpx2.MockTransport(handler),
        clock=clock,
        sleep=clock.sleep,
        utcnow=clock.utcnow,
    )


def test_fixed_origin_encoded_query_identity_and_no_cookie_reuse() -> None:
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, json={"id": 123}, headers={"set-cookie": "session=secret"})

    async def run():
        async with client(handler) as api:
            first = await api.get_json("/projects.json", {"q": "white space /雪", "page": 1})
            second = await api.get_json("/projects/123.json")
        return first, second

    first, second = asyncio.run(run())
    assert first.source_url == ORIGIN + "/projects.json?page=1&q=white%20space%20%2F%E9%9B%AA"
    assert second.data == {"id": 123}
    assert first.fetched_at == "2026-11-09T00:00:00+00:00"
    assert all(request.method == "GET" for request in requests)
    assert all(
        "cookie" not in request.headers and "authorization" not in request.headers
        for request in requests
    )
    assert all(
        request.headers["user-agent"].startswith("bestpractices-mcp/") for request in requests
    )
    assert requests[0].extensions["timeout"]["connect"] == 5
    assert requests[0].extensions["timeout"]["read"] == 10


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("https://evil.invalid/project.json", None),
        ("//evil.invalid/project.json", None),
        ("/en/projects.json", None),
        ("/en/projects/123.json", None),
        ("/fr/projects/123.json", None),
        ("/projects/../123.json", None),
        ("/projects/0.json", None),
        ("/projects/01.json", None),
        ("/projects/123.json?token=secret", None),
        ("/projects/123.json", {"q": "anything"}),
        ("/projects.json", {"secret": "not allowed"}),
        ("/projects.json", {"q": "text", "url": "https://example.org"}),
        ("/projects.json", {"page": True}),
    ],
)
def test_unapproved_request_target_never_reaches_transport(path, params) -> None:
    async def run():
        async with client(lambda _: pytest.fail("Request dispatched")) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json(path, params)
            assert error.value.code == "invalid_query"

    asyncio.run(run())


def test_shared_limiter_paces_concurrent_calls_and_retries() -> None:
    clock = Clock()
    starts = []
    calls = 0

    def handler(_request):
        nonlocal calls
        starts.append(clock())
        calls += 1
        return httpx2.Response(503 if calls == 1 else 200, json={"id": 123})

    async def run():
        async with client(handler, clock) as api:
            results = await asyncio.gather(*(api.get_json("/projects/123.json") for _ in range(3)))
            assert len(results) == 3

    asyncio.run(run())
    assert len(starts) == 4
    assert all(after - before >= 1 for before, after in zip(starts, starts[1:]))


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_retryable_statuses_have_three_attempts_and_backoff(status) -> None:
    clock = Clock()
    starts = []

    def handler(_request):
        starts.append(clock())
        return httpx2.Response(status, text="secret response body")

    async def run():
        async with client(handler, clock) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json("/projects/123.json")
            assert error.value.code == ("rate_limited" if status == 429 else "upstream_unavailable")
            assert "secret" not in json.dumps(error.value.to_payload())

    asyncio.run(run())
    assert starts == [0, 1, 3]


@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.parametrize("delay", [7, 90])
def test_final_retry_after_preserves_error_precedence_and_shared_cooldown(status, delay) -> None:
    clock = Clock()
    starts = []

    def handler(_request):
        starts.append(clock())
        if len(starts) < 3:
            return httpx2.Response(503)
        if len(starts) == 3:
            return httpx2.Response(status, headers={"Retry-After": str(delay)})
        return httpx2.Response(200, json=[])

    async def run():
        async with client(handler, clock) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json("/projects.json")
            rate_limited = status == 429 or delay == 90
            assert error.value.code == ("rate_limited" if rate_limited else "upstream_unavailable")
            if rate_limited:
                assert error.value.retry_after_seconds == delay
            assert starts == [0, 1, 3]
            assert clock.delays == [1, 2]
            assert clock() == 3

            if delay == 90:
                with pytest.raises(DomainError) as subsequent:
                    await api.get_json("/projects.json")
                assert subsequent.value.code == "rate_limited"
                assert subsequent.value.retry_after_seconds == delay
                assert starts == [0, 1, 3]
                assert clock.delays == [1, 2]
            else:
                assert (await api.get_json("/projects.json")).data == []
                assert starts == [0, 1, 3, 10]
                assert clock.delays == [1, 2, 7]

    asyncio.run(run())


def test_transient_transport_exhaustion_does_not_sleep_after_final_failure() -> None:
    clock = Clock()
    starts = []

    def handler(request):
        starts.append(clock())
        raise httpx2.ReadError("secret network detail", request=request)

    async def run():
        async with client(handler, clock) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json("/projects.json")
            assert error.value.code == "upstream_unavailable"
            assert "secret" not in json.dumps(error.value.to_payload())

    asyncio.run(run())
    assert starts == [0, 1, 3]
    assert clock.delays == [1, 2]
    assert clock() == 3


@pytest.mark.parametrize(
    "exception", [httpx2.ConnectError, httpx2.ReadError, httpx2.ConnectTimeout, httpx2.ReadTimeout]
)
def test_connection_and_read_failures_are_retried(exception) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            raise exception("secret network detail", request=request)
        return httpx2.Response(200, json={"id": 123})

    async def run():
        async with client(handler) as api:
            return await api.get_json("/projects/123.json")

    assert asyncio.run(run()).data == {"id": 123}
    assert len(calls) == 3


@pytest.mark.parametrize("value, expected", [("7", 7), ("broken", 1), ("-9", 1)])
def test_retry_after_seconds_and_malformed_fallback(value, expected) -> None:
    clock = Clock()
    starts = []

    def handler(_request):
        starts.append(clock())
        if len(starts) == 1:
            return httpx2.Response(429, headers={"Retry-After": value})
        return httpx2.Response(200, json=[])

    async def run():
        async with client(handler, clock) as api:
            await api.get_json("/projects.json")

    asyncio.run(run())
    assert starts == [0, expected]


def test_retry_after_http_date_is_shared_with_later_calls() -> None:
    clock = Clock()
    starts = []
    until = format_datetime(clock.utcnow() + timedelta(seconds=120), usegmt=True)

    def handler(_request):
        starts.append(clock())
        return httpx2.Response(503, headers={"Retry-After": until})

    async def run():
        async with client(handler, clock) as api:
            for _ in range(2):
                with pytest.raises(DomainError) as error:
                    await api.get_json("/projects.json")
                assert error.value.code == "rate_limited"
                assert error.value.retry_after_seconds == 120

    asyncio.run(run())
    assert starts == [0]
    assert not clock.delays


def test_later_shorter_retry_after_never_shortens_shared_cooldown() -> None:
    clock = Clock()

    async def run():
        async with client(lambda _: httpx2.Response(200, json=[]), clock) as api:
            with pytest.raises(DomainError):
                api._update_cooldown(http._Retryable(429, "90"), 30)
            with pytest.raises(DomainError) as error:
                api._update_cooldown(http._Retryable(429, "3"), 30)
            assert error.value.retry_after_seconds == 90

    asyncio.run(run())


@pytest.mark.parametrize("status", [301, 302, 307, 400, 401, 403, 500])
def test_redirects_and_other_http_failures_are_not_retried_or_followed(status) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(status, headers={"location": "https://evil.invalid"}, text="secret")

    async def run():
        async with client(handler) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json("/projects/123.json")
            assert error.value.code == "upstream_invalid_response"
            assert "secret" not in json.dumps(error.value.to_payload())

    asyncio.run(run())
    assert len(calls) == 1


def test_not_found_retains_safe_observation_for_empty_id_lookup() -> None:
    async def run():
        async with client(lambda _: httpx2.Response(404, text="secret")) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json("/projects/123.json")
            assert error.value.code == "project_not_found"
            assert error.value.details == {
                "source_url": ORIGIN + "/projects/123.json",
                "fetched_at": "2026-11-09T00:00:00+00:00",
            }

    asyncio.run(run())


@pytest.mark.parametrize(
    "body, content_type",
    [
        (b"<html>secret</html>", "text/html"),
        (b"<html>secret</html>", "application/json"),
        (b'{"id":1,"id":2}', "application/json"),
        (b'{"number":NaN}', "application/json"),
        (b'{"number":1e999}', "application/json"),
        (b'{"text":"\\ud800"}', "application/json"),
        (b"\xff", "application/json"),
        (b"[" * 70 + b"0" + b"]" * 70, "application/json"),
    ],
)
def test_invalid_json_is_safe_and_not_retried(body, content_type) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(200, content=body, headers={"content-type": content_type})

    async def run():
        async with client(handler) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json("/projects/123.json")
            assert error.value.code == "upstream_invalid_response"
            assert "secret" not in json.dumps(error.value.to_payload())

    asyncio.run(run())
    assert len(calls) == 1


class Stream(httpx2.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("compressed", [False, True])
def test_decoded_body_limit_and_stream_cleanup(monkeypatch, compressed) -> None:
    monkeypatch.setattr(http, "UPSTREAM_LIMIT_BYTES", 128)
    body = json.dumps({"large": "x" * 256}).encode()
    stream = Stream([gzip.compress(body) if compressed else body])
    headers = {"content-type": "application/json"}
    if compressed:
        headers["content-encoding"] = "gzip"

    async def run():
        async with client(lambda _: httpx2.Response(200, stream=stream, headers=headers)) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json("/projects/123.json")
            assert error.value.code == "upstream_invalid_response"

    asyncio.run(run())
    assert stream.closed


def test_exact_body_boundary_is_allowed(monkeypatch) -> None:
    monkeypatch.setattr(http, "UPSTREAM_LIMIT_BYTES", 2)

    async def run():
        async with client(lambda _: httpx2.Response(200, json=[])) as api:
            assert (await api.get_json("/projects.json")).data == []

    asyncio.run(run())


def test_attempt_timeout_respects_remaining_retry_budget(monkeypatch) -> None:
    monkeypatch.setattr(http, "OVERALL_TIMEOUT_SECONDS", 0.035)
    monkeypatch.setattr(http, "ATTEMPT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(http, "REQUEST_INTERVAL_SECONDS", 0)
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(1)
        return httpx2.Response(200, json=[])

    async def no_backoff(_delay):
        await asyncio.sleep(0)

    async def run():
        async with BadgeAppHTTP(transport=httpx2.MockTransport(handler), sleep=no_backoff) as api:
            with pytest.raises(DomainError) as error:
                await asyncio.wait_for(api.get_json("/projects.json"), timeout=0.3)
            assert error.value.code == "upstream_unavailable"

    asyncio.run(run())
    assert len(calls) == 1


def test_overall_deadline_includes_limiter_wait(monkeypatch) -> None:
    monkeypatch.setattr(http, "OVERALL_TIMEOUT_SECONDS", 0.02)
    waiting = asyncio.Event()
    clock = Clock()
    calls = []

    async def stuck_sleep(_delay):
        waiting.set()
        await asyncio.Event().wait()

    def handler(request):
        calls.append(request)
        return httpx2.Response(200, json=[])

    async def run():
        async with BadgeAppHTTP(
            transport=httpx2.MockTransport(handler), clock=clock, sleep=stuck_sleep
        ) as api:
            await api.get_json("/projects.json")
            # A scheduled start inside the budget still cannot wait indefinitely.
            api._next_start = 0.01
            with pytest.raises(DomainError) as error:
                await asyncio.wait_for(api.get_json("/projects.json"), timeout=0.3)
            assert error.value.code == "upstream_unavailable"
            assert waiting.is_set()

    asyncio.run(run())
    assert len(calls) == 1


def test_invalid_compression_is_not_retried_and_closes_stream() -> None:
    stream = Stream([b"invalid compressed secret"])
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(
            200,
            stream=stream,
            headers={"content-type": "application/json", "content-encoding": "gzip"},
        )

    async def run():
        async with client(handler) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json("/projects.json")
            assert error.value.code == "upstream_invalid_response"
            assert "secret" not in json.dumps(error.value.to_payload())

    asyncio.run(run())
    assert stream.closed
    assert len(calls) == 1


def test_extreme_retry_after_keeps_cooldown_without_numeric_overflow() -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(429, headers={"retry-after": "9" * 400})

    async def run():
        async with client(handler) as api:
            for _ in range(2):
                with pytest.raises(DomainError) as error:
                    await api.get_json("/projects.json")
                assert error.value.code == "rate_limited"

    asyncio.run(run())
    assert len(calls) == 1


def test_missing_search_endpoint_is_upstream_drift() -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(404, text="secret")

    async def run():
        async with client(handler) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json("/projects.json", {"q": "example"})
            assert error.value.code == "upstream_invalid_response"
            assert "secret" not in json.dumps(error.value.to_payload())

    asyncio.run(run())
    assert len(calls) == 1


def test_cancellation_during_body_closes_stream_and_propagates() -> None:
    entered = asyncio.Event()

    class HangingStream(Stream):
        async def __aiter__(self):
            entered.set()
            await asyncio.Event().wait()
            yield b"[]"

    stream = HangingStream([])

    async def run():
        def handler(_request):
            return httpx2.Response(200, stream=stream, headers={"content-type": "application/json"})

        async with client(handler) as api:
            task = asyncio.create_task(api.get_json("/projects.json"))
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert stream.closed

    asyncio.run(run())


def test_cancelled_limiter_wait_releases_guard_for_another_call() -> None:
    waiting = asyncio.Event()
    clock = Clock()
    count = 0

    async def sleep(delay):
        waiting.set()
        await asyncio.Event().wait()

    def handler(_request):
        nonlocal count
        count += 1
        return httpx2.Response(200, json=[])

    async def run():
        async with BadgeAppHTTP(
            transport=httpx2.MockTransport(handler), clock=clock, sleep=sleep
        ) as api:
            await api.get_json("/projects.json")
            pending = asyncio.create_task(api.get_json("/projects.json"))
            await waiting.wait()
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            clock.time = 2
            await asyncio.wait_for(api.get_json("/projects.json"), timeout=0.3)

    asyncio.run(run())
    assert count == 2


def test_cookie_policy_blocks_preexisting_cookies() -> None:
    from urllib.request import Request

    cookies = httpx2.Cookies()
    cookies.set("session", "secret", domain="www.bestpractices.dev", path="/")
    cookies.jar.set_policy(http._NoCookies())
    request = Request(ORIGIN + "/projects.json")
    cookies.jar.add_cookie_header(request)
    assert not request.has_header("Cookie")


def test_explicit_close_closes_transport() -> None:
    class Transport(httpx2.MockTransport):
        closed = False

        async def aclose(self):
            self.closed = True

    transport = Transport(lambda _: httpx2.Response(200, json=[]))

    async def run():
        api = BadgeAppHTTP(transport=transport)
        await api.aclose()
        assert transport.closed
        assert api._client.is_closed

    asyncio.run(run())


@pytest.mark.parametrize("now, next_start", [(30, 0), (0, 30)])
def test_limiter_rejects_expired_or_unreachable_start_without_dispatch(now, next_start) -> None:
    clock = Clock()
    clock.time = now

    async def run():
        async with client(lambda _: pytest.fail("Request dispatched"), clock) as api:
            api._next_start = next_start
            with pytest.raises(DomainError) as error:
                await api._wait_for_start(30)
            assert error.value.code == "upstream_unavailable"
        assert not clock.delays

    asyncio.run(run())


def test_retry_after_date_without_timezone_uses_backoff() -> None:
    clock = Clock()
    starts = []

    def handler(_request):
        starts.append(clock())
        if len(starts) == 1:
            return httpx2.Response(429, headers={"retry-after": "Mon, 09 Nov 2026 00:02:00 -0000"})
        return httpx2.Response(200, json=[])

    async def run():
        async with client(handler, clock) as api:
            assert (await api.get_json("/projects.json")).data == []

    asyncio.run(run())
    assert starts == [0, 1]


def test_attempt_rejects_expired_deadline_without_dispatch() -> None:
    async def run():
        async with client(lambda _: pytest.fail("Request dispatched")) as api:
            with pytest.raises(DomainError) as error:
                await api._attempt("/projects.json", None, 0)
            assert error.value.code == "upstream_unavailable"

    asyncio.run(run())


def test_response_completed_after_deadline_is_discarded_and_closed() -> None:
    clock = Clock()
    calls = []

    class LateStream(Stream):
        async def __aiter__(self):
            yield b"[]"
            clock.time = 30

    stream = LateStream([])

    def handler(request):
        calls.append(request)
        return httpx2.Response(200, stream=stream, headers={"content-type": "application/json"})

    async def run():
        async with client(handler, clock) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json("/projects.json")
            assert error.value.code == "upstream_unavailable"
        assert stream.closed

    asyncio.run(run())
    assert len(calls) == 1


@pytest.mark.parametrize("exception", [httpx2.WriteError, httpx2.PoolTimeout])
def test_non_retryable_transport_errors_are_safe_and_not_retried(exception) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        raise exception("secret network detail", request=request)

    async def run():
        async with client(handler) as api:
            with pytest.raises(DomainError) as error:
                await api.get_json("/projects.json")
            assert error.value.code == "upstream_unavailable"
            assert "secret" not in json.dumps(error.value.to_payload())

    asyncio.run(run())
    assert len(calls) == 1
