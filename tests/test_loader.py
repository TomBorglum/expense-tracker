"""Tests for the CSV -> SQLite loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from expense_tracker import db, loader


def _build(tmp_path: Path, csv_text: str) -> int:
    (tmp_path / "in.csv").write_text(csv_text, encoding="utf-8")
    return loader.build(data_dir=tmp_path, db_path=tmp_path / "out.sqlite")


def test_build_loads_all_rows(data_dir, tmp_path):
    db_path = tmp_path / "out.sqlite"
    count = loader.build(data_dir=data_dir, db_path=db_path)
    assert count == 4
    conn = db.connect(db_path)
    try:
        # Money is stored as exact integer cents.
        total = conn.execute("SELECT SUM(amount_cents) FROM expenses").fetchone()[0]
        assert total == 5420 + 1200 + 4830 + 1500
    finally:
        conn.close()


def test_build_is_idempotent(data_dir, tmp_path):
    db_path = tmp_path / "out.sqlite"
    loader.build(data_dir=data_dir, db_path=db_path)
    count = loader.build(data_dir=data_dir, db_path=db_path)
    assert count == 4  # rebuild drops and recreates, no duplication


def test_multiple_csv_files_are_concatenated(tmp_path):
    (tmp_path / "a.csv").write_text(
        "date,amount,category,description\n2026-01-01,1.00,X,one\n", encoding="utf-8"
    )
    (tmp_path / "b.csv").write_text(
        "date,amount,category,description\n2026-02-01,2.00,Y,two\n", encoding="utf-8"
    )
    count = loader.build(data_dir=tmp_path, db_path=tmp_path / "out.sqlite")
    assert count == 2


def test_invalid_date_rejected(tmp_path):
    with pytest.raises(loader.InvalidRow):
        _build(tmp_path, "date,amount,category,description\n01-01-2026,1.00,X,bad date\n")


def test_invalid_amount_rejected(tmp_path):
    with pytest.raises(loader.InvalidRow):
        _build(tmp_path, "date,amount,category,description\n2026-01-01,abc,X,bad amount\n")


def test_subcent_precision_rejected(tmp_path):
    with pytest.raises(loader.InvalidRow):
        _build(tmp_path, "date,amount,category,description\n2026-01-01,1.005,X,too precise\n")


def test_empty_category_rejected(tmp_path):
    with pytest.raises(loader.InvalidRow):
        _build(tmp_path, "date,amount,category,description\n2026-01-01,1.00,,no category\n")


def test_missing_column_rejected(tmp_path):
    with pytest.raises(loader.InvalidRow):
        _build(tmp_path, "date,amount,category\n2026-01-01,1.00,X\n")
