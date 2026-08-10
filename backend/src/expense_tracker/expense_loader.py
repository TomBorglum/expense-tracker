"""Reads the committed expense files into PostgreSQL.

`python -m expense_tracker.expense_loader <directory>`. The only thing that writes to
the database; the API reads and never creates.
"""

import asyncio
import csv
import datetime
import hashlib
import io
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import database_url
from .expense_repository import Expense, ExpenseRecord, LoadedExpenseFile

# The file's first line, split on tabs. Checking it strictly doubles as a delimiter
# check: a comma-separated file splits into one field and fails here.
_HEADER = ("Amount", "Currency", "Date", "Category", "Details")

# Day first: 02/01/2026 is 2 January.
_DATE_FORMAT = "%d/%m/%Y"

# At most two decimal places, because the column is numeric(12, 2) and a third would
# be rounded away in silence. No limit on the integer digits - the column owns range.
_AMOUNT = re.compile(r"^-?\d+(?:\.\d{1,2})?$")

# ISO 4217 alpha-3, e.g. DKK.
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class ExpenseFileError(Exception):
    """A file could not be loaded, and the run stops."""


class LoadSummary(NamedTuple):
    """What one run did."""

    files_read: int
    files_skipped: int
    rows_inserted: int


def parse_expense_rows(filename: str, data: bytes) -> list[ExpenseRecord]:
    """Turns one file's bytes into records, or raises ExpenseFileError naming the line.

    Takes bytes rather than a path so the caller hashes exactly what it parses.
    """
    try:
        # utf-8-sig strips a byte-order mark if a spreadsheet left one, and decodes
        # plain UTF-8 when it did not.
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ExpenseFileError(f"{filename}: not valid UTF-8 ({exc})") from exc

    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter="\t"))
    if not rows:
        raise ExpenseFileError(f"{filename}: file is empty")
    if tuple(rows[0]) != _HEADER:
        raise ExpenseFileError(
            f"{filename}: line 1 is not the expected header."
            + f" Expected {list(_HEADER)}, got {rows[0]}."
            + " Fields are separated by tabs, not commas."
        )

    records: list[ExpenseRecord] = []
    # From 2, so a number in a message is the line a text editor shows.
    for line_number, row in enumerate(rows[1:], start=2):
        # A trailing newline yields an empty row, and a spreadsheet often leaves a
        # line of empty columns. Neither is data and neither is an error.
        if not any(field.strip() for field in row):
            continue
        records.append(_parse_row(filename, line_number, row))
    return records


def _parse_row(filename: str, line_number: int, row: list[str]) -> ExpenseRecord:
    """One data line, validated field by field so the message says which one."""

    def refuse(problem: str) -> ExpenseFileError:
        return ExpenseFileError(f"{filename}: line {line_number}: {problem}")

    if len(row) != len(_HEADER):
        raise refuse(f"expected {len(_HEADER)} tab-separated fields, got {len(row)}")

    raw_amount, raw_currency, raw_date, category, details = (
        field.strip() for field in row
    )

    if not _AMOUNT.match(raw_amount):
        raise refuse(
            f"amount {raw_amount!r} is not a number with at most two decimal places"
        )
    try:
        amount = Decimal(raw_amount)
    except InvalidOperation as exc:  # pragma: no cover  # unreachable past the regex
        raise refuse(f"amount {raw_amount!r} is not a decimal") from exc

    if not _CURRENCY.match(raw_currency):
        raise refuse(f"currency {raw_currency!r} is not a three-letter ISO 4217 code")

    try:
        expense_date = datetime.datetime.strptime(raw_date, _DATE_FORMAT).date()
    except ValueError as exc:
        raise refuse(f"date {raw_date!r} is not DD/MM/YYYY") from exc

    if not category:
        raise refuse("category is blank")

    # details is allowed to be empty: a blank memo is a real thing an export produces.
    return ExpenseRecord(amount, raw_currency, expense_date, category, details)


def _changed_file_error(
    filename: str, loaded_at: datetime.datetime
) -> ExpenseFileError:
    """A known filename arriving with a different digest: the file was edited."""
    return ExpenseFileError(
        f"{filename} changed since it was loaded on"
        + f" {loaded_at:%Y-%m-%d %H:%M:%S%z} (sha256 mismatch)."
        + " Edit-then-reload is not supported: append a new file, or rebuild with"
        + " `backend-db-reset`, `backend-db-init` and `backend-load-expenses`."
    )


async def load_directory(directory: Path, url: str) -> LoadSummary:
    """Loads every *.tsv in `directory`, in name order, one transaction per file."""
    # Before the engine is built, so a mistyped path fails without opening a socket.
    if not directory.is_dir():
        raise ExpenseFileError(f"{directory}: not a directory")
    paths = sorted(directory.glob("*.tsv"))

    files_skipped = 0
    rows_inserted = 0
    engine = create_async_engine(url)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        for path in paths:
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            async with sessions() as session:
                # The whole entity rather than the two columns wanted: a Row types its
                # attributes as Any, which reportAny rejects, while a mapped instance
                # carries the model's types.
                recorded = await session.scalar(
                    select(LoadedExpenseFile).where(
                        LoadedExpenseFile.filename == path.name
                    )
                )
                if recorded is not None:
                    if recorded.sha256 == digest:
                        files_skipped += 1
                        continue
                    raise _changed_file_error(path.name, recorded.loaded_at)

                records = parse_expense_rows(path.name, data)
                # The ledger row first, for its generated id. RETURNING rather than a
                # second SELECT: one round trip, and the value cannot be raced.
                file_id = (
                    await session.execute(
                        insert(LoadedExpenseFile)
                        .values(
                            filename=path.name, sha256=digest, row_count=len(records)
                        )
                        .returning(LoadedExpenseFile.id)
                    )
                ).scalar_one()
                if records:
                    # The 2.0 ORM bulk form: one insertmanyvalues statement rather
                    # than an INSERT per row. An out-of-range amount is caught here by
                    # numeric(12, 2) and takes the uncommitted ledger row with it.
                    _ = await session.execute(
                        insert(Expense),
                        [
                            {"loaded_expense_file_id": file_id, **record._asdict()}
                            for record in records
                        ],
                    )
                await session.commit()
                rows_inserted += len(records)
    finally:
        await engine.dispose()

    return LoadSummary(len(paths), files_skipped, rows_inserted)


def main() -> int:
    """The `python -m` entry point. Returns a process exit status."""
    # sys.argv rather than argparse: there is one positional and no flags, and
    # typeshed types Namespace attribute access as Any, which reportAny rejects.
    if len(sys.argv) != 2:
        print(
            "usage: python -m expense_tracker.expense_loader <directory>\n"
            + "`pixi run backend-load-expenses` passes data/expenses/ for you.",
            file=sys.stderr,
        )
        return 2
    try:
        summary = asyncio.run(load_directory(Path(sys.argv[1]), database_url()))
    except ExpenseFileError as exc:
        # Caught rather than allowed to propagate: a traceback is the wrong shape of
        # output for a data problem the message already explains.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"{summary.files_read} files read, {summary.files_skipped} skipped,"
        + f" {summary.rows_inserted} rows inserted"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover  # tests call main() directly
    raise SystemExit(main())
