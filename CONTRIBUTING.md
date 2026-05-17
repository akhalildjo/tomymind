# Contributing to tomymind

> [!IMPORTANT]
> **External contributions are not open at this time.** tomymind is still
> being shaped by its initial maintainer and we want to settle the
> release process, the source-coverage roadmap, and a few internal
> conventions before opening the door. This document is kept up to date
> so that *when* contributions open up, the guide is ready — and so the
> maintainer follows a consistent process in the meantime.
>
> Until then:
>
> - **Bug reports and source requests are welcome** — use the
>   [issue templates](https://github.com/akhalildjo/tomymind/issues/new/choose).
>   They may take a while to be triaged.
> - **Security reports are always welcome** — see [`SECURITY.md`](SECURITY.md).
> - **Pull requests from outside the maintainer team will be closed**
>   with a friendly note pointing at this document. Please don't take
>   it personally — we'd just rather not leave you waiting on a review
>   that may not come for a while.
>
> Follow the repo if you want a heads-up when this changes.

---

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

## Release process (maintainers)

tomymind follows a **pragmatic gitflow**: `main` is the active trunk,
and `release/x.y` branches are created on-demand to stabilize a
version. Tags `vX.Y.Z` live on `release/x.y` (or, rarely, on a
`hotfix/x.y.z` branch for out-of-band patches off an older release).

We follow [Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH.
Until we hit `1.0.0`, anything in MINOR may include breaking changes;
PATCH stays backward-compatible.

### Cutting a new release (`vX.Y.Z`)

1. From the GitHub Actions tab, run the **Prepare release** workflow
   with the target version (e.g. `0.2.0`). It will:
   - Create `release/x.y` off `main`.
   - Bump `__version__` in `src/tomymind/__init__.py`.
   - Promote `[Unreleased]` in `CHANGELOG.md` to the new dated section.
   - Push the branch.
2. Review the bump commit on `release/x.y`. Push any final
   stabilization commits on that branch (and only that branch).
3. Tag and push:
   ```bash
   git fetch origin
   git checkout release/x.y
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
4. The **Release** workflow verifies the tag is on `release/*` or
   `hotfix/*`, verifies it matches `__version__`, builds the sdist +
   wheel, and publishes a GitHub Release with auto-generated notes.
5. The **Backmerge to main** workflow opens a PR from `release/x.y`
   back to `main`. Merge it to bring the version bump + CHANGELOG
   entries onto the trunk.

### Patching an already-shipped minor

Two cases:

- **The `release/x.y` branch is still alive** (we're still supporting
  that minor): push the fix directly to `release/x.y` and tag
  `vX.Y.Z+1` from there. No special workflow needed.
- **The `release/x.y` branch is gone** (we moved on): run the
  **Prepare hotfix** workflow with the base tag (e.g. `v0.2.0`) and
  the new version (e.g. `0.2.1`). It creates `hotfix/x.y.z` off the
  tag, bumps the version, and stubs out a CHANGELOG entry. Commit the
  fix, tag `vX.Y.Z`, push. The backmerge workflow opens PRs back to
  `main` and to `release/x.y` if it still exists.

### Branch protection (recommended)

The release flow assumes:

- `main` is protected: PR + green CI required.
- `release/**` and `hotfix/**` are protected: PR + green CI required.
- Only maintainers can push tags `v*`.

---

## Reporting bugs and security issues

- **Bugs / feature requests:** open an issue using one of the
  [templates](https://github.com/akhalildjo/tomymind/issues/new/choose).
- **Security vulnerabilities:** please *do not* open a public issue.
  Use [GitHub's private security advisory](https://github.com/akhalildjo/tomymind/security/advisories/new)
  instead. See [`SECURITY.md`](SECURITY.md).
