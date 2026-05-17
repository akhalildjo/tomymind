"""Async client for the mymind.com REST API.

Signs an HS256 JWT per request (kid header, plus path / method / iat / exp
claims), retries 429 with the RateLimit-aware sleep mymind asks for, and
exponential-backs-off 5xx. POST /objects is the only endpoint we use
today; the client is shaped so adding GET /objects or /search later is
a few-line addition.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import time
from dataclasses import dataclass

import httpx
import jwt as pyjwt

from . import __version__
from .errors import SessionError

DEFAULT_BASE_URL = "https://api.mymind.com"
_USER_AGENT = f"tomymind/{__version__} (https://github.com/akhalildjo/tomymind)"
_DEFAULT_TTL_SEC = 300


@dataclass(frozen=True)
class MymindCreds:
    """HS256 key material. `secret_b64` is the base64-encoded 32-byte key
    mymind issues in the dashboard -- we decode it once into HMAC bytes."""

    kid: str
    secret_b64: str

    def hmac_key(self) -> bytes:
        try:
            return base64.b64decode(self.secret_b64, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise SessionError(
                "MYMIND_SECRET must be base64 (the value copied from your "
                "mymind dashboard, which typically ends with '=')."
            ) from exc


@dataclass(frozen=True)
class CreateResult:
    """Outcome of one POST /objects call.

    `status`: 201 = freshly created, 200 = mymind already had this URL
    (native dedup, refreshed bumped timestamp), anything else = error.
    `detail` is populated on errors (RFC 9457 `detail` field if present,
    else the first 200 chars of the response body).
    """

    status: int
    url: str
    detail: str | None = None


def sign_request(
    creds: MymindCreds,
    *,
    method: str,
    path: str,
    ttl_sec: int = _DEFAULT_TTL_SEC,
    now: int | None = None,
) -> str:
    """Build a per-request bearer JWT.

    `now` lets tests pin the clock; production calls pass None so we use
    real time.
    """
    issued = int(time.time()) if now is None else now
    payload = {
        "method": method.upper(),
        "path": path,
        "iat": issued,
        "exp": issued + ttl_sec,
    }
    return pyjwt.encode(
        payload,
        creds.hmac_key(),
        algorithm="HS256",
        headers={"kid": creds.kid},
    )


def parse_ratelimit_reset(headers: httpx.Headers) -> float:
    """Pick the longest `t=` value from mymind's RateLimit header.

    mymind sends e.g. `RateLimit: burst;r=0;t=12, sustained;r=0;t=600`.
    We must wait for the slowest exhausted bucket. Returns at least 1.0s
    so a malformed header still produces a sane retry cadence.
    """
    raw = headers.get("RateLimit") or headers.get("RateLimit-Policy") or ""
    worst = 0.0
    for chunk in raw.split(","):
        for kv in chunk.split(";"):
            kv = kv.strip()
            if kv.startswith("t="):
                with contextlib.suppress(ValueError):
                    worst = max(worst, float(kv[2:]))
    return max(worst, 1.0)


class MymindClient:
    """Async wrapper. Use as an async context manager."""

    def __init__(
        self,
        creds: MymindCreds,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_sec: float = 30.0,
    ):
        self._creds = creds
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_sec,
            headers={"User-Agent": _USER_AGENT},
        )

    async def __aenter__(self) -> MymindClient:
        return self

    async def __aexit__(self, *_exc) -> None:
        await self._http.aclose()

    async def create_object(
        self,
        *,
        url: str,
        tags: list[str],
        max_429_retries: int = 4,
        max_5xx_retries: int = 3,
    ) -> CreateResult:
        path = "/objects"
        body = {"url": url}
        if tags:
            body["tags"] = [{"name": t} for t in tags]

        attempts_429 = 0
        attempts_5xx = 0
        backoff_5xx = 2.0

        while True:
            token = sign_request(self._creds, method="POST", path=path)
            response = await self._http.post(
                path,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )

            if response.status_code in (200, 201):
                return CreateResult(status=response.status_code, url=url)

            if response.status_code == 429 and attempts_429 < max_429_retries:
                attempts_429 += 1
                await asyncio.sleep(parse_ratelimit_reset(response.headers))
                continue

            if 500 <= response.status_code < 600 and attempts_5xx < max_5xx_retries:
                attempts_5xx += 1
                await asyncio.sleep(backoff_5xx)
                backoff_5xx *= 2
                continue

            return CreateResult(
                status=response.status_code,
                url=url,
                detail=_extract_detail(response),
            )


def _extract_detail(response: httpx.Response) -> str:
    """Pull the human-readable error blurb out of mymind's RFC 9457 body."""
    try:
        problem = response.json()
        if isinstance(problem, dict):
            for key in ("detail", "title", "type"):
                if problem.get(key):
                    return str(problem[key])
    except (ValueError, httpx.DecodingError):
        pass
    return response.text[:200]
