from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer

from .errors import SessionError
from .runner import run_import_cookies, run_login, run_scrape
from .scrapers import available_scrapers, get_scraper

app = typer.Typer(
    help="Multi-source bookmark importer for mymind.com",
    no_args_is_help=True,
    add_completion=False,
)


def _resolve_scraper(source: str):
    try:
        return get_scraper(source)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@app.command(help="Open a browser to log into a source, then save the session.")
def login(
    source: str = typer.Argument(..., help=f"One of: {', '.join(available_scrapers())}"),
):
    scraper = _resolve_scraper(source)
    try:
        asyncio.run(run_login(scraper))
    except SessionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command(help="Scrape bookmarks from a source using its saved session.")
def scrape(
    source: str = typer.Argument(..., help=f"One of: {', '.join(available_scrapers())}"),
    limit: int | None = typer.Option(None, help="Max bookmarks to scrape."),
    output: Path | None = typer.Option(
        None, help="Output JSON path. Defaults to output/<source>_bookmarks.json."
    ),
    show_browser: bool = typer.Option(
        False, "--show-browser", help="Run the browser visibly (disables headless)."
    ),
):
    scraper = _resolve_scraper(source)
    out_path = output or Path("output") / f"{source}_bookmarks.json"
    try:
        result = asyncio.run(
            run_scrape(
                scraper,
                limit=limit,
                output_path=out_path,
                headless=not show_browser,
            )
        )
    except SessionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"\nDone. {result.item_count} bookmarks → {out_path}")


@app.command(
    "import-cookies",
    help="Paste session cookies from a logged-in browser to skip the login flow.",
)
def import_cookies(
    source: str = typer.Argument(..., help=f"One of: {', '.join(available_scrapers())}"),
):
    scraper = _resolve_scraper(source)
    try:
        asyncio.run(run_import_cookies(scraper))
    except SessionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command(help="List the source scrapers currently available.")
def sources():
    for name in available_scrapers():
        typer.echo(name)


@app.command(help="Push scraped bookmarks to mymind.com via POST /objects.")
def push(
    source: str = typer.Argument(..., help=f"One of: {', '.join(available_scrapers())}"),
    input: Path | None = typer.Option(
        None,
        "--input",
        help="Input JSON path. Defaults to output/<source>_bookmarks.json.",
    ),
    ledger: Path | None = typer.Option(
        None,
        "--ledger",
        help="Ledger of already-pushed IDs. Defaults to output/.pushed_<source>.json.",
    ),
):
    # Lazy imports: pyjwt + httpx + python-dotenv only kick in for this
    # command, so users who only scrape don't need the `push` extra.
    try:
        from dotenv import load_dotenv

        from .mymind_client import MymindCreds
        from .push import run_push
    except ImportError as exc:
        typer.echo(
            f"error: missing dep ({exc}). Run: uv sync --extra scraper --extra push",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    load_dotenv()
    kid = os.environ.get("MYMIND_API_KEY_ID")
    secret = os.environ.get("MYMIND_API_KEY_SECRET")
    if not kid or not secret:
        typer.echo(
            "error: MYMIND_API_KEY_ID and MYMIND_API_KEY_SECRET must be set "
            "(copy .env.example to .env and fill them in).",
            err=True,
        )
        raise typer.Exit(code=2)

    creds = MymindCreds(kid=kid, secret_b64=secret)
    base_url = os.environ.get("MYMIND_API_BASE")
    input_path = input or Path("output") / f"{source}_bookmarks.json"
    ledger_path = ledger or Path("output") / f".pushed_{source}.json"

    try:
        asyncio.run(run_push(source, creds, input_path, ledger_path, base_url=base_url))
    except SessionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
