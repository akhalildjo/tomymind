from __future__ import annotations

import json
from pathlib import Path

from tomymind.push import load_ledger, save_ledger


def test_load_ledger_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_ledger(tmp_path / "nope.json") == set()


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    ledger = tmp_path / ".pushed_x.json"
    save_ledger(ledger, {"abc", "def", "ghi"})

    raw = json.loads(ledger.read_text(encoding="utf-8"))
    assert raw == ["abc", "def", "ghi"]  # sorted on disk for stable diffs

    assert load_ledger(ledger) == {"abc", "def", "ghi"}


def test_save_ledger_creates_parent_dir(tmp_path: Path) -> None:
    ledger = tmp_path / "deeply" / "nested" / ".pushed_x.json"
    save_ledger(ledger, {"x"})
    assert ledger.exists()
