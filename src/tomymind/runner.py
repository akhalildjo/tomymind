from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import BrowserContext, async_playwright

from .errors import SessionError
from .models import BookmarkItem, ScrapeResult
from .scrapers._base import BaseScraper

__all__ = ["SessionError", "run_import_cookies", "run_login", "run_scrape"]

# Renderer-level AutomationControlled feature is the cheap tell anti-bot
# stacks key on. Stealth patches (per-scraper, in on_page_ready) cover the
# JS-level tells, this kills the C++ one.
_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]

# Realistic browser context. With channel="chrome" we DON'T spoof the UA —
# real Chrome already sends a Chrome UA that matches its actual major
# version and its Client Hints (Sec-CH-UA). Overriding it creates a
# mismatch that's trivially detectable. We only spoof the UA when we
# fall back to bundled Chromium (which otherwise advertises itself).
_CHROME_CONTEXT_OPTIONS: dict = {
    "viewport": {"width": 1280, "height": 800},
    "locale": "en-US",
}
_CHROMIUM_FALLBACK_CONTEXT_OPTIONS: dict = {
    **_CHROME_CONTEXT_OPTIONS,
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


async def _launch_persistent(p, scraper: BaseScraper, headless: bool) -> BrowserContext:
    """Open a persistent context backed by a per-source profile directory.

    Tries the system Chrome binary first (channel='chrome') so we get a real
    Chrome fingerprint with matching UA + Client Hints. Falls back to
    Playwright's bundled Chromium with a one-time warning if Chrome isn't
    installed (and spoofs a Chrome UA in that case since Chromium's default
    UA is otherwise a giveaway).
    """
    base: dict = {
        "user_data_dir": str(scraper.session_path),
        "headless": headless,
        "args": _LAUNCH_ARGS,
    }
    try:
        return await p.chromium.launch_persistent_context(
            channel="chrome", **base, **_CHROME_CONTEXT_OPTIONS
        )
    except Exception:
        print(
            "  note: system Chrome not found, falling back to bundled Chromium. "
            "Anti-bot detection is weaker against bundled Chromium — install "
            "Google Chrome for the best results.",
            file=sys.stderr,
        )
        return await p.chromium.launch_persistent_context(
            **base, **_CHROMIUM_FALLBACK_CONTEXT_OPTIONS
        )


def _first_page(context: BrowserContext):
    # launch_persistent_context auto-opens an about:blank page; reuse it.
    return context.pages[0] if context.pages else None


async def run_login(scraper: BaseScraper) -> None:
    """Open a visible browser so the user can log in. Profile persists for later scrapes."""
    scraper.session_path.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await _launch_persistent(p, scraper, headless=False)
        try:
            await scraper.on_context_ready(context)
            page = _first_page(context) or await context.new_page()
            await scraper.on_page_ready(page)

            # Warmup: hit the source's root so the server hands us the
            # bootstrap cookies (guest_id, gt, ct0 ...) that the login API
            # checks. Going straight to /i/flow/login without these is what
            # makes X return 400 on onboarding/task.json.
            if scraper.warmup_url:
                await page.goto(scraper.warmup_url, wait_until="domcontentloaded")
                await asyncio.sleep(2)

            await page.goto(scraper.login_url, wait_until="domcontentloaded")

            print(f"\n  Connecte-toi à '{scraper.name}' dans la fenêtre qui vient de s'ouvrir.")
            print("  Quand tu vois ton fil/feed connecté, reviens ici et appuie sur ENTRÉE.\n")
            await asyncio.to_thread(input)

            await page.goto(scraper.home_url, wait_until="domcontentloaded")
            if not await scraper.is_logged_in(page):
                raise SessionError(
                    f"Session non détectée pour '{scraper.name}'. "
                    "Vérifie que tu es bien connecté puis relance la commande."
                )
        finally:
            await context.close()

    print(f"  Profil Chrome sauvegardé → {scraper.session_path}")


async def run_scrape(
    scraper: BaseScraper,
    limit: int | None,
    output_path: Path,
    headless: bool = True,
) -> ScrapeResult:
    """Load the saved Chrome profile and run the scraper, then dump results to JSON."""
    if not scraper.session_path.exists() or not any(scraper.session_path.iterdir()):
        raise SessionError(
            f"Aucune session pour '{scraper.name}'. Lance d'abord : tomymind login {scraper.name}"
        )

    items: list[BookmarkItem] = []
    async with async_playwright() as p:
        context = await _launch_persistent(p, scraper, headless=headless)
        try:
            await scraper.on_context_ready(context)
            page = _first_page(context) or await context.new_page()
            await scraper.on_page_ready(page)

            await page.goto(scraper.home_url, wait_until="domcontentloaded")
            if not await scraper.is_logged_in(page):
                raise SessionError(
                    f"Session expirée pour '{scraper.name}'. "
                    f"Relance : tomymind login {scraper.name}"
                )

            async for item in scraper.scrape(page, limit=limit):
                items.append(item)
                print(f"  [{len(items):>4}] {item.url}")
        finally:
            await context.close()

    result = ScrapeResult(source=scraper.name, item_count=len(items), items=items)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        result.model_dump_json(by_alias=True, indent=2, exclude_none=True),
        encoding="utf-8",
    )
    return result


async def run_import_cookies(scraper: BaseScraper) -> None:
    """Seed the persistent profile with cookies copied from a logged-in browser.

    Bypasses the login UI entirely — useful when the source's anti-bot stack
    refuses to let an automated browser through the login flow but accepts
    valid session cookies as-is.
    """
    if not scraper.cookie_import_specs or not scraper.cookie_import_domain:
        raise SessionError(f"'{scraper.name}' doesn't support cookie import yet.")

    host = scraper.cookie_import_domain.lstrip(".")
    print(f"\n  Import cookies pour '{scraper.name}'.")
    print(f"  Dans ton Chrome déjà connecté : F12 → Application → Cookies → https://{host}")
    print("  Copie la valeur de chaque cookie ci-dessous puis colle-la ici.\n")

    cookies_to_add: list[dict] = []
    for name, extra in scraper.cookie_import_specs.items():
        value = (await asyncio.to_thread(input, f"  {name} = ")).strip()
        if not value:
            raise SessionError(f"Valeur vide pour '{name}', abandon.")
        cookies_to_add.append(
            {
                "name": name,
                "value": value,
                "domain": scraper.cookie_import_domain,
                "path": "/",
                "secure": True,
                **extra,
            }
        )

    scraper.session_path.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        context = await _launch_persistent(p, scraper, headless=True)
        try:
            await context.add_cookies(cookies_to_add)
        finally:
            await context.close()

    print(f"\n  Cookies enregistrés dans le profil → {scraper.session_path}")
    print(f"  Tu peux maintenant scraper : tomymind scrape {scraper.name}")
