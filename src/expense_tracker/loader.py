"""Project the committed CSV files into an ephemeral SQLite database.

The CSV files under ``data/`` are the source of truth. ``build()`` drops and
recreates the ``expenses`` table on every call, so the database is always in sync
with the CSV files and can be safely deleted at any time.

Money is stored as an integer number of cents (``amount_cents``) so that SQL
``SUM`` is exact - never as a float.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import config, db

_CENTS = Decimal("100")


class InvalidRow(ValueError):
    """Raised when a CSV row cannot be parsed into a valid expense."""


def _parse_date(value: str) -> str:
    """Validate an ISO ``YYYY-MM-DD`` date and return it normalized."""
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise InvalidRow(f"invalid date {value!r} (expected YYYY-MM-DD)") from exc


def _parse_amount_cents(value: str) -> int:
    """Parse a decimal amount into an exact integer number of cents."""
    try:
        amount = Decimal(value.strip())
    except (InvalidOperation, ValueError) as exc:
        raise InvalidRow(f"invalid amount {value!r}") from exc
    # quantize to cents; reject sub-cent precision to keep totals exact
    cents = (amount * _CENTS).to_integral_value()
    if cents != amount * _CENTS:
        raise InvalidRow(f"amount {value!r} has sub-cent precision")
    return int(cents)


def _iter_rows(csv_path: Path):
    """Yield validated ``(date, amount_cents, category, description)`` tuples."""
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = set(config.COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise InvalidRow(
                f"{csv_path.name}: missing columns {sorted(missing)}"
            )
        for lineno, raw in enumerate(reader, start=2):
            category = (raw["category"] or "").strip()
            if not category:
                raise InvalidRow(f"{csv_path.name}:{lineno}: empty category")
            yield (
                _parse_date(raw["date"]),
                _parse_amount_cents(raw["amount"]),
                category,
                (raw["description"] or "").strip(),
                csv_path.name,
            )


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS expenses;
        CREATE TABLE expenses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            date         TEXT    NOT NULL,
            amount_cents INTEGER NOT NULL,
            category     TEXT    NOT NULL,
            description  TEXT    NOT NULL DEFAULT '',
            source_file  TEXT    NOT NULL
        );
        CREATE INDEX idx_expenses_date ON expenses(date);
        CREATE INDEX idx_expenses_category ON expenses(category);
        """
    )


def build(data_dir: Path | None = None, db_path: Path | None = None) -> int:
    """Rebuild the SQLite database from ``data/*.csv``. Returns the row count."""
    data_dir = data_dir or config.DATA_DIR
    db_path = db_path or config.DB_PATH

    csv_files = sorted(data_dir.glob("*.csv"))
    rows: list[tuple] = []
    for csv_path in csv_files:
        rows.extend(_iter_rows(csv_path))

    conn = db.connect(db_path)
    try:
        _create_schema(conn)
        conn.executemany(
            "INSERT INTO expenses "
            "(date, amount_cents, category, description, source_file) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def main() -> None:
    count = build()
    print(f"Loaded {count} expense(s) from {config.DATA_DIR} into {config.DB_PATH}")


if __name__ == "__main__":
    main()
