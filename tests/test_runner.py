from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tomymind.errors import SessionError
from tomymind.models import BookmarkItem
from tomymind.runner import run_import_cookies, run_login, run_scrape
from tomymind.scrapers._base import BaseScraper


class _FakeScraper(BaseScraper):
    name = "fake"
    login_url = "https://example.com/login"
    home_url = "https://example.com/home"
    warmup_url = None
    cookie_import_domain = ""
    cookie_import_specs: dict[str, dict] = {}

    def __init__(
        self,
        session_dir: Path,
        *,
        logged_in: bool = True,
        items: list[BookmarkItem] | None = None,
    ) -> None:
        self._session_dir = session_dir
        self._logged_in = logged_in
        self._items = items or []

    @property
    def session_path(self) -> Path:
        return self._session_dir

    async def is_logged_in(self, page) -> bool:  # noqa: ARG002
        return self._logged_in

    async def scrape(self, page, limit=None) -> AsyncIterator[BookmarkItem]:  # noqa: ARG002
        for item in self._items:
            yield item


class _CookieScraper(_FakeScraper):
    cookie_import_domain = ".example.com"
    cookie_import_specs = {"auth": {"httpOnly": True, "sameSite": "Lax"}}


def _make_context_and_page() -> tuple[MagicMock, MagicMock]:
    page = MagicMock()
    page.goto = AsyncMock()
    context = MagicMock()
    context.pages = [page]
    context.new_page = AsyncMock(return_value=page)
    context.add_cookies = AsyncMock()
    context.close = AsyncMock()
    return context, page


def _patch_playwright(context: MagicMock):
    """Patch `runner.async_playwright` to yield a stub Playwright that returns `context`."""
    p_mock = MagicMock()
    p_mock.chromium.launch_persistent_context = AsyncMock(return_value=context)
    pw_ctx = MagicMock()
    pw_ctx.__aenter__ = AsyncMock(return_value=p_mock)
    pw_ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("tomymind.runner.async_playwright", return_value=pw_ctx)


# --- run_scrape ----------------------------------------------------------


async def test_run_scrape_missing_session_dir_raises(tmp_path: Path) -> None:
    scraper = _FakeScraper(session_dir=tmp_path / "nope")
    with pytest.raises(SessionError, match="No session for 'fake'"):
        await run_scrape(scraper, limit=None, output_path=tmp_path / "out.json")


async def test_run_scrape_empty_session_dir_raises(tmp_path: Path) -> None:
    empty = tmp_path / "session"
    empty.mkdir()
    scraper = _FakeScraper(session_dir=empty)
    with pytest.raises(SessionError, match="No session for 'fake'"):
        await run_scrape(scraper, limit=None, output_path=tmp_path / "out.json")


async def test_run_scrape_session_expired_raises(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    (session / "marker").write_text("x", encoding="utf-8")
    scraper = _FakeScraper(session_dir=session, logged_in=False)
    context, _ = _make_context_and_page()

    with _patch_playwright(context), pytest.raises(SessionError, match="expired for 'fake'"):
        await run_scrape(scraper, limit=None, output_path=tmp_path / "out.json")


async def test_run_scrape_writes_json_output(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    (session / "marker").write_text("x", encoding="utf-8")
    items = [
        BookmarkItem(
            source_item_id="111",
            url="https://x.com/jack/status/111",
            suggested_tags=["x"],
        ),
        BookmarkItem(
            source_item_id="222",
            url="https://x.com/jack/status/222",
            suggested_tags=["x"],
        ),
    ]
    scraper = _FakeScraper(session_dir=session, items=items)
    output = tmp_path / "out.json"
    context, _ = _make_context_and_page()

    with _patch_playwright(context):
        result = await run_scrape(scraper, limit=None, output_path=output)

    assert result.item_count == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"] == "fake"
    assert payload["itemCount"] == 2
    assert {it["sourceItemId"] for it in payload["items"]} == {"111", "222"}
    context.close.assert_awaited_once()


async def test_run_scrape_creates_parent_dir(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    (session / "marker").write_text("x", encoding="utf-8")
    scraper = _FakeScraper(session_dir=session, items=[])
    output = tmp_path / "nested" / "deep" / "out.json"
    context, _ = _make_context_and_page()

    with _patch_playwright(context):
        await run_scrape(scraper, limit=None, output_path=output)

    assert output.exists()


# --- run_import_cookies --------------------------------------------------


async def test_run_import_cookies_unsupported_source_raises(tmp_path: Path) -> None:
    scraper = _FakeScraper(session_dir=tmp_path / "session")
    with pytest.raises(SessionError, match="doesn't support cookie import"):
        await run_import_cookies(scraper)


async def test_run_import_cookies_empty_value_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scraper = _CookieScraper(session_dir=tmp_path / "session")
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "   ")
    with pytest.raises(SessionError, match="Empty value for 'auth'"):
        await run_import_cookies(scraper)


async def test_run_import_cookies_verification_failure_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scraper = _CookieScraper(session_dir=tmp_path / "session", logged_in=False)
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "tok")
    context, _ = _make_context_and_page()

    with _patch_playwright(context), pytest.raises(SessionError, match="don't grant access"):
        await run_import_cookies(scraper)
    context.add_cookies.assert_awaited_once()


async def test_run_import_cookies_happy_path_adds_cookies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scraper = _CookieScraper(session_dir=tmp_path / "session", logged_in=True)
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "tok")
    context, _ = _make_context_and_page()

    with _patch_playwright(context):
        await run_import_cookies(scraper)

    context.add_cookies.assert_awaited_once()
    [cookies] = context.add_cookies.call_args.args
    assert len(cookies) == 1
    assert cookies[0]["name"] == "auth"
    assert cookies[0]["value"] == "tok"
    assert cookies[0]["domain"] == ".example.com"
    assert cookies[0]["path"] == "/"
    assert cookies[0]["secure"] is True
    assert cookies[0]["httpOnly"] is True
    assert cookies[0]["expires"] > 0
    context.close.assert_awaited_once()


# --- run_login -----------------------------------------------------------


async def test_run_login_session_not_detected_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scraper = _FakeScraper(session_dir=tmp_path / "session", logged_in=False)
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "")
    context, _ = _make_context_and_page()

    with (
        _patch_playwright(context),
        pytest.raises(SessionError, match="Session not detected for 'fake'"),
    ):
        await run_login(scraper)


async def test_run_login_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scraper = _FakeScraper(session_dir=tmp_path / "session", logged_in=True)
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "")
    context, page = _make_context_and_page()

    with _patch_playwright(context):
        await run_login(scraper)

    page.goto.assert_awaited()
    context.close.assert_awaited_once()
    assert (tmp_path / "session").exists()
