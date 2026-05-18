from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from tomymind.sources.x import XSource

parse = XSource._parse_tweet_href


class TestParseTweetHrefMatches:
    @pytest.mark.parametrize(
        ("href", "expected"),
        [
            ("/jack/status/12345", ("jack", "12345")),
            ("/jack/status/12345/", ("jack", "12345")),
            ("/jack/status/12345?lang=en", ("jack", "12345")),
            ("/jack/status/12345/photo/1", ("jack", "12345")),
            ("/jack/status/12345/video/1", ("jack", "12345")),
            ("/jack/status/12345/analytics", ("jack", "12345")),
            ("/jack/status/12345/quotes", ("jack", "12345")),
            ("/jack/status/12345/retweets", ("jack", "12345")),
            ("/jack/status/12345/likes", ("jack", "12345")),
            ("/some_user_123/status/12345", ("some_user_123", "12345")),
            ("/user42/status/1234567890123456789", ("user42", "1234567890123456789")),
        ],
    )
    def test_relative_paths(self, href: str, expected: tuple[str, str]) -> None:
        assert parse(href) == expected

    @pytest.mark.parametrize(
        "href",
        [
            "https://x.com/jack/status/12345",
            "https://twitter.com/jack/status/12345",
            "https://www.x.com/jack/status/12345",
            "https://www.twitter.com/jack/status/12345",
            "http://x.com/jack/status/12345",
        ],
    )
    def test_accepted_hosts(self, href: str) -> None:
        assert parse(href) == ("jack", "12345")

    def test_host_case_insensitive(self) -> None:
        assert parse("https://X.com/jack/status/12345") == ("jack", "12345")
        assert parse("https://Twitter.COM/jack/status/12345") == ("jack", "12345")


class TestParseTweetHrefRejects:
    @pytest.mark.parametrize(
        "href",
        [
            "",
            "/",
            "/jack",
            "/jack/",
            "/jack/status",
            "/jack/status/",
            "/jack/status/abc",
            "/jack/status/12a45",
            "/jack/STATUS/12345",
            "/i/bookmarks",
            "/i/flow/login",
            "/home",
            "/explore",
            "/settings",
        ],
    )
    def test_non_tweet_paths(self, href: str) -> None:
        assert parse(href) is None

    @pytest.mark.parametrize(
        "user",
        ["i", "home", "messages", "notifications", "compose", "search"],
    )
    def test_reserved_usernames(self, user: str) -> None:
        assert parse(f"/{user}/status/12345") is None

    @pytest.mark.parametrize(
        "href",
        [
            "https://example.com/jack/status/12345",
            "https://malicious.com/jack/status/12345",
            "https://x.com.malicious.com/jack/status/12345",
            "https://fake-x.com/jack/status/12345",
            "https://mobile.twitter.com/jack/status/12345",
            "//jack/status/12345",
        ],
    )
    def test_foreign_hosts(self, href: str) -> None:
        assert parse(href) is None

    def test_host_with_port_rejected(self) -> None:
        # Netloc with port doesn't match _X_HOSTS — documents current behavior.
        # Real X anchors never carry a port, so this is acceptable.
        assert parse("https://x.com:443/jack/status/12345") is None


def _make_page(url: str = "https://x.com/i/bookmarks", *, selector_side_effect):
    page = MagicMock()
    page.url = url
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock(side_effect=selector_side_effect)
    return page


class TestFetchTimeoutDiagnostic:
    async def test_warns_to_stderr_and_yields_nothing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = XSource()
        page = _make_page(
            selector_side_effect=PlaywrightTimeoutError("simulated timeout"),
        )

        items = [item async for item in source.fetch(page)]

        assert items == []
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "no tweets found within 20s" in captured.err
        assert "https://x.com/i/bookmarks" in captured.err
        assert "tomymind login x" in captured.err

    async def test_non_timeout_exception_propagates(self) -> None:
        source = XSource()
        page = _make_page(
            selector_side_effect=RuntimeError("browser crashed"),
        )

        with pytest.raises(RuntimeError, match="browser crashed"):
            async for _ in source.fetch(page):
                pass
