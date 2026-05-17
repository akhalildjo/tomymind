from __future__ import annotations

import base64
import json
from collections.abc import Callable

import httpx
import jwt as pyjwt
import pytest

from tomymind.errors import SessionError
from tomymind.mymind_client import (
    CreateResult,
    MymindClient,
    MymindCreds,
    _extract_detail,
    parse_ratelimit_reset,
    sign_request,
)

# Real-shape sample, NOT a real key: 32 random bytes base64-encoded.
_FAKE_KEY_BYTES = b"\x01" * 32
_FAKE_SECRET_B64 = base64.b64encode(_FAKE_KEY_BYTES).decode()


def test_hmac_key_decodes_base64() -> None:
    creds = MymindCreds(kid="kid1", secret_b64=_FAKE_SECRET_B64)
    assert creds.hmac_key() == _FAKE_KEY_BYTES


def test_hmac_key_rejects_garbage() -> None:
    creds = MymindCreds(kid="kid1", secret_b64="not-base64!!!")
    with pytest.raises(SessionError, match="base64"):
        creds.hmac_key()


def test_sign_request_payload_and_kid() -> None:
    creds = MymindCreds(kid="my-kid", secret_b64=_FAKE_SECRET_B64)
    token = sign_request(creds, method="post", path="/objects", ttl_sec=300, now=1_700_000_000)

    headers = pyjwt.get_unverified_header(token)
    assert headers["kid"] == "my-kid"
    assert headers["alg"] == "HS256"

    # iat is pinned in the past, so disable exp verification just for this
    # assertion -- we test exp enforcement separately below.
    payload = pyjwt.decode(
        token,
        _FAKE_KEY_BYTES,
        algorithms=["HS256"],
        options={"verify_exp": False},
    )
    assert payload["method"] == "POST"  # method must be uppercased
    assert payload["path"] == "/objects"
    assert payload["iat"] == 1_700_000_000
    assert payload["exp"] == 1_700_000_000 + 300


def test_sign_request_expired_token_rejected_by_pyjwt() -> None:
    # Sanity: confirm our exp claim is honored by a standard verifier.
    creds = MymindCreds(kid="k", secret_b64=_FAKE_SECRET_B64)
    token = sign_request(creds, method="POST", path="/x", ttl_sec=1, now=1_000_000_000)
    with pytest.raises(pyjwt.ExpiredSignatureError):
        pyjwt.decode(token, _FAKE_KEY_BYTES, algorithms=["HS256"])


def _headers(raw: str) -> httpx.Headers:
    return httpx.Headers({"RateLimit": raw})


def test_parse_ratelimit_reset_picks_longest_t() -> None:
    # burst exhausted in 12s, sustained in 600s -- must wait for sustained.
    assert parse_ratelimit_reset(_headers("burst;r=0;t=12, sustained;r=0;t=600")) == 600.0


def test_parse_ratelimit_reset_single_bucket() -> None:
    assert parse_ratelimit_reset(_headers("burst;r=5;t=42")) == 42.0


def test_parse_ratelimit_reset_falls_back_to_one_second() -> None:
    # Missing / malformed header -> still produces a sane sleep.
    assert parse_ratelimit_reset(httpx.Headers({})) == 1.0
    assert parse_ratelimit_reset(_headers("garbage;no;t-values")) == 1.0


def test_extract_detail_pulls_rfc9457_field() -> None:
    response = httpx.Response(
        429,
        json={"type": "RateLimited", "title": "Too many", "detail": "Sleep for 600s"},
    )
    assert _extract_detail(response) == "Sleep for 600s"


def test_extract_detail_falls_back_to_title_then_body() -> None:
    response = httpx.Response(429, json={"type": "RateLimited", "title": "Too many"})
    assert _extract_detail(response) == "Too many"

    response = httpx.Response(500, text="upstream exploded")
    assert _extract_detail(response) == "upstream exploded"


# --- MymindClient.create_object (httpx.MockTransport, no real network) -----
#
# These exercise the full retry/status logic against a canned transport. No
# real mymind credentials, no real HTTPS call, no risk of polluting a real
# library. The same `_FAKE_SECRET_B64` above is used to sign + verify the
# bearer JWT each request carries.

_TEST_URL = "https://x.com/jack/status/1"
_CREDS = MymindCreds(kid="kid1", secret_b64=_FAKE_SECRET_B64)


