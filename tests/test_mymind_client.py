from __future__ import annotations

import base64

import httpx
import jwt as pyjwt
import pytest

from tomymind.errors import SessionError
from tomymind.mymind_client import (
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
