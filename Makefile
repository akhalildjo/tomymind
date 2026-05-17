# Local validation pipeline for tomymind.
#
# Primary target: Windows (PowerShell or cmd, from the repo root). The recipes
# also run on macOS/Linux because every command (uv, docker, python) is
# cross-platform and the only "sleep" uses python -c.
#
# One-shot prereqs on Windows:
#   - Python 3.12+    https://www.python.org/downloads/  (or: winget install Python.Python.3.12)
#   - uv              winget install astral-sh.uv
#   - Docker Desktop  https://www.docker.com/products/docker-desktop/  (enable WSL2 backend)
#   - GNU Make        scoop install make    OR    winget install GnuWin32.Make
#
# Usage:
#   make              # same as `make help`
#   make check        # full validation (deps + lint + tests + docker round-trip)
#   make <target>     # run a single phase, see `make help`
#
# After `make check` passes, the only manual steps left need a real browser
# and your X credentials:
#   make login-x      # opens a visible Chromium, you log in by hand
#   make scrape-x     # scrapes everything into output/x_bookmarks.json

ifeq ($(OS),Windows_NT)
    SHELL := cmd.exe
    .SHELLFLAGS := /C
    SLEEP5 := python -c "import time; time.sleep(5)"
    BLANK := echo.
else
    SHELL := /bin/sh
    SLEEP5 := sleep 5
    BLANK := echo
endif

.DEFAULT_GOAL := help

.PHONY: help prereqs install install-chrome lint test cli \
        docker-build docker-up docker-status docker-logs docker-down \
        check login-x import-cookies-x scrape-x

help:
	@echo tomymind - local validation targets
	@$(BLANK)
	@echo   make prereqs        - check that python / uv / docker are installed
	@echo   make install        - uv sync scraper+stealth+importer+dev, then playwright install chromium
	@echo   make install-chrome - optional: install real Google Chrome via Playwright (needs admin on Windows)
	@echo   make lint           - ruff check and ruff format --check
	@echo   make test           - pytest
	@echo   make cli            - smoke test the tomymind CLI, lists sources
	@$(BLANK)
	@echo   make docker-build   - build the mymind-importer image
	@echo   make docker-up      - start nats + importer, waits for nats healthcheck
	@echo   make docker-status  - docker compose ps
	@echo   make docker-logs    - tail the last 80 lines of importer logs
	@echo   make docker-down    - stop everything and wipe the JetStream volume
	@$(BLANK)
	@echo   make check          - run everything above in order, clean teardown at the end
	@$(BLANK)
	@echo   make login-x        - manual: opens visible Chromium to log into X
	@echo   make import-cookies-x - paste auth_token + ct0 from a logged-in Chrome, skips login
	@echo   make scrape-x       - manual: scrape all bookmarks from X, needs prior login-x or import-cookies-x

prereqs:
	@echo == Prereqs ==
	python --version
	uv --version
	docker version --format "Client {{.Client.Version}} / Server {{.Server.Version}}"
	docker compose version

install:
	@echo == uv sync + playwright install chromium ==
	uv sync --extra scraper --extra stealth --extra importer --extra dev
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

docker-build:
	@echo == docker compose build importer ==
	docker compose build importer

docker-up: docker-build
	@echo == docker compose up -d, waits for nats healthcheck ==
	docker compose up -d --wait
	@$(SLEEP5)
	@$(MAKE) docker-status
	@$(MAKE) docker-logs

docker-status:
	@echo == docker compose ps ==
	docker compose ps

docker-logs:
	@echo == importer logs, tail 80 ==
	docker compose logs --tail 80 importer

docker-down:
	@echo == docker compose down -v ==
	docker compose down -v

check: prereqs install lint test cli docker-up docker-down
	@$(BLANK)
	@echo === All automated checks passed ===
	@echo Manual steps left, need a real browser + your X account:
	@echo   make login-x
	@echo   make scrape-x

login-x:
	@echo == tomymind login x -- visible Chromium, press ENTER in this terminal once logged in ==
	uv run tomymind login x

import-cookies-x:
	@echo == tomymind import-cookies x -- paste auth_token + ct0 from your logged-in Chrome ==
	uv run tomymind import-cookies x

scrape-x:
	@echo == tomymind scrape x ==
	uv run tomymind scrape x
