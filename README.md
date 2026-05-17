# tomymind

Multi-source bookmark importer for [mymind.com](https://mymind.com). Scrapes
your bookmarks from sites you're already logged into, then pushes each URL to
mymind via the official API.

Everything runs on your machine as manually-triggered CLI commands. No broker,
no daemon, no Docker. The three-step flow per source:

1. **Authenticate** — paste cookies from a logged-in browser (or, for sources
   where it works, do a one-shot manual login).
2. **Scrape** — pulls your bookmarks into a local JSON file.
3. **Push** — sends each URL to mymind. The push is idempotent, resumable, and
   rate-limit-aware.

**Sources today: X.** Adding new sources only touches `src/tomymind/scrapers/`.

## Setup

Requires Python 3.12+ and `uv`.

```bash
# Install uv: https://docs.astral.sh/uv/getting-started/installation/
uv sync --extra scraper --extra stealth --extra push --extra dev
uv run playwright install chromium
```

Base install is just `pydantic`; each role pulls its own extra:

- `scraper`: Playwright + Typer + python-dotenv — for `login` / `import-cookies` / `scrape`
- `stealth`: tf-playwright-stealth — anti-bot evasion (required for X)
- `push`: httpx + PyJWT — mymind API client + JWT signing
- `dev`: pytest + ruff

## Usage (worked example: X)

### 1. Get a session

X's anti-bot stack tends to refuse automated browsers at login time. The
cookie-import path is the most reliable workaround — it copies the session
from a Chrome where you're already logged in.

```bash
# Open Chrome → F12 → Application → Cookies → https://x.com
# Copy the values of `auth_token` and `ct0`, then:
uv run tomymind import-cookies x
# (paste each value at the prompt; the tool verifies the session before exiting)
```

Alternative if the source allows it: `uv run tomymind login x` opens a visible
Chromium window for a manual login.

### 2. Scrape

```bash
uv run tomymind scrape x                    # all bookmarks, headless
uv run tomymind scrape x --limit 50         # cap to first 50
uv run tomymind scrape x --show-browser     # run visibly to debug
uv run tomymind scrape x --output output/my-x-dump.json
```

Output lands in `output/x_bookmarks.json` by default.

### 3. Push to mymind

Copy `.env.example` to `.env` and fill in your mymind API credentials
(`MYMIND_API_KEY_ID` + `MYMIND_API_KEY_SECRET`), then:

```bash
uv run tomymind push x
```

The push tool:
- Skips items already in `output/.pushed_x.json` (a local ledger)
- POSTs each remaining URL with a per-request HS256 JWT
- Retries 429 by sleeping until the slowest rate-limit bucket resets
- Retries 5xx with exponential backoff
- Persists the ledger after every successful POST, so Ctrl+C is resumable

Mymind dedups natively on URL (200 OK on duplicate, 201 on new), so re-running
push never creates actual duplicate objects — at worst it wastes some API
credits on URLs the ledger has lost track of.

### Shortcuts via Make

```bash
make import-cookies-x        # → tomymind import-cookies x
make scrape-x                # → tomymind scrape x
make push-x                  # → tomymind push x
make check                   # lint + tests + cli smoke
```

## Output shape

```json
{
  "source": "x",
  "scrapedAt": "2026-05-14T12:00:00Z",
  "itemCount": 2,
  "items": [
    {
      "sourceItemId": "1234567890",
      "url": "https://x.com/jack/status/1234567890",
      "suggestedTags": ["x"],
      "rawMetadata": { "capturedFrom": "bookmarks" }
    }
  ]
}
```

## Roadmap

- [x] Repo skeleton, common models, CLI, base scraper runner
- [x] **X** scraper (`/i/bookmarks` with infinite scroll)
- [x] Cookie-import flow for sources that refuse automated login
- [x] `tomymind push` — HS256 JWT signer, mymind client, rate-limit handling,
      resumable ledger
- [ ] **Instagram** scraper (`/<user>/saved/`, stealth required)
- [ ] **Pinterest** scraper (`/<user>/_saved/`)

## Notes on scraping

- **First-party data only**: scrape your own account.
- **Session reuse**: log in (or import cookies) once per source; subsequent
  runs reuse the persistent Chrome profile under `sessions/<source>/`. If a
  session expires, re-run `import-cookies` (or `login`).
- **Anti-bot**: X needs `--extra stealth`. The X scraper raises a clear error
  at scrape time if the extra is missing.
- **Be gentle**: scrolls are throttled. Don't parallelize runs on the same
  account.
- **Gitignored**: `sessions/`, `output/*.json`, `output/.pushed_*.json`, `.env`.
