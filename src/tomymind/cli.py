from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from .errors import SessionError
from .runner import run_login, run_scrape
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


@app.command(help="List the source scrapers currently available.")
def sources():
    for name in available_scrapers():
        typer.echo(name)


if __name__ == "__main__":
    app()
