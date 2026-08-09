"""Read the committed expense files into PostgreSQL. `python -m expense_tracker.loader`.

The second entry point into this package, and the only thing that writes to it: the API
reads expenses and never creates them, so this is where rows come from. It is a sibling
of deps.py rather than something below it - a CLI is not part of the HTTP wiring - and
the import-linter contracts in pyproject.toml keep the two from reaching for each other.

Idempotency lives in the loaded_file ledger, not in the expense rows. Two identical
lines - same amount, day, category and details - are two real purchases, so the rows
cannot say whether they have been loaded before. A file can, by name and by digest.

Every file is its own transaction: its ledger row and its expenses commit together or
not at all, and earlier files stay committed when a later one fails. A run that dies
half way can therefore be re-run, and picks up where it stopped.
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
from .db import Expense, ExpenseRecord, LoadedFile

# The file's first line, split on tabs. Named here once so a mismatch is reported
# against a single source of truth, and so switching format later is one edit.
#
# Checking it strictly doubles as a delimiter check: a comma-separated file splits into
# one field whose name is the whole line, which fails here on line 1 with the offending
# text quoted, rather than loading a column of nonsense.
_HEADER = ("Amount", "Currency", "Date", "Category", "Details")

# What the file calls a date. Danish exports, so day first - 02/01/2026 is 2 January.
_DATE_FORMAT = "%d/%m/%Y"

# At most two decimal places, because the column is numeric(12, 2) and a third would be
# rounded away in silence. Deliberately no limit on the integer digits: that is a range
# question, and the column answers it - see the atomicity note in load_directory.
_AMOUNT = re.compile(r"^-?\d+(?:\.\d{1,2})?$")

# ISO 4217 alpha-3, e.g. DKK. Same shape as the CHECK constraint on the column.
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class ExpenseFileError(Exception):
    """A file could not be loaded, and the run stops.

    One type for a malformed line, an unreadable directory and a file that changed
    after being loaded: all of them mean the same thing to a caller, which is that the
    data on disk needs a human before anything else happens.
    """


class LoadSummary(NamedTuple):
    """What one run did. Printed by main(), asserted on by the tests."""

    files_read: int
    files_skipped: int
    rows_inserted: int


def parse_expense_rows(filename: str, data: bytes) -> list[ExpenseRecord]:
    """Turn one file's bytes into records, or raise ExpenseFileError naming the line.

    Takes bytes rather than a path so the caller reads the file exactly once and hashes
    the same bytes it parses - a file that changed between the two would otherwise be
    recorded under a digest that never existed.

    utf-8-sig strips a byte-order mark if a spreadsheet left one, and decodes plain
    UTF-8 when it did not. Real files carry Danish text; the committed samples stay
    ASCII because CLAUDE.md asks committed source to.
    """
    try:
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
    # Enumerate from 2 so the number in a message is the line a text editor shows.
    for line_number, row in enumerate(rows[1:], start=2):
        # A trailing newline yields an empty row, and a spreadsheet often leaves a line
        # of empty columns. Neither is data and neither is an error.
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
    """A known filename arriving with a different digest: the file was edited.

    Refused rather than skipped or re-read. Skipping would make a typo fix appear to
    work while doing nothing; re-reading would either duplicate the rows that did not
    change or delete rows from a database that is meant to be a read-only view. So the
    loader stops and says which file, when it was taken in, and what to do instead.
    """
    return ExpenseFileError(
        f"{filename} changed since it was loaded on"
        + f" {loaded_at:%Y-%m-%d %H:%M:%S%z} (sha256 mismatch)."
        + " Edit-then-reload is not supported: append a new file, or rebuild with"
        + " `backend-db-reset`, `backend-db-init` and `backend-load-expenses`."
    )


async def load_directory(directory: Path, url: str) -> LoadSummary:
    """Load every *.csv in `directory`, in name order, one transaction per file.

    The directory check comes before the engine is built, so a mistyped path fails
    without opening a socket - which is what lets a test cover this path with no server.
    """
    if not directory.is_dir():
        raise ExpenseFileError(f"{directory}: not a directory")
    paths = sorted(directory.glob("*.csv"))

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
                # attributes as Any, which recommended mode's reportAny rejects, while
                # a mapped instance carries the types from the model. Five short columns
                # for one file is not a cost worth a cast to avoid.
                recorded = await session.scalar(
                    select(LoadedFile).where(LoadedFile.filename == path.name)
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
                        insert(LoadedFile)
                        .values(
                            filename=path.name, sha256=digest, row_count=len(records)
                        )
                        .returning(LoadedFile.id)
                    )
                ).scalar_one()
                if records:
                    # The 2.0 ORM bulk form: one insertmanyvalues statement rather than
                    # an INSERT per row. An out-of-range amount is caught here, by
                    # numeric(12, 2), and takes the ledger row above down with it -
                    # both are in this transaction, which has not committed yet.
                    _ = await session.execute(
                        insert(Expense),
                        [
                            {"loaded_file_id": file_id, **record._asdict()}
                            for record in records
                        ],
                    )
                await session.commit()
                rows_inserted += len(records)
    finally:
        await engine.dispose()

    return LoadSummary(len(paths), files_skipped, rows_inserted)


def main() -> int:
    """The `python -m` entry point. Returns a process exit status.

    sys.argv rather than argparse: there is one positional and no flags, and typeshed
    types argparse.Namespace attribute access as Any, which recommended mode's
    reportAny rejects - a suppression bought for nothing.
    """
    if len(sys.argv) != 2:
        print(
            "usage: python -m expense_tracker.loader <directory>\n"
            + "`pixi run backend-load-expenses` passes data/expenses/ for you.",
            file=sys.stderr,
        )
        return 2
    try:
        summary = asyncio.run(load_directory(Path(sys.argv[1]), database_url()))
    except ExpenseFileError as exc:
        # Caught rather than allowed to propagate: a traceback is the wrong shape of
        # output for a data problem the message already explains in full.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"{summary.files_read} files read, {summary.files_skipped} skipped,"
        + f" {summary.rows_inserted} rows inserted"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover  # tests call main() directly
    raise SystemExit(main())
