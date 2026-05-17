<!--
Thanks for contributing to tomymind!

Keep PRs small and self-contained: one scraper, one CLI command, one bug
fix per PR. `main` stays green.
-->

## Summary

<!-- What does this PR change, and why? 1-3 sentences is plenty. -->

## Type of change

<!-- Tick everything that applies. -->

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] New scraper (new source under `src/tomymind/scrapers/`)
- [ ] Breaking change (fix or feature that would cause existing behavior to change)
- [ ] Documentation / DX (README, CLAUDE.md, comments, CI, Makefile)
- [ ] Refactor (no behavior change)

## How was this tested?

<!--
Which `make` targets / commands did you run? Which OS(es)? If it's a
scraper change, did you run it end-to-end against the real source with
your own account?
-->

- [ ] `make lint` passes
- [ ] `make test` passes
- [ ] Manually tested on: <!-- Windows / macOS / Linux -->

## Cross-platform checklist

<!-- tomymind must run on Windows, macOS and Linux. Tick everything that applies. -->

- [ ] Paths use `pathlib.Path` and `/`, never string concatenation with `/` or `\`
- [ ] File I/O passes `encoding="utf-8"` explicitly
- [ ] No `subprocess(..., shell=True)`, no bash-isms
- [ ] No hardcoded `/tmp`, `/home/...`, or `C:\...` paths in tests

## Related issue

<!-- e.g. Closes #123, Refs #456 -->
