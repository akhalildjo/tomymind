<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo/tomymind-dark.svg">
    <img src="assets/logo/tomymind.svg" alt="tomymind" width="440">
  </picture>
</h1>

<p align="center"><em>Bring your scattered bookmarks home to <a href="https://mymind.com">mymind</a>.</em></p>

<p align="center">
  <a href="https://github.com/akhalildjo/tomymind/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/akhalildjo/tomymind/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <a href="https://github.com/akhalildjo/tomymind/releases"><img alt="Latest release" src="https://img.shields.io/github/v/release/akhalildjo/tomymind?include_prereleases&sort=semver"></a>
  <a href="https://www.python.org/downloads/"><img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue.svg"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green.svg"></a>
  <a href="#requirements"><img alt="Platforms" src="https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg"></a>
</p>

`tomymind` is a small command-line tool that imports your bookmarks from
other sites into your mymind library. It runs entirely on your machine,
authenticates as the real you (using your own browser session — no
third-party API keys), and pushes each URL to mymind via the official
API.

**Sources supported today:** X (Twitter) — Instagram and Pinterest on the
roadmap.

> [!IMPORTANT]
> This is a **community project**, not an official mymind product. It
> talks to the [public mymind API](https://access.mymind.com/api) using
> your own credentials. No affiliation, no endorsement.
>
> **Use is at your own risk.** Each source has its own Terms of Service,
> and automated access may not be permitted on every platform. Only run
> `tomymind` with accounts you own, only to export your own bookmarks,
> and make sure your usage complies with each service's ToS. The tool is
> provided "as is" without warranty — see [LICENSE](LICENSE).

---

## Table of contents

- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Using it — worked example with X](#using-it--worked-example-with-x)
- [Command reference](#command-reference)
- [What stays on your machine](#what-stays-on-your-machine)
- [Troubleshooting](#troubleshooting)
- [Adding a new source](#adding-a-new-source)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Acknowledgments](#acknowledgments)
- [License](#license)

---

## How it works

Every source follows the same three steps, each triggered manually:

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  1. Authenticate │ ─▶ │   2. Scrape      │ ─▶ │   3. Push        │
│                  │    │                  │    │                  │
│ paste cookies    │    │ headless browser │    │ POST /objects    │
│ from your Chrome │    │ scrolls + parses │    │ with HS256 JWT   │
│ (or manual login)│    │ your bookmarks   │    │ rate-limit aware │
└──────────────────┘    └──────────────────┘    └──────────────────┘
       │                        │                        │
       ▼                        ▼                        ▼
  sessions/<src>/        output/<src>.json     mymind.com library
```

What that means in practice:

- **You stay in control.** Nothing happens in the background. Every step
  is a command you type.
- **Your data stays local** until you explicitly `push`. The scrape phase
  writes a plain JSON file you can read, edit, or archive.
- **mymind does the rest.** We only send URLs. Title, screenshot,
  preview, summary, tags — mymind extracts all of that server-side, just
  like when you save via the browser extension.
- **It's resumable.** Ctrl+C during a push and re-run: it picks up
  exactly where it stopped, thanks to a local ledger.

---

## Quick start

```bash
git clone https://github.com/akhalildjo/tomymind.git
cd tomymind
make install

# One-time: get your mymind API credentials and put them in .env
cp .env.example .env
# then open .env in your editor and fill in MYMIND_API_KEY_ID + MYMIND_API_KEY_SECRET

# Per-source flow (X example):
make import-cookies-x       # paste auth_token + ct0 from your logged-in Chrome
make scrape-x               # writes output/x_bookmarks.json
make push-x                 # POSTs each URL to mymind
```

That's the whole thing.

---

## Requirements

- **Python 3.12 or newer**
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** — fast,
  reproducible Python package manager
- **A browser** where you're already logged into the source you want to
  scrape (Chrome recommended)
- **(optional) [GNU Make](https://www.gnu.org/software/make/)** — provides
  shortcut commands. On Windows: `winget install GnuWin32.Make` or
  `scoop install make`. Skip it if you prefer typing the full
  `uv run tomymind …` commands.

Runs on Windows, macOS, and Linux.

---

## Installation

```bash
git clone https://github.com/akhalildjo/tomymind.git
cd tomymind
make install
```

Under the hood this runs:

```bash
uv sync --extra scraper --extra stealth --extra push --extra dev
uv run playwright install chromium
```

Don't have Make? Run the two commands above directly.

### Optional: install real Google Chrome (recommended)

Playwright ships with Chromium, but some anti-bot stacks fingerprint it.
Using real Google Chrome works better. If you already have Chrome installed
on your system, Playwright will find it automatically. Otherwise:

```bash
make install-chrome
```

> [!NOTE]
> On Windows, this needs an Administrator terminal because Playwright
> installs Chrome system-wide. Skip if you've already got Chrome from
> [chrome.com](https://www.google.com/chrome/).

---

## Configuration

You need two credentials from mymind to use `push`. Get them from your
mymind account settings (look for "API" or "Developer"). You'll receive:

- A **Key ID** — a short identifier (e.g. `bmtw…`)
- A **Private key** — a base64-encoded HMAC secret, ending in `=`

Drop them into `.env`:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
MYMIND_API_KEY_ID=your-key-id-here
MYMIND_API_KEY_SECRET=your-base64-secret-here=
```

Paste both values **verbatim** — no quotes, no spaces. The trailing `=`
on the secret is base64 padding and must be preserved.

> [!CAUTION]
> Your `MYMIND_API_KEY_SECRET` grants full read/write access to your
> mymind library. Treat it like a password. Never commit `.env`, never
> paste it in a chat or screenshot, never share it. If it leaks,
> regenerate the pair in your mymind settings.

---

## Using it — worked example with X

### Step 1: get a session

X aggressively blocks automated browsers at login. The workaround is to
copy your existing session cookies from a Chrome window where you're
already logged in.

```bash
make import-cookies-x
```

You'll be prompted to paste two cookies. To find them:

1. Open Chrome and go to [x.com](https://x.com) (make sure you're logged in)
2. Press **F12** to open DevTools
3. Click the **Application** tab (you may need to expand `>>` to see it)
4. In the left sidebar: **Cookies → https://x.com**
5. Find and copy the **Value** for these two cookies:
   - `auth_token` — a long hexadecimal string
   - `ct0` — a longer hexadecimal string

Paste each at the prompt. The tool verifies your session before exiting,
so a wrong or expired value fails fast instead of mysteriously later.

> [!TIP]
> Cookies have a 30-day lifetime by default. When the scraper starts
> reporting "Session expired", re-run `make import-cookies-x` to refresh.

#### Alternative: manual login

For sources that allow automated logins (X currently does not), you can
use:

```bash
make login-x
```

This opens a visible Chromium window. Log in normally, then return to
the terminal and press **ENTER** to save the session.

### Step 2: scrape

```bash
make scrape-x
```

You'll see progress streaming live:

```
  [   1] https://x.com/jack/status/1234567890
  [   2] https://x.com/openai/status/1234567891
  …
  [ 412] https://x.com/anthropicai/status/1234568302
Done. 412 bookmarks → output/x_bookmarks.json
```

For more control:

```bash
uv run tomymind scrape x --limit 100         # cap to first 100
uv run tomymind scrape x --show-browser      # watch the browser work
uv run tomymind scrape x --output ./my.json  # custom output path
```

### Step 3: push to mymind

```bash
make push-x
```

```
  412 scraped, 0 already pushed, 412 to send.
  [   1/412] NEW     https://x.com/jack/status/1234567890
  [   2/412] NEW     https://x.com/openai/status/1234567891
  [   3/412] EXISTED https://x.com/somefriend/status/9999999
  …
  Done. 408 created, 3 already in mymind, 1 failed.
```

Each line tells you what happened:

| Tag | Meaning |
|---|---|
| `NEW` | A new object was created in your mymind library (HTTP 201) |
| `EXISTED` | mymind already had this URL — it just refreshed the timestamp (HTTP 200) |
| `FAIL XXX` | An error; the URL is skipped and you can investigate the status code |

The pusher automatically:

- **Retries 429 (rate limit)** by sleeping until your slowest credit bucket resets
- **Retries 5xx errors** with exponential backoff (2s, 4s, 8s)
- **Writes a local ledger** (`output/.pushed_x.json`) after each success
- **Resumes from the ledger** on re-run, so Ctrl+C is safe

---

## Command reference

```
tomymind sources                             List supported sources
tomymind login <source>                      Manual login flow (visible browser)
tomymind import-cookies <source>             Paste cookies from a logged-in browser
tomymind scrape <source> [options]           Scrape bookmarks to JSON
tomymind push <source> [options]             Push JSON to mymind

scrape options:
  --limit N                                  Stop after N bookmarks
  --show-browser                             Run with a visible browser window
  --output PATH                              Custom output JSON path

push options:
  --input PATH                               Custom input JSON path
  --ledger PATH                              Custom ledger path
```

Or via Make:

```
make import-cookies-x      make scrape-x      make push-x
make login-x               make check         make help
```

---

## What stays on your machine

Everything sensitive is stored locally and is gitignored:

| File / folder | Contents |
|---|---|
| `sessions/<source>/` | Persistent Chrome profile (cookies, localStorage) |
| `output/<source>_bookmarks.json` | Scraped bookmarks |
| `output/.pushed_<source>.json` | Local ledger of already-pushed IDs |
| `.env` | Your mymind API credentials |

The tool makes network calls only to:

1. The source's website during scraping (same traffic as a normal browser visit)
2. `https://api.mymind.com/objects` during push

No analytics, no telemetry, no third-party services.

---

## Troubleshooting

<details>
<summary><b>"Session expired" right after import-cookies</b></summary>

- Double-check you copied **both** cookies (`auth_token` AND `ct0`) — one
  without the other won't authenticate.
- Make sure you copied the **Value** column, not the Name or any other
  field.
- The session may have been revoked since you copied it (e.g. you logged
  out in the other browser). Log in again in Chrome and re-copy.

</details>

<details>
<summary><b>"system Chrome not found, falling back to bundled Chromium"</b></summary>

This is a warning, not an error. The cookie-import flow works fine with
Chromium. If you want the warning gone, install real Google Chrome from
[chrome.com](https://www.google.com/chrome/) or run `make install-chrome`.

</details>

<details>
<summary><b>Scrape finishes with 0 items</b></summary>

- Your session may have expired mid-scrape. Re-run `make import-cookies-x`.
- The source might have changed its HTML structure. Open an issue with
  the source name and your output.

</details>

<details>
<summary><b>"MYMIND_API_KEY_ID and MYMIND_API_KEY_SECRET must be set"</b></summary>

You haven't created `.env` yet, or the values are blank. See
[Configuration](#configuration).

</details>

<details>
<summary><b>Push fails with 401 Unauthorized</b></summary>

Your credentials are wrong or revoked. Regenerate them in your mymind
settings and update `.env`. Note: `MYMIND_API_KEY_SECRET` must be the
**base64** value mymind gives you (typically ends in `=`), pasted
verbatim with no transformations.

</details>

<details>
<summary><b>Push appears stuck for minutes</b></summary>

You probably hit the rate limit. mymind's `POST /objects` costs 10–250
credits per call, and your account has both a burst budget and a
30-day sustained budget. The pusher sleeps until the slowest bucket
resets and resumes automatically. You can Ctrl+C and resume later —
the ledger has your progress.

</details>

---

## Adding a new source

The architecture is shaped so new sources only touch
`src/tomymind/scrapers/`. Briefly:

1. Create `src/tomymind/scrapers/<name>.py` with a class subclassing
   `BaseScraper`. Implement `is_logged_in()` and `scrape()`.
2. Register it in `src/tomymind/scrapers/__init__.py`.
3. Optionally declare `cookie_import_specs` if the source has an
   anti-automation login flow.

See [`CLAUDE.md`](CLAUDE.md) for the full contract and conventions, or
[`src/tomymind/scrapers/x.py`](src/tomymind/scrapers/x.py) as a worked
reference.

External PRs aren't open yet — see [Contributing](#contributing).

---

## Roadmap

### Sources

- [x] **X (Twitter)** scraper — `/i/bookmarks` with infinite scroll
- [ ] **Instagram** scraper — `/<user>/saved/`
- [ ] **Pinterest** scraper — `/<user>/_saved/`
- [ ] **YouTube** "Watch later" → mymind

### Core

- [x] Repo skeleton, base scraper runner, output schema
- [x] Cookie-import flow for sources that refuse automated login
- [x] `tomymind push` — HS256 JWT signer, rate-limit-aware client,
      resumable ledger

### Test coverage

The unit suite covers pure helpers and mocked plumbing on every CI
matrix cell. Known gaps, in ROI order:

- [ ] `httpx.MockTransport` tests for `MymindClient.create_object`
      covering the 200 / 201 / 429-retry / 5xx-retry paths
- [ ] One real-Playwright smoke test on Linux to validate
      `launch_persistent_context` + `add_cookies` bindings against a
      local HTML fixture (no live third-party site)
- [ ] CI job that runs `make check` on Windows so the Makefile's
      `cmd.exe` branch is exercised end-to-end (today only `uv run
      pytest` is)
- [ ] Test for the `channel="chrome"` system-Chrome lookup with the
      "Chrome not found → bundled Chromium" fallback on each OS
- [ ] Repro of Windows session-dir file-locking behavior so we catch
      the failure mode before users do

Live `x.com` / `instagram.com` / `pinterest.com` E2E tests are
**deliberately out of scope** — live pages change too often, see
[`CLAUDE.md`](CLAUDE.md) for the rationale.

Want a source added? [Open an issue](https://github.com/akhalildjo/tomymind/issues).

---

## Contributing

> [!NOTE]
> **External code contributions aren't open yet.** tomymind is still
> being shaped by its initial maintainer — release process, source
> roadmap, and a few internal conventions are still settling. Pull
> requests from outside the maintainer team will be closed with a
> pointer to [`CONTRIBUTING.md`](CONTRIBUTING.md). This may change in
> the future — follow the repo for a heads-up.

What you *can* do right now:

- **Report bugs** or **request new sources** via the
  [issue templates](https://github.com/akhalildjo/tomymind/issues/new/choose).
  Expect a slower-than-average triage while contributions are closed.
- **Report security issues** privately via
  [GitHub Security Advisories](https://github.com/akhalildjo/tomymind/security/advisories/new) —
  these are always welcome. See [`SECURITY.md`](SECURITY.md).

For full details (including the maintainer release process and what
contributing will look like once it opens) see
[`CONTRIBUTING.md`](CONTRIBUTING.md). For architecture and the
debugging playbook, see [`CLAUDE.md`](CLAUDE.md).

---

## Acknowledgments

Huge thanks to **Tobias van Schneider** and the **[mymind](https://mymind.com)
team** for building a bookmark home that actually respects its users — no
algorithmic feed, no ads, no dark patterns — and for opening up a
[public API](https://access.mymind.com/api) that makes a community tool
like this one possible in the first place.

This project also stands on the shoulders of the open-source ecosystem:
[Playwright](https://playwright.dev/), [Pydantic](https://docs.pydantic.dev/),
[Typer](https://typer.tiangolo.com/), [httpx](https://www.python-httpx.org/),
[uv](https://docs.astral.sh/uv/), [ruff](https://docs.astral.sh/ruff/), and
[pytest](https://docs.pytest.org/) — thanks to every maintainer who keeps
those alive.

And finally, thanks to every contributor who files an issue, opens a PR,
or just stars the repo. Every bit helps.

---

## License

MIT — see [LICENSE](LICENSE).

---

<sub>Made by and for the mymind community. mymind® is a trademark of
[mymind GmbH](https://mymind.com); X® is a trademark of X Corp. This
project is not affiliated with, endorsed by, or sponsored by either.</sub>
