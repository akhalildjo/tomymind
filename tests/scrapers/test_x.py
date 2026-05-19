from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from tomymind.scrapers.x import XScraper

parse = XScraper._parse_tweet_href


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


class TestScrapeTimeoutDiagnostic:
    async def test_warns_to_stderr_and_yields_nothing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scraper = XScraper()
        page = _make_page(
            selector_side_effect=PlaywrightTimeoutError("simulated timeout"),
        )

        items = [item async for item in scraper.scrape(page)]

        assert items == []
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "no tweets found within 20s" in captured.err
        assert "https://x.com/i/bookmarks" in captured.err
        assert "tomymind login x" in captured.err

    async def test_non_timeout_exception_propagates(self) -> None:
        scraper = XScraper()
        page = _make_page(
            selector_side_effect=RuntimeError("browser crashed"),
        )

        with pytest.raises(RuntimeError, match="browser crashed"):
            async for _ in scraper.scrape(page):
                pass


class TestScrapePacing:
    """Lock in the v0.1.1 anti-automation pacing: initial dwell, jittered
    scroll pause, jittered scroll distance. Without this test, the
    sleep/evaluate wiring could regress (e.g. somebody reverting to a
    fixed pause) and the only existing tests cover the parse helper and
    the timeout early-exit, neither of which would catch it."""

    async def test_jittered_pacing_and_yields_tweet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        scraper = XScraper()
        # One non-yielding pass is enough to end the loop and exercise
        # the scroll step, while keeping the test cheap.
        scraper._idle_scroll_limit = 1

        # Pin randomness: always return the upper bound of each range so
        # the test asserts exact values without depending on call order.
        def fake_uniform(lo: float, hi: float) -> float:
            return hi

        monkeypatch.setattr("tomymind.scrapers.x.random.uniform", fake_uniform)

        sleeps: list[float] = []

        async def fake_sleep(sec: float) -> None:
            sleeps.append(sec)

        monkeypatch.setattr("tomymind.scrapers.x.asyncio.sleep", fake_sleep)

        anchor = MagicMock()
        anchor.get_attribute = AsyncMock(return_value="/jack/status/12345")
        article = MagicMock()
        article.query_selector_all = AsyncMock(return_value=[anchor])

        evaluate_calls: list[str] = []

        async def fake_evaluate(expr: str) -> int:
            evaluate_calls.append(expr)
            # Stable scrollHeight across passes → idle increments on pass 2.
            return 1000

        page = MagicMock()
        page.url = "https://x.com/i/bookmarks"
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[article])
        page.evaluate = AsyncMock(side_effect=fake_evaluate)

        items = [item async for item in scraper.scrape(page)]

        # Tweet was yielded unchanged by the pacing logic.
        assert len(items) == 1
        assert items[0].source_item_id == "12345"
        assert str(items[0].url) == "https://x.com/jack/status/12345"

        # Pass 1 yields the tweet (no idle increment); pass 2 sees the
        # same tweet (skipped via seen_ids) on an unchanged height
        # (idle=1, loop exits). So we get 1 initial dwell + 2 scroll
        # pauses.
        dwell_hi = scraper._initial_dwell_range_sec[1]
        pause_hi = scraper._scroll_pause_range_sec[1]
        assert sleeps == [dwell_hi, pause_hi, pause_hi]

        # Both scroll iterations issued a randomized scrollBy.
        scroll_calls = [c for c in evaluate_calls if "scrollBy" in c]
        distance_hi = scraper._scroll_distance_range[1]
        expected = f"window.scrollBy(0, window.innerHeight * {distance_hi})"
        assert scroll_calls == [expected, expected]
