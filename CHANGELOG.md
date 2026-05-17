# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Changed

- Package version is now sourced from `src/tomymind/__init__.py` via
  `[tool.hatch.version]` so there is a single source of truth.
- Enriched `pyproject.toml` metadata: authors, project URLs, keywords,
  trove classifiers (OS, Python versions, audience, topic).

## [0.1.0] — 2026-05-17

Initial public release.

### Added

- `tomymind` CLI with `sources`, `login`, `import-cookies`, `scrape` and
  `push` commands.
- X (Twitter) scraper for `/i/bookmarks` with infinite-scroll handling,
  in-run dedup by `source_item_id`, and a stealth-patched persistent
  Chrome profile per source.
- Cookie-import flow for sources whose anti-bot stack rejects automated
  logins (X today).
- `push` command: HS256 JWT signer per request, rate-limit-aware client
  that honors `RateLimit` headers, 5xx exponential backoff, and a local
  resumable ledger (`output/.pushed_<source>.json`).
- Cross-platform Makefile with `install`, `lint`, `test`, `cli`,
  `check`, and per-source `login-x` / `import-cookies-x` / `scrape-x` /
  `push-x` targets.

[Unreleased]: https://github.com/akhalildjo/tomymind/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/akhalildjo/tomymind/releases/tag/v0.1.0
