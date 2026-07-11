"""Expense tracker: a read-only dashboard over CSV-sourced expenses.

CSV files under ``data/`` are the source of truth. On startup they are projected
into an ephemeral SQLite database that the Flask server queries. The database is
never committed and is rebuilt from the CSV files on every run.
"""

__all__ = ["__version__"]

__version__ = "0.0.0"