def _seq_handler(
    *responses: httpx.Response,
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    """Return (handler, captured_requests). Handler yields responses in order
    and raises if the client makes more calls than we set up."""
    iterator = iter(responses)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        try:
            return next(iterator)
        except StopIteration:
            raise AssertionError(
                f"unexpected extra request: {request.method} {request.url}"
            ) from None

    return handler, captured


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> MymindClient:
    return MymindClient(
        _CREDS,
        base_url="https://api.mymind.test",
        transport=httpx.MockTransport(handler),
    )


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace asyncio.sleep in mymind_client with a recorder so retry tests
    don't actually wait. Returns the list of sleep durations the SUT requested."""
    sleeps: list[float] = []

    async def _fake(duration: float) -> None:
        sleeps.append(duration)

    monkeypatch.setattr("tomymind.mymind_client.asyncio.sleep", _fake)
    return sleeps


async def test_create_object_201_returns_created() -> None:
    handler, captured = _seq_handler(httpx.Response(201, json={"id": "obj-123"}))
    async with _client(handler) as client:
        result = await client.create_object(url=_TEST_URL, tags=["x"])

    assert result == CreateResult(status=201, url=_TEST_URL)
    assert len(captured) == 1


async def test_create_object_200_returns_existing() -> None:
    # Same URL re-pushed: mymind's native dedup returns 200, no error.
    handler, _ = _seq_handler(httpx.Response(200, json={"id": "obj-existing"}))
    async with _client(handler) as client:
        result = await client.create_object(url=_TEST_URL, tags=[])

    assert result.status == 200
    assert result.detail is None


async def test_create_object_body_wraps_tags_as_name_objects() -> None:
    # Per mymind API: tags must be objects with a `name` key, not bare strings.
    handler, captured = _seq_handler(httpx.Response(201))
    async with _client(handler) as client:
        await client.create_object(url=_TEST_URL, tags=["x", "reading"])

    body = json.loads(captured[0].content)
    assert body == {
        "url": _TEST_URL,
        "tags": [{"name": "x"}, {"name": "reading"}],
    }


async def test_create_object_body_omits_tags_when_empty() -> None:
    handler, captured = _seq_handler(httpx.Response(201))
    async with _client(handler) as client:
        await client.create_object(url=_TEST_URL, tags=[])

    body = json.loads(captured[0].content)
    assert body == {"url": _TEST_URL}
    assert "tags" not in body


async def test_create_object_sends_bearer_jwt_signed_with_creds() -> None:
    handler, captured = _seq_handler(httpx.Response(201))
    async with _client(handler) as client:
        await client.create_object(url=_TEST_URL, tags=[])

    auth = captured[0].headers["Authorization"]
    assert auth.startswith("Bearer ")
    token = auth.removeprefix("Bearer ")
    # The token must verify against the same fake key the client signed with,
    # and the claims must match the request (method + path, no /api prefix).
    payload = pyjwt.decode(token, _FAKE_KEY_BYTES, algorithms=["HS256"])
    assert payload["method"] == "POST"
    assert payload["path"] == "/objects"
    assert pyjwt.get_unverified_header(token)["kid"] == "kid1"


async def test_create_object_posts_to_objects_path() -> None:
    handler, captured = _seq_handler(httpx.Response(201))
    async with _client(handler) as client:
        await client.create_object(url=_TEST_URL, tags=[])

    assert captured[0].method == "POST"
    assert captured[0].url.path == "/objects"


async def test_create_object_429_retries_then_succeeds(no_sleep: list[float]) -> None:
    handler, captured = _seq_handler(
        httpx.Response(429, headers={"RateLimit": "burst;r=0;t=12, sustained;r=0;t=600"}),
        httpx.Response(201),
    )
    async with _client(handler) as client:
        result = await client.create_object(url=_TEST_URL, tags=[])

    assert result.status == 201
    assert len(captured) == 2
    # Must sleep for the slowest exhausted bucket (sustained = 600s), not burst.
    assert no_sleep == [600.0]


async def test_create_object_429_exhausted_returns_status_and_detail(
    no_sleep: list[float],
) -> None:
    # max_429_retries=2 → 1 initial call + 2 retries = 3 responses to feed.
    handler, captured = _seq_handler(
        *(
            httpx.Response(
                429,
                headers={"RateLimit": "burst;r=0;t=1"},
                json={"type": "RateLimited", "detail": "Too many requests"},
            )
            for _ in range(3)
        )
    )
    async with _client(handler) as client:
        result = await client.create_object(url=_TEST_URL, tags=[], max_429_retries=2)

    assert result.status == 429
    assert result.detail == "Too many requests"
    assert len(captured) == 3


async def test_create_object_5xx_retries_with_exponential_backoff(
    no_sleep: list[float],
) -> None:
    handler, captured = _seq_handler(
        httpx.Response(500),
        httpx.Response(502),
        httpx.Response(201),
    )
    async with _client(handler) as client:
        result = await client.create_object(url=_TEST_URL, tags=[])

    assert result.status == 201
    assert len(captured) == 3
    # First retry waits 2s, second 4s (exponential).
    assert no_sleep == [2.0, 4.0]


async def test_create_object_5xx_exhausted_returns_status(no_sleep: list[float]) -> None:
    handler, _ = _seq_handler(*(httpx.Response(503, text="upstream exploded") for _ in range(4)))
    async with _client(handler) as client:
        result = await client.create_object(url=_TEST_URL, tags=[], max_5xx_retries=3)

    assert result.status == 503
    assert result.detail == "upstream exploded"
    # 3 retries means we slept 3 times, with the 2s/4s/8s exponential cadence.
    assert no_sleep == [2.0, 4.0, 8.0]


async def test_create_object_4xx_returns_immediately_with_detail() -> None:
    # 4xx (other than 429) must NOT retry — would just waste credits/time.
    handler, captured = _seq_handler(
        httpx.Response(
            400,
            json={"type": "BadRequest", "detail": "Pick exactly one of url, content, blob"},
        )
    )
    async with _client(handler) as client:
        result = await client.create_object(url=_TEST_URL, tags=[])

    assert result.status == 400
    assert result.detail == "Pick exactly one of url, content, blob"
    assert len(captured) == 1


async def test_create_object_401_surfaces_rfc9457_detail() -> None:
    handler, _ = _seq_handler(
        httpx.Response(
            401,
            json={"type": "Unauthorized", "title": "Bad signature", "detail": "kid not found"},
        )
    )
    async with _client(handler) as client:
        result = await client.create_object(url=_TEST_URL, tags=[])

    assert result.status == 401
    assert result.detail == "kid not found"
