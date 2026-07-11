"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with row access by column name.

    Rows are returned as ``sqlite3.Row`` so callers can index by column name
    (``row["amount"]``) and convert to plain dicts easily.
    """
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
