# Security Policy

Thanks for helping keep tomymind and its users safe.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security reports.**

Instead, use GitHub's private vulnerability reporting:

➡️ **[Report a vulnerability](https://github.com/akhalildjo/tomymind/security/advisories/new)**

This opens a private channel between you and the maintainers. The report
stays confidential until a fix is published.

### What to include

- A clear description of the issue and its impact.
- Steps to reproduce, including the affected version (commit SHA or tag).
- Any proof-of-concept code or logs (strip your own credentials first —
  see below).
- Optionally, a suggested fix.

### What to expect

- An acknowledgement within **5 business days**.
- A triage update within **14 days**, including whether we accept the
  report and a target timeline for a fix.
- Credit in the release notes when the fix ships, unless you'd rather
  stay anonymous.

## Supported versions

tomymind is pre-1.0. Security fixes are released against the latest
tagged version on `main`. Older tagged versions do not receive
backported fixes — upgrade to the latest release to get the fix.

| Version       | Supported |
| ------------- | --------- |
| Latest `main` | Yes       |
| Older tags    | No        |

## Scope

In scope:

- The `tomymind` Python package and CLI in this repository.
- The GitHub Actions workflows in `.github/workflows/`.
- The documentation in this repository if it would lead a reader to a
  vulnerable configuration.

Out of scope:

- Issues in upstream dependencies (report those upstream — please do let
  us know if a dependency CVE affects tomymind so we can pin or patch).
- The mymind API itself — please report those to
  [mymind](https://mymind.com) directly.
- The source sites that tomymind scrapes (x.com, etc.) — report those
  to the respective vendors.

## Handling credentials in reports

tomymind uses two kinds of secrets that must **never** appear in a
public issue, a PR, a screenshot, or any artifact shared during
reporting:

- **`MYMIND_API_KEY_SECRET`** — base64 HMAC key. Grants full read/write
  on a mymind library. Treat like a password. If yours is exposed in a
  report or log, regenerate it immediately in your mymind settings.
- **Source session cookies** (e.g. X's `auth_token`, `ct0`) — grant full
  account access. Revoke by logging out of the source in your browser.

If you accidentally leak either in a public space, rotate them first,
then file the report.
