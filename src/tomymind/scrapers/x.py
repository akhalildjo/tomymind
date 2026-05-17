from __future__ import annotations

import asyncio
import re
import sys
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ..errors import SessionError
from ..models import BookmarkItem
from ._base import BaseScraper

_TWEET_PATH_RE = re.compile(r"^/([^/]+)/status/(\d+)(?:/|$|\?)")
_X_HOSTS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com", ""}


class XScraper(BaseScraper):
    name = "x"
    login_url = "https://x.com/i/flow/login"
    home_url = "https://x.com/home"
    bookmarks_url = "https://x.com/i/bookmarks"
    # Visiting the root first builds up guest_id / gt / ct0 cookies. Without
    # them /i/flow/login gets a 400 on onboarding/task.json.
    warmup_url = "https://x.com/"
    # Cookies the user can paste from a logged-in Chrome to skip login.
    # auth_token is the session bearer; ct0 is the CSRF token X embeds in
    # every authenticated XHR. With both, X treats us as the logged-in user.
    cookie_import_domain = ".x.com"
    cookie_import_specs = {
        "auth_token": {"httpOnly": True, "sameSite": "None"},
        "ct0": {"httpOnly": False, "sameSite": "Lax"},
    }

    # Stop after this many consecutive scrolls that don't reveal new content.
    _idle_scroll_limit = 5
    _scroll_pause_sec = 1.8

    async def on_page_ready(self, page: Page) -> None:
        # X aggressively fingerprints Playwright. tf-playwright-stealth patches
        # navigator.webdriver, plugins, languages, WebGL and other tells via an
        # init script that runs before any page JS. Requires `--extra stealth`.
        try:
            from playwright_stealth import stealth_async
        except ImportError as exc:
            raise SessionError(
                "X requires the 'stealth' extra to bypass anti-bot detection. "
                "Run: uv sync --extra scraper --extra stealth"
            ) from exc
        await stealth_async(page)

    async def is_logged_in(self, page: Page) -> bool:
        try:
            await page.wait_for_selector(
                '[data-testid="AppTabBar_Home_Link"], [data-testid="primaryColumn"]',
                timeout=10000,
            )
        except Exception:
            return False
        return "/login" not in page.url and "/i/flow/login" not in page.url

    async def scrape(self, page: Page, limit: int | None = None) -> AsyncIterator[BookmarkItem]:
        await page.goto(self.bookmarks_url, wait_until="domcontentloaded")

        if "/login" in page.url or "/i/flow/login" in page.url:
            raise SessionError(
                f"Session expired for '{self.name}'. Re-run: tomymind login {self.name}"
            )

        try:
            await page.wait_for_selector('article[data-testid="tweet"]', timeout=20000)
        except PlaywrightTimeoutError:
            print(
                f"  warning: no tweets found within 20s on {page.url!r}. "
                "Possible causes: empty bookmarks, expired session, or X DOM change. "
                "Re-run `tomymind login x` to refresh the session, "
                "or `tomymind scrape x --show-browser` to inspect visually.",
                file=sys.stderr,
            )
            return

        seen_ids: set[str] = set()
        idle = 0
        last_height = 0

        while idle < self._idle_scroll_limit:
            articles = await page.query_selector_all('article[data-testid="tweet"]')
            new_in_pass = 0

            for article in articles:
                anchors = await article.query_selector_all('a[href*="/status/"]')
                for anchor in anchors:
                    href = await anchor.get_attribute("href")
                    if not href:
                        continue
                    parsed = self._parse_tweet_href(href)
                    if not parsed:
                        continue
                    user, tweet_id = parsed
                    if tweet_id in seen_ids:
                        continue
                    canonical = urlunparse(
                        ("https", "x.com", f"/{user}/status/{tweet_id}", "", "", "")
                    )
                    seen_ids.add(tweet_id)
                    new_in_pass += 1
                    yield BookmarkItem(
                        source_item_id=tweet_id,
                        url=canonical,
                        suggested_tags=["x"],
                        raw_metadata={"capturedFrom": "bookmarks"},
                    )
                    if limit and len(seen_ids) >= limit:
                        return
                    break  # one canonical link per article

            height = await page.evaluate("document.documentElement.scrollHeight")
            if height == last_height and new_in_pass == 0:
                idle += 1
            else:
                idle = 0
            last_height = height
            await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            await asyncio.sleep(self._scroll_pause_sec)

    @staticmethod
    def _parse_tweet_href(href: str) -> tuple[str, str] | None:
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc.lower() not in _X_HOSTS:
            return None
        m = _TWEET_PATH_RE.match(parsed.path)
        if not m:
            return None
        user, tweet_id = m.group(1), m.group(2)
        if user in {"i", "home", "messages", "notifications", "compose", "search"}:
            return None
        return user, tweet_id
