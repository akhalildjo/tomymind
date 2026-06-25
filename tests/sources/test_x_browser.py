from __future__ import annotations

import pytest
from playwright.async_api import Route, async_playwright

from tomymind.sources.x import XSource

# A trimmed stand-in for the X bookmarks DOM: two genuine tweet articles plus
# two decoys (a reserved /i/ "status" link and a non-status link) so the smoke
# test proves the live selector + parse path filters exactly like production.
_FIXTURE_HTML = """\
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Bookmarks</title></head>
  <body>
    <div data-testid="primaryColumn">
      <article data-testid="tweet">
        <a href="/jack/status/111">permalink</a>
        <a href="/jack/status/111/photo/1">photo</a>
      </article>
      <article data-testid="tweet">
        <a href="/alice/status/222?lang=en">permalink</a>
      </article>
      <article data-testid="tweet">
        <a href="/i/status/333">reserved-user decoy, must be ignored</a>
      </article>
      <article data-testid="tweet">
        <a href="/explore">non-status decoy, must be ignored</a>
      </article>
    </div>
  </body>
</html>
"""

# Whole module needs a real browser; the default run and the unit-test CI
# matrix deselect it (see pyproject `addopts = -m 'not browser'`).
pytestmark = pytest.mark.browser


async def test_fetch_drives_real_chromium_and_stealth_applies() -> None:
    """End-to-end smoke test against a real headless Chromium. It hits no
    network: `page.route` fulfills the bookmarks URL from a local fixture, so
    it never touches real x.com (per CLAUDE.md's no-live-E2E rule). This is the
    one test that actually exercises the playwright + playwright-stealth
    integration, so a dependency bump that breaks either turns this red instead
    of sailing through the mock-based unit suite."""
    source = XSource()
    # Strip the anti-automation pacing so the smoke test is fast and
    # deterministic; the jitter wiring itself is covered by the unit suite.
    source._idle_scroll_limit = 1
    source._initial_dwell_range_sec = (0.0, 0.0)
    source._scroll_pause_range_sec = (0.0, 0.0)

    async def serve_fixture(route: Route) -> None:
        await route.fulfill(status=200, content_type="text/html", body=_FIXTURE_HTML)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            # Exercises the stealth init-script path — the most fragile point
            # across playwright upgrades.
            await source.on_page_ready(page)
            await page.route("**/i/bookmarks**", serve_fixture)

            # is_logged_in's real selector path resolves quickly once the auth
            # marker is on the page (the fixture carries primaryColumn).
            await page.goto(source.bookmarks_url, wait_until="domcontentloaded")
            assert await source.is_logged_in(page) is True

            items = [item async for item in source.fetch(page)]
        finally:
            await browser.close()

    by_id = {item.source_item_id: item for item in items}
    assert set(by_id) == {"111", "222"}
    assert str(by_id["111"].url) == "https://x.com/jack/status/111"
    assert str(by_id["222"].url) == "https://x.com/alice/status/222"
    assert all(item.suggested_tags == ["x"] for item in items)
    assert all(item.raw_metadata == {"capturedFrom": "bookmarks"} for item in items)
