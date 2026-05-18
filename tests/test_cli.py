from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from tomymind.cli import app
from tomymind.errors import SessionError

# Click 8.3+ splits stdout/stderr on CliRunner by default.
_runner = CliRunner()

# Real-shape (NOT real) base64-encoded 32-byte HMAC key, for env stubs.
_FAKE_SECRET_B64 = base64.b64encode(b"\x01" * 32).decode()


def test_help_lists_all_commands() -> None:
    result = _runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in ("login", "fetch", "import-cookies", "push", "sources"):
        assert sub in result.stdout


def test_sources_prints_registered_sources() -> None:
    result = _runner.invoke(app, ["sources"])
    assert result.exit_code == 0
    assert "x" in result.stdout.split()


@pytest.mark.parametrize("command", ["login", "fetch", "import-cookies"])
def test_unknown_source_exits_2(command: str) -> None:
    result = _runner.invoke(app, [command, "totally-unknown"])
    assert result.exit_code == 2
    assert "Unknown source" in result.stderr


def test_push_missing_env_vars_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYMIND_API_KEY_ID", raising=False)
    monkeypatch.delenv("MYMIND_API_KEY_SECRET", raising=False)
    # Run from a clean directory so a stray .env in the repo can't supply the vars.
    monkeypatch.chdir(tmp_path)

    result = _runner.invoke(app, ["push", "x"])

    assert result.exit_code == 2
    assert "MYMIND_API_KEY_ID" in result.stderr


def test_login_session_error_exits_1() -> None:
    with patch("tomymind.cli.run_login", new=AsyncMock(side_effect=SessionError("boom"))):
        result = _runner.invoke(app, ["login", "x"])
    assert result.exit_code == 1
    assert "error: boom" in result.stderr


def test_fetch_session_error_exits_1(tmp_path: Path) -> None:
    with patch("tomymind.cli.run_fetch", new=AsyncMock(side_effect=SessionError("boom"))):
        result = _runner.invoke(app, ["fetch", "x", "--output", str(tmp_path / "out.json")])
    assert result.exit_code == 1
    assert "error: boom" in result.stderr


def test_fetch_success_prints_summary(tmp_path: Path) -> None:
    out_path = tmp_path / "out.json"

    from tomymind.models import FetchResult

    fake_result = FetchResult(source="x", item_count=3, items=[])
    with patch("tomymind.cli.run_fetch", new=AsyncMock(return_value=fake_result)):
        result = _runner.invoke(app, ["fetch", "x", "--output", str(out_path)])

    assert result.exit_code == 0
    assert "Done. 3 bookmarks" in result.stdout
    assert str(out_path) in result.stdout


def test_import_cookies_session_error_exits_1() -> None:
    with patch(
        "tomymind.cli.run_import_cookies",
        new=AsyncMock(side_effect=SessionError("boom")),
    ):
        result = _runner.invoke(app, ["import-cookies", "x"])
    assert result.exit_code == 1
    assert "error: boom" in result.stderr


def test_push_session_error_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYMIND_API_KEY_ID", "k")
    monkeypatch.setenv("MYMIND_API_KEY_SECRET", _FAKE_SECRET_B64)
    monkeypatch.chdir(tmp_path)

    with patch(
        "tomymind.push.run_push",
        new=AsyncMock(side_effect=SessionError("boom")),
    ):
        result = _runner.invoke(app, ["push", "x"])

    assert result.exit_code == 1
    assert "error: boom" in result.stderr
