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
   from an already-logged-in browser, faster and skips the login UI for
   sources that don't accept automated browser logins).
2. **Fetch** -- `tomymind fetch <source>` writes
   `output/<source>_bookmarks.json` headlessly.
3. **Push** -- `tomymind push <source>` reads that JSON, POSTs each URL to
   `https://api.mymind.com/objects` with a per-request HS256 JWT, writes a
   ledger of pushed IDs so Ctrl+C is resumable.

Sources today: **X**. The architecture is shaped so adding new sources only
touches `src/tomymind/sources/`.

**Login is intentionally a manual operation on the host.** The login flow
needs a visible Chromium window so the user can type credentials and clear
any 2FA / captcha; automating it is out of scope. The cookie-import path
skips the login UI entirely for sources that don't accept automated browser
logins (X's case today).

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
uv sync --extra source --extra automation --extra push --extra dev
uv run playwright install chromium

# `tomymind` is the only console script. All commands are host-side, manual.
uv run tomymind sources
uv run tomymind login <source>              # visible Chromium, user logs in, ENTER to save
uv run tomymind import-cookies <source>     # paste session cookies, no UI login
uv run tomymind fetch <source> [--limit N] [--show-browser] [--output PATH]
uv run tomymind push <source> [--input PATH] [--ledger PATH]

# Quality gates
uv run ruff check .
uv run ruff format .
uv run pytest                # asyncio_mode=auto is set in pyproject.toml
uv run pytest path/to/test_file.py::test_name -v
```

`sessions/<source>/` (persistent Chrome user-data dir, drives
`launch_persistent_context`), `output/*.json` (fetched bookmarks), and
`output/.pushed_<source>.json` (push ledger) are gitignored -- never commit
them. `.env` is gitignored too; `.env.example` ships the template.

### pyproject extras at a glance

| Extra | Purpose | Pulls in |
|---|---|---|
| `source` | `tomymind login` / `import-cookies` / `fetch` | playwright, typer, python-dotenv |
| `automation` | browser session compatibility (X, future Instagram) | tf-playwright-stealth |
| `push` | `tomymind push` (mymind API client + JWT signing) | httpx, pyjwt |
| `dev` | tests + lint | pytest, pytest-asyncio, ruff |

## Architecture

### Call flow

Everything is one process per CLI invocation, all on the host:

```
   cli.py  ──▶  runner.py  ──▶  Playwright  ──▶  source.fetch(page)  ──▶  output/<source>_bookmarks.json
                    ↑                ↑
                    │                └── BaseSource subclass picked from
                    │                     sources/__init__._REGISTRY
                    └── loads sessions/<source>/ (persistent Chrome profile)

   cli.py  ──▶  push.py  ──▶  mymind_client.py  ──▶  POST https://api.mymind.com/objects
                  ↑                ↑                    (HS256 JWT per request,
                  │                │                     429 retry with RateLimit-aware sleep,
                  │                │                     5xx retry with backoff)
                  │                └── output/.pushed_<source>.json (ledger, rewritten after
                  │                     every successful 200/201 so Ctrl+C is resumable)
                  └── output/<source>_bookmarks.json
```

- `cli.py` parses args and resolves the source via `sources.get_source(name)`.
- `runner.run_login` opens a **non-headless** browser via
  `launch_persistent_context` (prefers system Chrome via `channel="chrome"`,
  falls back to bundled Chromium), awaits stdin on a worker thread, then
  calls `source.is_logged_in(page)` against `source.home_url`. The profile
  dir at `sessions/<source>/` persists on its own — no explicit
  `storage_state` dump needed.
- `runner.run_import_cookies` is the cookie-paste alternative: prompts for the
  source's `cookie_import_specs` (e.g. X's `auth_token` + `ct0`), injects them
  into the persistent profile with a 30-day `expires` (without it Chromium
  treats them as session cookies and never writes them to disk), then
  verifies `is_logged_in` before exiting so a wrong/expired token surfaces
  immediately instead of at the next fetch.
- `runner.run_fetch` reopens the same persistent profile, navigates to `home_url`,
  re-checks `is_logged_in`, then iterates `source.fetch(page, limit)`. Items
  are streamed (`async for`) so progress is visible and the run can stop on
  `--limit`.
- `push.run_push` reads the fetch JSON, filters out items whose
  `source_item_id` is already in the local ledger, and hands each remaining
  item to `mymind_client.MymindClient.create_object`. The ledger is
  persisted to `output/.pushed_<source>.json` and survives across runs, so
  re-running `push` after a Ctrl+C or after a fresh `fetch` only sends
  what hasn't been sent yet from this machine. Cross-machine / cross-install
  dedup is not done client-side; mymind's native server-side URL dedup
  (existing URL → `200 OK`, refreshes `bumped`) is the safety net.
- `mymind_client.sign_request` builds a per-request bearer JWT (kid header
  + path/method/iat/exp claims, 5-min TTL). The secret is base64-decoded
  to bytes once per call. See `## mymind API` below for the rate-limit
  contract the client honors.

### Key conventions

- **`SessionError` lives in `tomymind.errors`**, not in `runner.py`. Sources
  raise it (e.g. when a protected page redirects to login mid-run) so the
  CLI's friendly handler catches it. Avoid creating an inverse
  `sources → runner` import.
- **Sources must yield, not return lists.** `BaseSource.fetch` is typed as
  `AsyncIterator[BookmarkItem]`; the runner relies on streaming for the
  progress UI and the `--limit` early-exit. If you override `fetch` with an
  `async def` that has no `yield` in its body, it becomes a coroutine instead
  of an async generator and the runner's `async for` crashes with
  `TypeError: 'coroutine' object is not async iterable`.
- **Dedup by `source_item_id` inside a single run** is the source's job (X
  uses a `seen_ids: set[str]`). Cross-run dedup at push time is handled by
  the local ledger (`output/.pushed_<source>.json`) plus mymind's native
  URL dedup.
- **Idle-scroll termination**: infinite-scroll sources stop after N
  consecutive scrolls that reveal no new items *and* no height change. See
  `XSource._idle_scroll_limit` for the X tuning.

## Adding a new source

1. Create `src/tomymind/sources/<name>.py` with a class subclassing
   `BaseSource`. Set `name`, `login_url`, `home_url`. Implement
   `is_logged_in(page) -> bool` (check a UI element that only exists when
   authenticated) and `fetch(page, limit) -> AsyncIterator[BookmarkItem]`.
2. Register it in `src/tomymind/sources/__init__.py` by adding it to
   `_REGISTRY`. `tomymind sources` will pick it up automatically.
3. All four CLI commands (`login`, `import-cookies`, `fetch`, `push`)
   then work against the new source without any further wiring.

For sources that need browser-context compatibility tweaks (X needs it today;
sources like Instagram likely will too), override `on_page_ready(page)` to
apply `playwright_stealth.stealth_async` before the first navigation, and
throttle scroll/click cadence. `on_context_ready` is the place for
context-wide things (extra headers, cookies); the page-level hook is needed
because `playwright_stealth` relies on `page.add_init_script`.

## Debugging a flaky source

- **Run visibly**: `uv run tomymind fetch <source> --show-browser` to watch
  the live DOM.
- **Pause mid-run**: drop `await page.pause()` inside `fetch()` to open the
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
  sources via **unit tests on the pure parsing helpers**
  (`_parse_tweet_href`, future `_parse_pin_link`, …) with hard-coded HREF
  fixtures including reserved-path / weird-handle cases.
- Tests go under `tests/` mirroring `src/tomymind/` (e.g.
  `tests/sources/test_x.py`). `asyncio_mode=auto` is already set, so use
  `async def test_*` freely.

## mymind API

**API reference**: https://access.mymind.com/api (docs). Base URL for
requests is `https://api.mymind.com` (override via `MYMIND_API_BASE` env
var if pointing at staging). The `mymind_client` module implements all of
this; this section is the spec it follows.

- **Strategy**: ship URLs only (plus optional tags). mymind extracts title,
  screenshot, preview and metadata server-side. **Don't pre-fetch pages,
  read Open Graph tags, or generate screenshots client-side.**
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
  agents working on this project are allowed to touch).
- **External contributions are currently closed** — see the notice at
  the top of `CONTRIBUTING.md`. Issues stay open for bug reports and
  source requests, security advisories stay open, but external PRs are
  not accepted right now. Agents working on this repo should still
  follow PR-based workflows (no direct commits to `main`).
- Keep PRs small and self-contained: one source / one CLI command / one
  bug fix per PR. `main` stays green.
- **Always resolve review conversations once they're addressed.** The
  `main` branch ruleset requires every conversation to be resolved
  before merge; an unresolved Copilot / reviewer comment will block
  the PR with "A conversation must be resolved before this pull
  request can be merged." Resolve via the GitHub UI ("Resolve
  conversation") or the MCP `resolve_review_thread` tool — including
  threads you skip intentionally, with a one-line reply explaining
  why. Never bypass the rule with admin merge unless explicitly
  asked.
- An earlier iteration scaffolded a NATS JetStream + Docker importer
  architecture for an automated event-driven flow; that path was dropped
  in favor of the simpler "manual CLI per source" flow you see today. If
  you find references to NATS, `mymind_importer` as a service, or Docker
  in old git history, they are intentionally removed.

### Branch model (pragmatic gitflow)

We use a lightweight gitflow optimized for a small project with
infrequent releases:

- **`main`** — active trunk. Feature work merges here via PR. Tags are
  **never** placed directly on `main`.
- **`release/x.y`** — created on demand from `main` when freezing a
  minor version (e.g. `release/0.2` for the `0.2.x` line). All
  `vx.y.z` tags for that minor live on this branch. The branch may
  stay alive after the initial tag to absorb patch versions.
- **`hotfix/x.y.z`** — created off an existing `vx.y.z` tag when the
  matching `release/x.y` branch is gone and we need an out-of-band
  patch. Tags `vx.y.z+1` live on this branch.

Tag → branch invariant enforced by `release.yml`: `v*` tags are
rejected if the commit isn't reachable from a `release/*` or
`hotfix/*` branch on origin.

### Release workflows (`.github/workflows/`)

- **`prepare-release.yml`** (`workflow_dispatch`) — input: target
  version. Creates `release/x.y` off `main`, bumps `__version__`,
  promotes `[Unreleased]` in `CHANGELOG.md` to a dated section, pushes
  the branch. Does **not** tag — the maintainer tags after review.
- **`prepare-hotfix.yml`** (`workflow_dispatch`) — inputs: base tag +
  new version. Creates `hotfix/x.y.z` off the tag, bumps version,
  stubs a CHANGELOG entry. The maintainer commits the actual fix on
  top, then tags.
- **`release.yml`** (tag `v*` push) — verifies tag is on `release/*`
  or `hotfix/*`, verifies the tag matches `__version__`, builds
  sdist+wheel, publishes a GitHub Release with auto-generated notes.
- **`backmerge.yml`** (tag `v*` push) — opens a PR from the source
  branch back to `main`. For a `hotfix/x.y.z` tag, also opens a PR to
  `release/x.y` if that branch still exists.
- **`ci.yml`** — runs on push to `main`, `release/**`, `hotfix/**`,
  and on PRs targeting `main` or `release/**`.

**Important constraints when modifying these workflows:**

- `release.yml` and `backmerge.yml` both need `fetch-depth: 0` to see
  all remote branches via `git branch -r --contains`.
- The bump-version logic uses inline Python (not `sed`) because the
  CHANGELOG link-rewrite regex is tricky to get right portably. If
  you touch it, mirror the change in both `prepare-release.yml` and
  `prepare-hotfix.yml`.
- The repo URL `https://github.com/akhalildjo/tomymind` is hardcoded
  in both prepare workflows for the CHANGELOG link references. If the
  repo ever moves, search for it in `.github/workflows/`.

### Repo settings (public-repo hardening)

The repo is **public**, MIT-licensed. The branch model above is enforced
at the GitHub level by three **Rulesets** (Settings → Rules → Rulesets —
not the deprecated "Branch protection rules" UI):

| Ruleset | Target | Effect |
|---|---|---|
| A — `main` | branch `main` | Restrict deletions, block force-push, require PR + green CI, require conversation resolution, dismiss stale approvals |
| B — release / hotfix | `release/**` and `hotfix/**` | Same as A; admin can bypass for the direct fix-push case on a live `release/x.y` documented in `CONTRIBUTING.md` |
| C — version tags | tags matching `v*` | Restrict creation / update / deletion to admin — enforces "only the maintainer pushes `v*` tags" |

Required status checks on A and B are every job name produced by
`ci.yml`: `Lint (ruff)`, the nine `Test (<os> / Python <version>)`
matrix cells, and `Build distribution`. **Add new cells to the rulesets
when the CI matrix grows**, otherwise they don't gate the merge.

Code security features (free on public repos, all ON):

- Dependabot alerts + security updates (in addition to the
  `dependabot.yml` version updates already configured).
- Secret scanning + push protection.
- CodeQL default setup for Python (adds `Analyze (python)` and
  `Analyze (actions)` checks to PRs).
- Private vulnerability reporting (the channel `SECURITY.md` points
  users at).

Actions settings that matter for the release flow:

- **Allow GitHub Actions to create and approve pull requests** must be
  ON, otherwise `backmerge.yml` and `prepare-release.yml` fail at
  `gh pr create`.
- Fork-PR workflows: "Require approval for all external contributors"
  — random PRs don't burn CI minutes while contributions are closed
  (see `CONTRIBUTING.md`).

Pull-request merge settings:

- **Merge commits ON** — needed for backmerges (`release/*` → `main`)
  so the version-bump commit lands on both branches with its history
  intact.
- **Squash merging ON** — default for feature PRs.
- **Rebase merging OFF** — avoid history mutation on protected
  branches.
- **Auto-delete head branches ON** — safe because protected
  `release/*` / `hotfix/*` branches are exempt from auto-delete by
  design (GitHub never auto-deletes a protected ref).

The README carries a "Use at your own risk" disclaimer under the top
`[!IMPORTANT]` callout (ToS responsibility is the user's, not the
maintainer's) and the trademark footer acknowledges both **mymind®**
(mymind GmbH) and **X®** (X Corp). Keep that disclaimer present
whenever the README is restructured — it's the surface-level legal
posture for the public repo.
