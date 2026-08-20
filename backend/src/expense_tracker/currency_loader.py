"""Reads the committed exchange rate files into PostgreSQL.

`python -m expense_tracker.currency_loader <directory>`. Replaces the table's whole
contents, so an edited rate reloads where an edited expense file is refused.
"""

import asyncio
import csv
import io
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import URL, delete, insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import database_url
from .currency_repository import CurrencyRate, CurrencyRateRecord

# The file's first line, split on tabs. Checking it strictly doubles as a delimiter
# check: a comma-separated file splits into one field and fails here.
_HEADER = ("FROM_CURRENCY", "TO_CURRENCY", "EXCHANGE_RATE")

# ISO 4217 alpha-3, e.g. DKK.
_CURRENCY = re.compile(r"^[A-Z]{3}$")

# At most six decimal places, because the column is numeric(18, 6) and a seventh would
# be rounded away in silence. Unsigned: a rate that is not positive converts nothing,
# and the CHECK constraint refuses it too.
_RATE = re.compile(r"^\d+(?:\.\d{1,6})?$")


class CurrencyFileError(Exception):
    """A file could not be loaded, and the run stops."""


class LoadSummary(NamedTuple):
    """What one run did."""

    files_read: int
    rows_deleted: int
    rows_inserted: int


def parse_currency_rows(filename: str, data: bytes) -> list[CurrencyRateRecord]:
    """Turns one file's bytes into records, or raises CurrencyFileError by line."""
    try:
        # utf-8-sig strips a byte-order mark if a spreadsheet left one, and decodes
        # plain UTF-8 when it did not.
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CurrencyFileError(f"{filename}: not valid UTF-8 ({exc})") from exc

    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter="\t"))
    if not rows:
        raise CurrencyFileError(f"{filename}: file is empty")
    if tuple(rows[0]) != _HEADER:
        raise CurrencyFileError(
            f"{filename}: line 1 is not the expected header."
            + f" Expected {list(_HEADER)}, got {rows[0]}."
            + " Fields are separated by tabs, not commas."
        )

    records: list[CurrencyRateRecord] = []
    # From 2, so a number in a message is the line a text editor shows.
    for line_number, row in enumerate(rows[1:], start=2):
        # A trailing newline yields an empty row, and a spreadsheet often leaves a
        # line of empty columns. Neither is data and neither is an error.
        if not any(field.strip() for field in row):
            continue
        records.append(_parse_row(filename, line_number, row))
    return records


def _parse_row(filename: str, line_number: int, row: list[str]) -> CurrencyRateRecord:
    """One data line, validated field by field so the message says which one."""

    def refuse(problem: str) -> CurrencyFileError:
        return CurrencyFileError(f"{filename}: line {line_number}: {problem}")

    if len(row) != len(_HEADER):
        raise refuse(f"expected {len(_HEADER)} tab-separated fields, got {len(row)}")

    raw_from, raw_to, raw_rate = (field.strip() for field in row)

    for label, code in (("from", raw_from), ("to", raw_to)):
        if not _CURRENCY.match(code):
            raise refuse(
                f"{label} currency {code!r} is not a three-letter ISO 4217 code"
            )

    if not _RATE.match(raw_rate):
        raise refuse(
            f"exchange rate {raw_rate!r} is not a positive number with at most six"
            + " decimal places"
        )
    try:
        exchange_rate = Decimal(raw_rate)
    except InvalidOperation as exc:  # pragma: no cover  # unreachable past the regex
        raise refuse(f"exchange rate {raw_rate!r} is not a decimal") from exc
    if not exchange_rate:
        raise refuse("exchange rate is zero")

    return CurrencyRateRecord(raw_from, raw_to, exchange_rate)


async def load_directory(directory: Path, url: URL) -> LoadSummary:
    """Replaces every rate with the ones in `directory`'s *.tsv, in one transaction."""
    # Before the engine is built, so a mistyped path fails without opening a socket.
    if not directory.is_dir():
        raise CurrencyFileError(f"{directory}: not a directory")
    paths = sorted(directory.glob("*.tsv"))

    # Every file parsed before anything is deleted, so a bad file leaves the rates that
    # are already loaded exactly as they were.
    records: list[CurrencyRateRecord] = []
    for path in paths:
        records.extend(parse_currency_rows(path.name, path.read_bytes()))

    engine = create_async_engine(url)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            # One transaction for the pair: nothing observes the table empty, and a row
            # the database refuses takes the delete with it.
            #
            # RETURNING rather than rowcount, which SQLAlchemy types as Any on a Result.
            deleted = len(
                (
                    await session.scalars(
                        delete(CurrencyRate).returning(CurrencyRate.id)
                    )
                ).all()
            )
            if records:
                # The 2.0 ORM bulk form: one insertmanyvalues statement rather than an
                # INSERT per row.
                _ = await session.execute(
                    insert(CurrencyRate), [record._asdict() for record in records]
                )
            await session.commit()
    finally:
        await engine.dispose()

    return LoadSummary(len(paths), deleted, len(records))


def main() -> int:
    """The `python -m` entry point. Returns a process exit status."""
    # sys.argv rather than argparse: there is one positional and no flags, and
    # typeshed types Namespace attribute access as Any, which reportAny rejects.
    if len(sys.argv) != 2:
        print(
            "usage: python -m expense_tracker.currency_loader <directory>\n"
            + "`pixi run backend-load-currencies` passes data/currencies/ for you.",
            file=sys.stderr,
        )
        return 2
    try:
        summary = asyncio.run(load_directory(Path(sys.argv[1]), database_url()))
    except CurrencyFileError as exc:
        # Caught rather than allowed to propagate: a traceback is the wrong shape of
        # output for a data problem the message already explains.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"{summary.files_read} files read, {summary.rows_deleted} rows deleted,"
        + f" {summary.rows_inserted} rows inserted"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover  # tests call main() directly
    raise SystemExit(main())
