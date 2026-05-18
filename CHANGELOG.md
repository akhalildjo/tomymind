# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-17

Initial public release.

### Added

- `tomymind` CLI with `sources`, `login`, `import-cookies`, `fetch` and
  `push` commands.
- X (Twitter) source connector for `/i/bookmarks` with infinite-scroll
  handling, in-run dedup by `source_item_id`, and a persistent Chrome
  profile per source for browser session compatibility.
- Cookie-import flow for sources that don't accept automated browser
  logins (X today).
- `push` command: HS256 JWT signer per request, rate-limit-aware client
  that honors `RateLimit` headers, 5xx exponential backoff, and a local
  resumable ledger (`output/.pushed_<source>.json`).
- Cross-platform Makefile with `install`, `lint`, `test`, `cli`,
  `check`, and per-source `login-x` / `import-cookies-x` / `fetch-x` /
  `push-x` targets.
- Continuous integration on GitHub Actions: lint + tests across Linux,
  macOS, and Windows on Python 3.12 / 3.13 / 3.14, plus an sdist + wheel
  build job.
- Release workflow that publishes a GitHub Release with built
  distributions when a `v*` tag is pushed (with a guard that the tag
  matches `__version__`).
- Dependabot config for weekly updates of both Python dependencies (via
  the `uv` ecosystem) and GitHub Actions versions.
- Community files: `CONTRIBUTING.md`, `SECURITY.md`, issue templates
  (bug report, new source request), and a pull request template.
- Acknowledgments section in the README crediting Tobias van Schneider
  and the mymind team.
- "Use at your own risk" / ToS responsibility disclaimer in the README
  top callout, and an X trademark notice alongside mymind's in the
  footer.
- "Tested on" section in the README documenting the CI matrix coverage
  and inviting field reports for non-Linux platforms.
- `httpx.MockTransport`-based tests for `MymindClient.create_object`
  covering 201 / 200-dedup / 4xx no-retry / 401 / 429 retry-then-success
  / 429 exhausted / 5xx exponential backoff / 5xx exhausted, plus
  request shape (tag wrapping, Bearer JWT, POST `/objects`).

### Changed

- Package version is now sourced from `src/tomymind/__init__.py` via
  `[tool.hatch.version]` so there is a single source of truth.
- Enriched `pyproject.toml` metadata: authors, project URLs, keywords,
  trove classifiers (OS, Python versions, audience, topic).
- `MymindClient.__init__` accepts an optional `transport=` kwarg
  (defaults to `None` → real httpx default) for test injection. No
  existing call sites change.

[Unreleased]: https://github.com/akhalildjo/tomymind/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/akhalildjo/tomymind/releases/tag/v0.1.0
