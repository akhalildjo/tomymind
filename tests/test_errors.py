from __future__ import annotations

import pytest

from tomymind.errors import SessionError


def test_session_error_is_runtime_error() -> None:
    assert issubclass(SessionError, RuntimeError)


def test_session_error_preserves_message() -> None:
    err = SessionError("session lost")
    assert str(err) == "session lost"


def test_session_error_raises_and_matches() -> None:
    with pytest.raises(SessionError, match="abc"):
        raise SessionError("abc")
