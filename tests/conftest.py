"""Shared fixtures: a SQLite database built from a temporary CSV directory."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from expense_tracker import db, loader

SAMPLE_CSV = """\
date,amount,category,description
2026-05-03,54.20,Groceries,Weekly shop
2026-05-07,12.00,Transport,Bus pass
2026-06-15,48.30,Groceries,Weekly shop
2026-06-28,15.00,Entertainment,Cinema
"""


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    (tmp_path / "expenses.csv").write_text(SAMPLE_CSV, encoding="utf-8")
    return tmp_path


@pytest.fixture
def conn(data_dir: Path, tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.sqlite"
    loader.build(data_dir=data_dir, db_path=db_path)
    connection = db.connect(db_path)
    yield connection
    connection.close()
