from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer

from .errors import SessionError
from .runner import run_fetch, run_import_cookies, run_login
from .sources import available_sources, get_source

app = typer.Typer(
    help="Multi-source bookmark importer for mymind.com",
    no_args_is_help=True,
    add_completion=False,
)


def _resolve_source(source: str):
    try:
        return get_source(source)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@app.command(help="Open a browser to log into a source, then save the session.")
def login(
    source: str = typer.Argument(..., help=f"One of: {', '.join(available_sources())}"),
):
    source_obj = _resolve_source(source)
    try:
        asyncio.run(run_login(source_obj))
    except SessionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command(help="Fetch bookmarks from a source using its saved session.")
def fetch(
    source: str = typer.Argument(..., help=f"One of: {', '.join(available_sources())}"),
    limit: int | None = typer.Option(None, help="Max bookmarks to fetch."),
    output: Path | None = typer.Option(
        None, help="Output JSON path. Defaults to output/<source>_bookmarks.json."
    ),
    show_browser: bool = typer.Option(
        False, "--show-browser", help="Run the browser visibly (disables headless)."
    ),
):
    source_obj = _resolve_source(source)
    out_path = output or Path("output") / f"{source}_bookmarks.json"
    try:
        result = asyncio.run(
            run_fetch(
                source_obj,
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
    source: str = typer.Argument(..., help=f"One of: {', '.join(available_sources())}"),
):
    source_obj = _resolve_source(source)
    try:
        asyncio.run(run_import_cookies(source_obj))
    except SessionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command(help="List the sources currently available.")
def sources():
    for name in available_sources():
        typer.echo(name)


@app.command(help="Push fetched bookmarks to mymind.com via POST /objects.")
def push(
    source: str = typer.Argument(..., help=f"One of: {', '.join(available_sources())}"),
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
    # command, so users who only fetch don't need the `push` extra.
    try:
        from dotenv import find_dotenv, load_dotenv

        from .mymind_client import MymindCreds
        from .push import run_push
    except ImportError as exc:
        typer.echo(
            f"error: missing dep ({exc}). Run: uv sync --extra source --extra push",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    # Load .env from the directory the user runs `tomymind` in (and its
    # parents), not from wherever the package lives. Bare load_dotenv() starts
    # find_dotenv()'s search at this file's location — which in a pip-installed
    # tree is site-packages, so a user's project-local .env would never be
    # picked up. usecwd=True searches from the current working directory
    # instead; find_dotenv returns "" when nothing is found, which load_dotenv
    # treats as a no-op.
    load_dotenv(find_dotenv(usecwd=True))
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
