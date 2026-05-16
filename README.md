# tomymind

Multi-source bookmark importer for [mymind.com](https://mymind.com). Scrapes
your bookmarks from X, Instagram and Pinterest, then pushes them to mymind via
the official API.

> **Status.** Phase 1 (X scraper) is in. Phase 2 scaffold (NATS JetStream +
> `mymind-importer` container) is in but inert: the importer image builds and
> starts, but real publish/consume logic lands in follow-up PRs. Instagram and
> Pinterest scrapers come later.

## Architecture

```
Source scrapers ──▶ NATS JetStream ──▶ mymind-importer ──▶ mymind API
   (host, login           (Docker)            (Docker,
    needs visible                              JWT signer,
    browser)                                   rate limiter)
```

The `login` flow needs a visible Chromium window, so it stays on the host. The
`scrape` step is headless and can run either on the host (today) or in a
container (later). The importer always runs in Docker.

## Setup

Requires Python 3.12+ and (for the Docker stack) Docker 24+ with Compose v2.

```bash
# install uv if you don't have it: https://docs.astral.sh/uv/getting-started/installation/
# All workstreams in one go:
uv sync --extra scraper --extra importer --extra dev
uv run playwright install chromium
```

The base install is minimal (just `pydantic`); each role pulls its deps via an
extra:

- `scraper`: Playwright, Typer, python-dotenv — needed to run `tomymind`
- `importer`: nats-py, httpx, PyJWT — for the `mymind_importer` service
- `stealth`: tf-playwright-stealth — for Instagram (heavy, opt-in)
- `dev`: pytest + ruff

## Usage

### Scrape a source (host)

Two-step flow: log in once (manual, visible browser), then scrape headlessly.

```bash
# 1. Log in to a source. Opens a real Chromium window — you log in by hand,
#    then come back to the terminal and press ENTER.
uv run tomymind login x

# 2. Scrape bookmarks. Headless by default.
uv run tomymind scrape x --limit 50

# Run visibly to debug:
uv run tomymind scrape x --show-browser

# Custom output path:
uv run tomymind scrape x --output output/my-x-dump.json

# List available scrapers:
uv run tomymind sources
```

Sessions are stored under `sessions/<source>.json` (cookies + localStorage).
They're gitignored. Bookmarks land under `output/<source>_bookmarks.json`.

### Phase 2 stack (Docker)

```bash
# Bring up NATS JetStream (and the placeholder importer container)
docker compose up -d

# Follow logs
docker compose logs -f importer

# Stop (keeps the NATS volume so JetStream state survives restarts)
docker compose down

# Stop and wipe persisted JetStream state
docker compose down -v
```

The importer reads its config from environment variables — copy `.env.example`
to `.env` and fill in `MYMIND_API_KEY_ID` / `MYMIND_API_KEY_SECRET` once those
are needed (no-op while the importer is still a placeholder).

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

This shape is the future `BookmarkDiscovered` event payload — phase 2 will publish
each item to NATS instead of writing JSON.

## Roadmap

- [x] Repo skeleton, common models, CLI, base scraper runner
- [x] **X** scraper (`/i/bookmarks` with infinite scroll)
- [x] Phase 2 scaffold: NATS JetStream service, `mymind-importer` package +
      Docker image, Docker Compose
- [ ] Wire NATS publish on the scraper side (`--publish` flag) and a NATS
      subscriber in the importer
- [ ] `mymind-importer` business logic: HS256 JWT signer, mymind client,
      credit-aware rate limiter, retries on 429
- [ ] **Instagram** scraper (`/<user>/saved/`, stealth required)
- [ ] **Pinterest** scraper (`/<user>/_saved/`)
- [ ] Orchestrator API + minimal UI

## Notes on scraping

- **First-party data only**: scrape your own account.
- **Session reuse**: we only log in once per source; subsequent runs reuse the
  storage state. If a session expires, re-run `tomymind login <source>`.
- **Anti-bot**: Instagram is the touchy one. The `stealth` extra
  (`uv sync --extra stealth`) installs `tf-playwright-stealth`; the scraper will
  opt into it when needed.
- **Be gentle**: scrolls are throttled. Don't parallelize runs on the same account.
