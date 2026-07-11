"""Pure, Flask-free query functions over the ephemeral SQLite database.

Every function takes an open ``sqlite3.Connection`` so the module stays free of
web-framework and global state and can be unit-tested directly.

Money is stored as integer cents; these functions convert to ``Decimal`` dollars
(cents / 100) so callers never do float arithmetic on money.
"""

import sqlite3
from decimal import Decimal
from typing import NamedTuple


def _cents_to_dollars(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(Decimal("0.01"))


class Expense(NamedTuple):
    date: str
    amount: Decimal
    category: str
    description: str


class CategoryTotal(NamedTuple):
    category: str
    total: Decimal


class MonthTotal(NamedTuple):
    month: str  # "YYYY-MM"
    total: Decimal


def _where(
    date_from: str | None, date_to: str | None, category: str | None
) -> tuple[str, list[str]]:
    """Build a WHERE clause and its parameters from optional filters."""
    clauses: list[str] = []
    params: list[str] = []
    if date_from:
        clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        params.append(date_to)
    if category:
        clauses.append("category = ?")
        params.append(category)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def all_expenses(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    category: str | None = None,
) -> list[Expense]:
    """Return matching expenses, most recent first."""
    where, params = _where(date_from, date_to, category)
    rows = conn.execute(
        "SELECT date, amount_cents, category, description "
        f"FROM expenses{where} ORDER BY date DESC, id DESC",
        params,
    ).fetchall()
    return [
        Expense(r["date"], _cents_to_dollars(r["amount_cents"]), r["category"], r["description"])
        for r in rows
    ]


def total_by_category(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    category: str | None = None,
) -> list[CategoryTotal]:
    """Return summed totals per category, largest first."""
    where, params = _where(date_from, date_to, category)
    rows = conn.execute(
        "SELECT category, SUM(amount_cents) AS total "
        f"FROM expenses{where} GROUP BY category ORDER BY total DESC, category",
        params,
    ).fetchall()
    return [CategoryTotal(r["category"], _cents_to_dollars(r["total"])) for r in rows]


def total_by_month(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    category: str | None = None,
) -> list[MonthTotal]:
    """Return summed totals per calendar month, oldest first."""
    where, params = _where(date_from, date_to, category)
    rows = conn.execute(
        "SELECT substr(date, 1, 7) AS month, SUM(amount_cents) AS total "
        f"FROM expenses{where} GROUP BY month ORDER BY month",
        params,
    ).fetchall()
    return [MonthTotal(r["month"], _cents_to_dollars(r["total"])) for r in rows]


def grand_total(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    category: str | None = None,
) -> Decimal:
    """Return the total of all matching expenses."""
    where, params = _where(date_from, date_to, category)
    row = conn.execute(
        f"SELECT COALESCE(SUM(amount_cents), 0) AS total FROM expenses{where}",
        params,
    ).fetchone()
    return _cents_to_dollars(row["total"])


def categories(conn: sqlite3.Connection) -> list[str]:
    """Return the distinct categories (unfiltered), for the filter dropdown."""
    rows = conn.execute(
        "SELECT DISTINCT category FROM expenses ORDER BY category"
    ).fetchall()
    return [r["category"] for r in rows]


def date_range(conn: sqlite3.Connection) -> tuple[str | None, str | None]:
    """Return the (min, max) expense date, or (None, None) when empty."""
    row = conn.execute("SELECT MIN(date) AS lo, MAX(date) AS hi FROM expenses").fetchone()
    return (row["lo"], row["hi"])
