# tomymind

Multi-source bookmark importer for [mymind.com](https://mymind.com). Scrapes your
bookmarks from X, Instagram and Pinterest, then pushes them to mymind via the
official API.

> **Status — Phase 1 (scrapers).** We're validating each scraper in isolation
> before plugging in the message broker and the mymind importer. Today only the
> X scraper is implemented.

## Architecture target

```
Source scrapers ──▶ NATS JetStream ──▶ mymind-importer ──▶ mymind API
   (X · Insta ·         (queue)            (JWT signer,
    Pinterest)                              rate limiter,
                                            dedup)
```

Phase 1 keeps everything local: no broker, no Docker. Each scraper writes its
bookmarks to a JSON file under `output/`. The importer pipeline comes in phase 2.

## Setup

Requires Python 3.12+.

```bash
# install uv if you don't have it: https://docs.astral.sh/uv/getting-started/installation/
uv sync
uv run playwright install chromium
```

## Usage

Each source has the same two-step flow: log in once (manual, visible browser),
then scrape (headless).

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
- [ ] **Instagram** scraper (`/<user>/saved/`, stealth required)
- [ ] **Pinterest** scraper (`/<user>/_saved/`)
- [ ] `mymind-importer` service: JWT signer, credit-aware rate limiter, dedup, retries
- [ ] NATS JetStream wiring + Docker Compose
- [ ] Orchestrator API + minimal UI

## Notes on scraping

- **First-party data only**: scrape your own account.
- **Session reuse**: we only log in once per source; subsequent runs reuse the
  storage state. If a session expires, re-run `tomymind login <source>`.
- **Anti-bot**: Instagram is the touchy one. The `stealth` extra
  (`uv sync --extra stealth`) installs `tf-playwright-stealth`; the scraper will
  opt into it when needed.
- **Be gentle**: scrolls are throttled. Don't parallelize runs on the same account.
