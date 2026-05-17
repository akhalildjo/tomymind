from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from ..models import BookmarkItem


class BaseScraper(ABC):
    """Common interface every source scraper implements.

    Subclasses set the class attributes and implement `is_logged_in` and `scrape`.
    """

    name: str
    login_url: str
    home_url: str
    # Optional URL hit before login_url so the server seeds bootstrap cookies
    # (guest tokens, CSRF, etc.) that the login API expects. None = skip.
    warmup_url: str | None = None

    @property
    def session_path(self) -> Path:
        # Persistent Chrome profile dir for this source. Cookies, localStorage
        # and the whole user_data_dir live here so anti-bot sees a returning
        # Chrome user rather than a fresh Playwright launch.
        return Path("sessions") / self.name

    @abstractmethod
    async def is_logged_in(self, page: Page) -> bool:
        """Return True if the current page indicates an active session."""

    @abstractmethod
    async def scrape(self, page: Page, limit: int | None = None) -> AsyncIterator[BookmarkItem]:
        """Yield bookmarks one by one. Stop when limit is reached or source is exhausted."""
        if False:  # pragma: no cover
            yield  # makes the body a valid async generator

    async def on_context_ready(self, context: BrowserContext) -> None:
        """Hook for subclasses to set extra headers, cookies or context-wide options."""
        return None

    async def on_page_ready(self, page: Page) -> None:
        """Hook called after the first page is created and before any navigation.

        Use it for page-level patches that must be in place before the page
        fetches any script — e.g. tf-playwright-stealth init scripts.
        """
        return None
