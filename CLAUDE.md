# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

`tomymind` is a multi-source bookmark importer for [mymind.com](https://mymind.com).
The target architecture is microservices: source scrapers → NATS JetStream →
`mymind-importer` → mymind API. **Today only phase 1 (scrapers in isolation) is
implemented**. There is no broker, no `mymind-importer`, no Docker. Each
scraper writes its output to a JSON file under `output/`.

The JSON output shape (`ScrapeResult` with camelCase aliases via Pydantic) is
intentionally identical to the future `BookmarkDiscovered` event payload — keep
it stable when changing models.

## Commands

```bash
# First-time setup
uv sync
uv run playwright install chromium
uv sync --extra dev          # adds pytest, ruff
uv sync --extra stealth      # adds tf-playwright-stealth (needed for Instagram)

# CLI (registered as the `tomymind` console script)
uv run tomymind sources
uv run tomymind login <source>              # opens visible Chromium, user logs in by hand, ENTER to save
uv run tomymind scrape <source> [--limit N] [--show-browser] [--output PATH]

# Quality gates
uv run ruff check .
uv run ruff format .
uv run pytest                # asyncio_mode=auto is set in pyproject.toml
uv run pytest path/to/test_file.py::test_name -v
```

`sessions/<source>.json` (Playwright `storage_state`) and `output/*.json` are
gitignored — never commit them.

## Architecture

### Call flow

```
cli.py  →  runner.py  →  Playwright  →  scraper.scrape(page)  →  output/<source>.json
                ↑              ↑
                │              └── BaseScraper subclass picked from
                │                   scrapers/__init__._REGISTRY
                └── loads sessions/<source>.json (storage_state)
```

- `cli.py` parses args and resolves the scraper via `scrapers.get_scraper(name)`.
- `runner.run_login` opens a **non-headless** browser, awaits stdin on a worker
  thread, then calls `scraper.is_logged_in(page)` against `scraper.home_url`
  before persisting `storage_state`.
- `runner.run_scrape` loads the saved `storage_state`, navigates to `home_url`,
  re-checks `is_logged_in`, then iterates `scraper.scrape(page, limit)`. Items
  are streamed (`async for`) so progress is visible and the run can stop on
  `--limit`.

### Key conventions

- **`SessionError` lives in `tomymind.errors`**, not in `runner.py`. Scrapers
  raise it (e.g. when a protected page redirects to login mid-scrape) so the
  CLI's friendly handler catches it. Avoid creating an inverse
  `scrapers → runner` import.
- **Scrapers must yield, not return lists.** `BaseScraper.scrape` is typed as
  `AsyncIterator[BookmarkItem]`; the runner relies on streaming for the
  progress UI and the `--limit` early-exit. If you override `scrape` with an
  `async def` that has no `yield` in its body, it becomes a coroutine instead
  of an async generator and the runner's `async for` crashes with
  `TypeError: 'coroutine' object is not async iterable`.
- **Dedup by `source_item_id` inside a single run** is the scraper's job (X
  uses a `seen_ids: set[str]`). Cross-run dedup will be handled later in
  `mymind-importer` plus mymind's native URL dedup.
- **Idle-scroll termination**: infinite-scroll scrapers stop after N
  consecutive scrolls that reveal no new items *and* no height change. See
  `XScraper._idle_scroll_limit` for the X tuning.

## Adding a new scraper

1. Create `src/tomymind/scrapers/<name>.py` with a class subclassing
   `BaseScraper`. Set `name`, `login_url`, `home_url`. Implement
   `is_logged_in(page) -> bool` (check a UI element that only exists when
   authenticated) and `scrape(page, limit) -> AsyncIterator[BookmarkItem]`.
2. Register it in `src/tomymind/scrapers/__init__.py` by adding it to
   `_REGISTRY`. `tomymind sources` will pick it up automatically.
3. The CLI commands (`login`, `scrape`) work without any further wiring.

For sources with strong anti-bot detection (Instagram, eventually), override
`on_context_ready(context)` to install `tf-playwright-stealth` and throttle
scroll/click cadence.

## Debugging a flaky scraper

- **Run visibly**: `uv run tomymind scrape <source> --show-browser` to watch
  the live DOM.
- **Pause mid-run**: drop `await page.pause()` inside `scrape()` to open the
  Playwright Inspector with step-through and a selector picker.
- **Selector priority**: `data-testid` > stable `aria-*` > semantic tag. Avoid
  CSS classes (Instagram/X obfuscate them per build).
- **Typical failure modes**:
  - 0 items + run terminated quickly → session expired (re-run `login`) *or*
    the top-level item selector changed (e.g. `article[data-testid="tweet"]`).
  - `wait_for_selector` timeout → page didn't reach a logged-in state; check
    `page.url` and screenshot via `await page.screenshot(path="dbg.png")`.
  - Items found but URLs wrong → href parsing helper (`_parse_tweet_href` and
    siblings) needs new edge-cases; add a unit test rather than printf.

## Testing

- **Do NOT write E2E tests that hit real x.com / instagram.com / pinterest.com.**
  Live pages change, accounts get rate-limited, CI becomes red noise. Cover
  scrapers via **unit tests on the pure parsing helpers**
  (`_parse_tweet_href`, future `_parse_pin_link`, …) with hard-coded HREF
  fixtures including reserved-path / weird-handle cases.
- Tests go under `tests/` mirroring `src/tomymind/` (e.g.
  `tests/scrapers/test_x.py`). `asyncio_mode=auto` is already set, so use
  `async def test_*` freely.

## mymind API — context for the future `mymind-importer`

**API reference**: https://access.mymind.com/api

When phase 2 starts, these constraints apply (not yet captured in source;
review chat history of PR #1 or the link above for full details):

- **Auth**: HS256 JWT signed per request. Header `kid`, claims `path`,
  `method` (uppercase), `iat`, `exp` (recommended `iat + 300`). Bearer in
  `Authorization`. `User-Agent` required.
- **Create bookmark**: `POST /objects` with `{"url": "...", "tags": [...]}`.
  mymind extracts title/screenshot/metadata itself. Same URL → 200 OK with
  existing object (native dedup, refreshes `bumped`).
- **Rate limit**: dual credit system (`burst` + `sustained` over 30 days).
  Response headers `RateLimit-Policy`, `RateLimit` (`r`=remaining, `t`=reset
  seconds), `RateLimit-Cost`. `POST /objects` costs 10–250 credits. On 429,
  sleep until the slowest exhausted policy's `t`.
- **Errors**: `application/problem+json` (RFC 9457). Branch on `type`
  (`NotFound`, `Unauthorized`, `RateLimited`, …), not on `detail`.

## Git / PR conventions

- Development branch for this workstream: `claude/mymind-bookmark-importer-ce8Qv`.
- GitHub repo (MCP-scoped): `akhalildjo/tomymind`.
- PR #1 contains the phase-1 scaffold + X scraper and the rationale for the
  current layout — check it before redesigning core abstractions.
