# Local validation pipeline for tomymind.
#
# Primary target: Windows (PowerShell or cmd, from the repo root). The recipes
# also run on macOS/Linux because every command (uv, python) is cross-platform.
#
# One-shot prereqs on Windows:
#   - Python 3.12+    https://www.python.org/downloads/  (or: winget install Python.Python.3.12)
#   - uv              winget install astral-sh.uv
#   - GNU Make        scoop install make    OR    winget install GnuWin32.Make
#
# Usage:
#   make              # same as `make help`
#   make check        # full validation (deps + lint + tests + cli smoke)
#   make <target>     # run a single phase, see `make help`
#
# After `make check` passes, the user-facing flow per source is:
#   make import-cookies-x    # paste auth_token + ct0 from a logged-in Chrome
#   make fetch-x             # writes output/x_bookmarks.json
#   make push-x              # POST every URL to mymind (needs .env)

ifeq ($(OS),Windows_NT)
    SHELL := cmd.exe
    .SHELLFLAGS := /C
    BLANK := echo.
else
    SHELL := /bin/sh
    BLANK := echo
endif

.DEFAULT_GOAL := help

.PHONY: help prereqs install install-chrome lint test cli \
        check login-x import-cookies-x fetch-x push-x

help:
	@echo tomymind - local validation targets
	@$(BLANK)
	@echo   make prereqs        - check that python / uv are installed
	@echo   make install        - uv sync source+automation+push+dev, then playwright install chromium
	@echo   make install-chrome - optional: install real Google Chrome via Playwright (needs admin on Windows)
	@echo   make lint           - ruff check and ruff format --check
	@echo   make test           - pytest
	@echo   make cli            - smoke test the tomymind CLI, lists sources
	@$(BLANK)
	@echo   make check          - run everything above in order
	@$(BLANK)
	@echo   make login-x        - manual: opens visible Chromium to log into X
	@echo   make import-cookies-x - paste auth_token + ct0 from a logged-in Chrome, skips login
	@echo   make fetch-x        - manual: fetch all bookmarks from X, needs prior login-x or import-cookies-x
	@echo   make push-x         - POST fetched X bookmarks to mymind, needs .env with MYMIND_API_KEY_*

prereqs:
	@echo == Prereqs ==
	python --version
	uv --version

install:
	@echo == uv sync + playwright install chromium ==
	uv sync --extra source --extra automation --extra push --extra dev
	uv run playwright install chromium

# Optional: drops real Google Chrome where channel="chrome" looks. Needs admin
# on Windows (it's a system-wide install). Skip it if you already have Chrome
# installed via chrome.com -- the runner will pick it up via channel="chrome"
# automatically. The cookie-import flow works fine without this.
install-chrome:
	@echo == playwright install chrome -- may need admin on Windows ==
	uv run playwright install chrome

lint:
	@echo == ruff check ==
	uv run ruff check .
	@echo == ruff format --check ==
	uv run ruff format --check .

test:
	@echo == pytest ==
	uv run pytest

cli:
	@echo == tomymind sources ==
	uv run tomymind sources

check: prereqs install lint test cli
	@$(BLANK)
	@echo === All automated checks passed ===
	@echo Manual steps left, need a real browser + your accounts:
	@echo   make import-cookies-x  (or: make login-x)
	@echo   make fetch-x
	@echo   make push-x

login-x:
	@echo == tomymind login x -- visible Chromium, press ENTER in this terminal once logged in ==
	uv run tomymind login x

import-cookies-x:
	@echo == tomymind import-cookies x -- paste auth_token + ct0 from your logged-in Chrome ==
	uv run tomymind import-cookies x

fetch-x:
	@echo == tomymind fetch x ==
	uv run tomymind fetch x

push-x:
	@echo == tomymind push x -- POST fetched bookmarks to mymind ==
	uv run tomymind push x
