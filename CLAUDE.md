# CLAUDE.md

This file documents the project's architecture, conventions and gotchas.
[Claude Code](https://claude.ai/code) reads it for context when working on
the codebase; human contributors should read it too before opening a PR,
since it captures decisions and constraints that aren't obvious from the
code alone.

## Project state

`tomymind` is a multi-source bookmark importer for [mymind.com](https://mymind.com).
Everything runs on the host as manually-triggered CLI commands -- no broker,
no daemon, no Docker. The three-step user flow per source is:

1. **Get a session** -- either `tomymind login <source>` (visible Chromium,
   manual login) or `tomymind import-cookies <source>` (paste session cookies
   from an already-logged-in browser, faster and dodges anti-bot stacks that
   refuse automated browsers).
2. **Scrape** -- `tomymind scrape <source>` writes
   `output/<source>_bookmarks.json` headlessly.
3. **Push** -- `tomymind push <source>` reads that JSON, POSTs each URL to
   `https://api.mymind.com/objects` with a per-request HS256 JWT, writes a
   ledger of pushed IDs so Ctrl+C is resumable.

Sources today: **X**. The architecture is shaped so adding new sources only
touches `src/tomymind/scrapers/`.

**Login is intentionally a manual operation on the host.** The login flow
needs a visible Chromium window so the user can type credentials and clear
any 2FA / captcha; automating it is out of scope. The cookie-import path
skips the login UI entirely for sources whose anti-bot stack refuses
automated browsers at the login screen (X's case today).

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
# Dev setup
uv sync --extra scraper --extra stealth --extra push --extra dev
uv run playwright install chromium

# `tomymind` is the only console script. All commands are host-side, manual.
uv run tomymind sources
uv run tomymind login <source>              # visible Chromium, user logs in, ENTER to save
uv run tomymind import-cookies <source>     # paste session cookies, no UI login
uv run tomymind scrape <source> [--limit N] [--show-browser] [--output PATH]
uv run tomymind push <source> [--input PATH] [--ledger PATH]

# Quality gates
uv run ruff check .
uv run ruff format .
uv run pytest                # asyncio_mode=auto is set in pyproject.toml
uv run pytest path/to/test_file.py::test_name -v
```

`sessions/<source>/` (persistent Chrome user-data dir, drives
`launch_persistent_context`), `output/*.json` (scraped bookmarks), and
`output/.pushed_<source>.json` (push ledger) are gitignored -- never commit
them. `.env` is gitignored too; `.env.example` ships the template.

### pyproject extras at a glance

| Extra | Purpose | Pulls in |
|---|---|---|
| `scraper` | `tomymind login` / `import-cookies` / `scrape` | playwright, typer, python-dotenv |
| `stealth` | anti-bot evasion (X, future Instagram) | tf-playwright-stealth |
| `push` | `tomymind push` (mymind API client + JWT signing) | httpx, pyjwt |
| `dev` | tests + lint | pytest, pytest-asyncio, ruff |

## Architecture

### Call flow

Everything is one process per CLI invocation, all on the host:

```
   cli.py  ──▶  runner.py  ──▶  Playwright  ──▶  scraper.scrape(page)  ──▶  output/<source>_bookmarks.json
                    ↑                ↑
                    │                └── BaseScraper subclass picked from
                    │                     scrapers/__init__._REGISTRY
                    └── loads sessions/<source>/ (persistent Chrome profile)

   cli.py  ──▶  push.py  ──▶  mymind_client.py  ──▶  POST https://api.mymind.com/objects
                  ↑                ↑                    (HS256 JWT per request,
                  │                │                     429 retry with RateLimit-aware sleep,
                  │                │                     5xx retry with backoff)
                  │                └── output/.pushed_<source>.json (ledger, rewritten after
                  │                     every successful 200/201 so Ctrl+C is resumable)
                  └── output/<source>_bookmarks.json
```

- `cli.py` parses args and resolves the scraper via `scrapers.get_scraper(name)`.
- `runner.run_login` opens a **non-headless** browser via
  `launch_persistent_context` (prefers system Chrome via `channel="chrome"`,
  falls back to bundled Chromium), awaits stdin on a worker thread, then
  calls `scraper.is_logged_in(page)` against `scraper.home_url`. The profile
  dir at `sessions/<source>/` persists on its own — no explicit
  `storage_state` dump needed.
- `runner.run_import_cookies` is the cookie-paste alternative: prompts for the
  source's `cookie_import_specs` (e.g. X's `auth_token` + `ct0`), injects them
  into the persistent profile with a 30-day `expires` (without it Chromium
  treats them as session cookies and never writes them to disk), then
  verifies `is_logged_in` before exiting so a wrong/expired token surfaces
  immediately instead of at the next scrape.
- `runner.run_scrape` reopens the same persistent profile, navigates to `home_url`,
  re-checks `is_logged_in`, then iterates `scraper.scrape(page, limit)`. Items
  are streamed (`async for`) so progress is visible and the run can stop on
  `--limit`.
- `push.run_push` reads the scrape JSON, filters out items whose
  `source_item_id` is already in the local ledger, and hands each remaining
  item to `mymind_client.MymindClient.create_object`. The ledger is
  persisted to `output/.pushed_<source>.json` and survives across runs, so
  re-running `push` after a Ctrl+C or after a fresh `scrape` only sends
  what hasn't been sent yet from this machine. Cross-machine / cross-install
  dedup is not done client-side; mymind's native server-side URL dedup
  (existing URL → `200 OK`, refreshes `bumped`) is the safety net.
- `mymind_client.sign_request` builds a per-request bearer JWT (kid header
  + path/method/iat/exp claims, 5-min TTL). The secret is base64-decoded
  to bytes once per call. See `## mymind API` below for the rate-limit
  contract the client honors.

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
  uses a `seen_ids: set[str]`). Cross-run dedup at push time is handled by
  the local ledger (`output/.pushed_<source>.json`) plus mymind's native
  URL dedup.
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
3. All four CLI commands (`login`, `import-cookies`, `scrape`, `push`)
   then work against the new source without any further wiring.

For sources with strong anti-bot detection (X needs it today; sources like
Instagram likely will too), override `on_page_ready(page)` to apply
`playwright_stealth.stealth_async` before the first navigation, and throttle
scroll/click cadence. `on_context_ready` is the place for context-wide
things (extra headers, cookies); stealth is page-level because it relies on
`page.add_init_script`.

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

## mymind API

**API reference**: https://access.mymind.com/api (docs). Base URL for
requests is `https://api.mymind.com` (override via `MYMIND_API_BASE` env
var if pointing at staging). The `mymind_client` module implements all of
this; this section is the spec it follows.

- **Strategy**: ship URLs only (plus optional tags). mymind extracts title,
  screenshot, preview and metadata server-side. **Don't pre-fetch pages,
  scrape Open Graph tags, or generate screenshots client-side.**
- **Auth**: HS256 JWT signed per request. Header `kid`, claims `path`
  (e.g. `/objects`, no `/api` prefix), `method` (uppercase), `iat`, `exp`
  (recommended `iat + 300`). Bearer in `Authorization`. `User-Agent`
  required. The `MYMIND_API_KEY_SECRET` env var is the base64-encoded
  32-byte HMAC key as issued by mymind; `MymindCreds.hmac_key()` decodes
  it once per call.
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
  sleep until the slowest exhausted policy's `t` -- see
  `parse_ratelimit_reset`.
- **Errors**: `application/problem+json` (RFC 9457). Branch on `type`
  (`NotFound`, `Unauthorized`, `RateLimited`, …), not on `detail`.
  `_extract_detail` surfaces the human-readable field to CLI output.

## Git / PR conventions

- GitHub repo: `akhalildjo/tomymind` (this is the only repo Claude Code
  agents working on this project are allowed to touch; human contributors
  obviously have the same scope by convention).
- Keep PRs small and self-contained: one scraper / one CLI command / one
  bug fix per PR. `main` stays green.
- An earlier iteration scaffolded a NATS JetStream + Docker importer
  architecture for an automated event-driven flow; that path was dropped
  in favor of the simpler "manual CLI per source" flow you see today. If
  you find references to NATS, `mymind_importer` as a service, or Docker
  in old git history, they are intentionally removed.
