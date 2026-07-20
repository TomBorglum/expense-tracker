"""Tests for the SQLite connection helpers and schema."""

import sqlite3

import pytest
from flask import Flask

from expense_tracker.db import get_db


def test_get_db_returns_same_connection_within_context(app: Flask) -> None:
    with app.app_context():
        assert get_db() is get_db()


def test_connection_closed_after_context(app: Flask) -> None:
    with app.app_context():
        db = get_db()

    # Using a closed connection raises rather than silently reconnecting.
    with pytest.raises(sqlite3.ProgrammingError):
        _ = db.execute("SELECT 1")


def test_schema_creates_expense_table(app: Flask) -> None:
    with app.app_context():
        row = (
            get_db()
            .execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'expense'")
            .fetchone()
        )

    assert row is not None


def test_rows_are_addressable_by_column_name(app: Flask) -> None:
    with app.app_context():
        db = get_db()
        _ = db.execute(
            "INSERT INTO expense (incurred_on, amount, description, category)"
            " VALUES (?, ?, ?, ?)",
            ("2026-07-20", 1250, "Coffee beans", "Groceries"),
        )
        row = db.execute("SELECT description, amount FROM expense").fetchone()

    assert row["description"] == "Coffee beans"
    assert row["amount"] == 1250
