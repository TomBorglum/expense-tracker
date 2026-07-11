"""Filesystem paths and shared constants.

Paths are resolved relative to the repository root (three levels up from this
file: ``src/expense_tracker/config.py`` -> repo root) so tasks work regardless of
the current working directory.
"""

import os
from pathlib import Path

# Repo root: .../expense-tracker
ROOT_DIR = Path(__file__).resolve().parents[2]

# Committed CSV source of truth.
DATA_DIR = Path(os.environ.get("EXPENSE_DATA_DIR", ROOT_DIR / "data"))

# Ephemeral SQLite cache, rebuilt from the CSV files on every run (gitignored).
DB_PATH = Path(os.environ.get("EXPENSE_DB_PATH", ROOT_DIR / "expenses.sqlite"))

# CSV columns, in order. Also the SQLite column order.
COLUMNS = ("date", "amount", "category", "description")

# Server defaults.
HOST = os.environ.get("EXPENSE_HOST", "127.0.0.1")
PORT = int(os.environ.get("EXPENSE_PORT", "8000"))
