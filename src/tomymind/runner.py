from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from .errors import SessionError
from .models import BookmarkItem, ScrapeResult
from .scrapers._base import BaseScraper

__all__ = ["SessionError", "run_login", "run_scrape"]


async def run_login(scraper: BaseScraper) -> None:
    """Open a non-headless browser so the user can log in, then persist the session."""
    scraper.session_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        await scraper.on_context_ready(context)
        page = await context.new_page()
        await page.goto(scraper.login_url, wait_until="domcontentloaded")

        print(f"\n  Connecte-toi à '{scraper.name}' dans la fenêtre qui vient de s'ouvrir.")
        print("  Quand tu vois ton fil/feed connecté, reviens ici et appuie sur ENTRÉE.\n")
        await asyncio.to_thread(input)

        await page.goto(scraper.home_url, wait_until="domcontentloaded")
        if not await scraper.is_logged_in(page):
            await browser.close()
            raise SessionError(
                f"Session non détectée pour '{scraper.name}'. "
                "Vérifie que tu es bien connecté puis relance la commande."
            )

        await context.storage_state(path=str(scraper.session_path))
        await browser.close()

    print(f"  Session sauvegardée → {scraper.session_path}")


async def run_scrape(
    scraper: BaseScraper,
    limit: int | None,
    output_path: Path,
    headless: bool = True,
) -> ScrapeResult:
    """Load the saved session and run the scraper, then dump results to JSON."""
    if not scraper.session_path.exists():
        raise SessionError(
            f"Aucune session pour '{scraper.name}'. Lance d'abord : tomymind login {scraper.name}"
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(storage_state=str(scraper.session_path))
        await scraper.on_context_ready(context)
        page = await context.new_page()

        await page.goto(scraper.home_url, wait_until="domcontentloaded")
        if not await scraper.is_logged_in(page):
            await browser.close()
            raise SessionError(
                f"Session expirée pour '{scraper.name}'. Relance : tomymind login {scraper.name}"
            )

        items: list[BookmarkItem] = []
        try:
            async for item in scraper.scrape(page, limit=limit):
                items.append(item)
                print(f"  [{len(items):>4}] {item.url}")
        finally:
            await browser.close()

    result = ScrapeResult(source=scraper.name, item_count=len(items), items=items)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        result.model_dump_json(by_alias=True, indent=2, exclude_none=True),
        encoding="utf-8",
    )
    return result
