# Contributing to tomymind

Thanks for your interest in contributing! tomymind is a small,
focused tool and we want to keep it that way — bug fixes, new scrapers,
and documentation improvements are all welcome.

This guide is the short version. For deeper context on architecture,
conventions, and the debugging playbook, see [`CLAUDE.md`](CLAUDE.md).

---

## Ground rules

- **First-party data only.** This tool exists to import *your* bookmarks
  into *your* mymind library. We won't accept PRs that scrape other
  people's content, public search results, or anything not behind your
  own login.
- **Be gentle with the sources.** No parallel runs against the same
  account, no aggressive scroll cadence. We don't want to get anyone's
  account flagged.
- **Cross-platform from the start.** Code must run on Windows, macOS,
  and Linux. The CI matrix enforces this.
- **No live-site E2E tests.** Real x.com / instagram.com / pinterest.com
  pages change too often. Test the parsing helpers
  (`_parse_tweet_href` style) with hard-coded fixtures.

---

## Getting set up

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/akhalildjo/tomymind.git
cd tomymind
make install              # uv sync + playwright install chromium
```

If you don't have `make`, run the two commands `make install` prints under
the hood (`uv sync --extra ...` and `uv run playwright install chromium`).

---

## Quality gates

Before opening a PR:

```bash
make lint          # ruff check + ruff format --check
make test          # pytest
```

CI runs the same checks on Linux, macOS, and Windows across Python 3.12,
3.13, and 3.14. If a check passes locally but fails in CI, you've almost
certainly hit a cross-platform issue — look at paths, line endings, and
file encodings first.

---

## Adding a new scraper

The architecture is shaped so new sources only touch
`src/tomymind/scrapers/`.

1. Create `src/tomymind/scrapers/<name>.py` with a class subclassing
   `BaseScraper`. Set `name`, `login_url`, `home_url`. Implement
   `is_logged_in(page) -> bool` and `scrape(page, limit) -> AsyncIterator[BookmarkItem]`.
2. Register it in `src/tomymind/scrapers/__init__.py` by adding it to
   `_REGISTRY`.
3. Add unit tests for the pure parsing helpers under
   `tests/scrapers/test_<name>.py`. Don't write tests that hit the real
   site.

See [`src/tomymind/scrapers/x.py`](src/tomymind/scrapers/x.py) as a
worked reference and [`CLAUDE.md`](CLAUDE.md) for the full contract.

---

## Commit and PR conventions

- **Keep PRs small and self-contained.** One scraper, one CLI command,
  one bug fix per PR. `main` stays green.
- **Write meaningful commit messages.** First line is a summary (≤ 72
  chars); body explains the *why* if it isn't obvious.
- **Reference issues** with `Fixes #123` or `Refs #456` in the PR body.
- **Update the [CHANGELOG](CHANGELOG.md)** under `[Unreleased]` for any
  user-visible change.

---

## Releasing (maintainers)

Releases are tag-driven:

1. Bump `__version__` in `src/tomymind/__init__.py` and move the
   `[Unreleased]` block in `CHANGELOG.md` under the new version heading
   with today's date.
2. Open a PR, get it reviewed and merged to `main`.
3. From `main`, tag and push:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
4. The `Release` workflow verifies that the tag matches the package
   version, builds the wheel + sdist, and publishes a GitHub Release
   with auto-generated notes.

We follow [Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH.
Until we hit `1.0.0`, anything in MINOR may include breaking changes;
PATCH stays backward-compatible.

---

## Reporting bugs and security issues

- **Bugs / feature requests:** open an issue using one of the
  [templates](https://github.com/akhalildjo/tomymind/issues/new/choose).
- **Security vulnerabilities:** please *do not* open a public issue.
  Use [GitHub's private security advisory](https://github.com/akhalildjo/tomymind/security/advisories/new)
  instead. See [`SECURITY.md`](SECURITY.md).
