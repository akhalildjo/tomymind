# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

`tomymind` is a multi-source bookmark importer for [mymind.com](https://mymind.com).
Target architecture is microservices: source scrapers → NATS JetStream →
`mymind-importer` → mymind API.

**Status:**
- **Phase 1 — scrapers (done for X):** each scraper writes its output to a
  JSON file under `output/`. Login flow runs on the host (visible Chromium);
  scrape runs headless.
- **Phase 2 — Docker stack (scaffold only):** `docker-compose.yml` brings up
  NATS JetStream and the `mymind-importer` container. The importer image
  builds and starts but currently runs an inert placeholder — the NATS
  consumer and the mymind client land in follow-up PRs.

The JSON output shape (`ScrapeResult` with camelCase aliases via Pydantic) is
intentionally identical to the future `BookmarkDiscovered` event payload —
keep it stable when changing models.

**Login stays on the host, period.** The `tomymind login` flow needs a
visible Chromium window so the user can type credentials and clear any
2FA / captcha. Don't try to dockerize this — GUI-in-Docker is platform
hostile (X11 forwarding on Linux, XQuartz on macOS, WSLg on Win11). The
scrape step is already headless and is the only piece that benefits from a
container.

## Portability

`tomymind` must run on **Windows, macOS and Linux** — bake cross-platform
support into every change, don't fix it after the fact:

- **Paths**: always `pathlib.Path` and the `/` operator; never string-concat
  with `/` or `\`. Always pass `encoding="utf-8"` to `read_text` / `write_text`
  / `open` — Windows defaults to `cp1252`.
- **Shell**: no `subprocess(..., shell=True)`, no bash-isms in Python. CLI
  examples in README/docs must also run as-is in PowerShell (no `&&`-only
  chains, no `$VAR` expansion that PowerShell parses differently — prefer
  one command per line).
- **Filesystem casing**: assume both case-sensitive (Linux, macOS-APFS) and
  case-insensitive (Windows, macOS-default). Don't create files that differ
  only by case.
- **Line endings & newlines**: let Python handle them — never write `\r\n`
  literals, never strip `\r` defensively.
- **Tests**: no hardcoded `/tmp`, `/home/...`, `C:\...`; use `tmp_path` /
  `Path.home()` and skip with a clear reason if a test is genuinely
  OS-specific.

## Commands

Base deps are intentionally minimal (just `pydantic`). Each role pulls in its
own extra:

```bash
# Dev setup (scraper + stealth + importer + test tooling)
uv sync --extra scraper --extra stealth --extra importer --extra dev
uv run playwright install chromium

# Scraper CLI (registered as the `tomymind` console script — requires --extra scraper)
uv run tomymind sources
uv run tomymind login <source>              # opens visible Chromium, user logs in by hand, ENTER to save
uv run tomymind scrape <source> [--limit N] [--show-browser] [--output PATH]

# Docker stack (phase 2: NATS JetStream + mymind-importer)
docker compose up -d nats                   # broker only
docker compose up -d                        # broker + importer (placeholder for now)
docker compose logs -f importer
docker compose down                         # stop services (keeps the NATS volume)
docker compose down -v                      # also drop persisted JetStream state

# Quality gates
uv run ruff check .
uv run ruff format .
uv run pytest                # asyncio_mode=auto is set in pyproject.toml
uv run pytest path/to/test_file.py::test_name -v
```

`sessions/<source>.json` (Playwright `storage_state`) and `output/*.json` are
gitignored — never commit them.

### pyproject extras at a glance

| Extra | Purpose | Pulls in |
|---|---|---|
| `scraper` | running `tomymind login` / `scrape` on the host | playwright, typer, python-dotenv |
| `stealth` | anti-bot evasion (X, future Instagram) | tf-playwright-stealth |
| `importer` | the `mymind_importer` service (runs in Docker) | nats-py, httpx, pyjwt |
| `dev` | tests + lint | pytest, pytest-asyncio, ruff |

The Docker image for `mymind-importer` installs **only** `--extra importer`
so Playwright + Chromium (~1 GB) stay out of that image.

## Architecture

### Call flow

Phase 1 (scraper, runs on the host):

```
cli.py  →  runner.py  →  Playwright  →  scraper.scrape(page)  →  output/<source>.json
                ↑              ↑
                │              └── BaseScraper subclass picked from
                │                   scrapers/__init__._REGISTRY
                └── loads sessions/<source>.json (storage_state)
```

Phase 2 (importer, runs in Docker — scaffold only, NATS publish/consume
TBD in follow-up PRs):

```
                                 ┌────────────────────────────┐
scraper (host, phase 1) ────┐    │ Docker compose (phase 2)   │
                            ├──▶ │   NATS JetStream service   │
                            │    │            │               │
                            │    │            ▼               │
                            │    │   mymind-importer service  │ ──▶ mymind API
                            │    │   (JWT signer, rate-limit) │
                            │    └────────────────────────────┘
                            │
                            └── For now scrapers still write output/<source>.json;
                                PR #2 adds a `--publish` flag that emits
                                `bookmarks.discovered.<source>` events to NATS.
```

- `cli.py` parses args and resolves the scraper via `scrapers.get_scraper(name)`.
- `runner.run_login` opens a **non-headless** browser, awaits stdin on a worker
  thread, then calls `scraper.is_logged_in(page)` against `scraper.home_url`
  before persisting `storage_state`.
- `runner.run_scrape` loads the saved `storage_state`, navigates to `home_url`,
  re-checks `is_logged_in`, then iterates `scraper.scrape(page, limit)`. Items
  are streamed (`async for`) so progress is visible and the run can stop on
  `--limit`.
- `src/mymind_importer/__main__.py` is the importer entry point — currently a
  signal-aware placeholder so `docker compose up importer` stays alive. Real
  logic (NATS subscribe → JWT-signed `POST /objects` → 429 back-off) goes
  here in subsequent PRs.

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

For sources with strong anti-bot detection (X already needs it, Instagram
will), override `on_page_ready(page)` to apply `playwright_stealth.stealth_async`
before the first navigation, and throttle scroll/click cadence. `on_context_ready`
is the place for context-wide things (extra headers, cookies); stealth is
page-level because it relies on `page.add_init_script`.

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

## mymind API — context for `mymind-importer`

**API reference**: https://access.mymind.com/api (see `/api/objects` for the
endpoint that creates a bookmark from a URL).

- **Strategy**: we only ship URLs (plus optional tags). mymind extracts
  title, screenshot, preview and metadata server-side. **Don't pre-fetch
  pages, scrape Open Graph tags, or generate screenshots client-side.**
- **Auth**: HS256 JWT signed per request. Header `kid`, claims `path`,
  `method` (uppercase), `iat`, `exp` (recommended `iat + 300`). Bearer in
  `Authorization`. `User-Agent` required.
- **Create bookmark**: `POST /objects` with `{"url": "https://...",
  "tags": [{"name": "x"}, {"name": "reading"}]}`. Exactly one of `url`,
  `content`, `blob` — combining them returns 400. **Tags are objects with
  a `name` key, not bare strings** — convert at the boundary, keep the
  internal `BookmarkItem.suggested_tags` as `list[str]`.
  Same URL → `200 OK` with the existing object (native dedup, refreshes
  the `bumped` timestamp). New URL → `201 Created`.
- **Rate limit**: dual credit system (`burst` + `sustained` over 30 days).
  Response headers `RateLimit-Policy`, `RateLimit` (`r`=remaining, `t`=reset
  seconds), `RateLimit-Cost`. `POST /objects` costs 10–250 credits. On 429,
  sleep until the slowest exhausted policy's `t`.
- **Errors**: `application/problem+json` (RFC 9457). Branch on `type`
  (`NotFound`, `Unauthorized`, `RateLimited`, …), not on `detail`.

## Git / PR conventions

- GitHub repo (MCP-scoped): `akhalildjo/tomymind`.
- Phase 1 (X scraper + base layout) landed in PR #1 — read it before
  redesigning core abstractions.
- Phase 2 lands as a series of small PRs (scaffold → NATS plumbing → mymind
  auth → mymind client → importer loop → polish), each mergeable on its own
  so `main` stays green.
