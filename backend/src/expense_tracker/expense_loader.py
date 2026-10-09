"""Reads the month files the expense data repository writes into PostgreSQL.

`python -m expense_tracker.expense_loader <directory>`. The only thing that writes to
the database; the API reads and never creates.
"""

import asyncio
import datetime
import hashlib
import re
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Annotated, ClassVar, Literal, NamedTuple, cast

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError
from pydantic_core import PydanticCustomError
from sqlalchemy import URL, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .category_filter import strip_path
from .config import database_url
from .expense_repository import Expense, ExpenseRecord, LoadedExpenseFile

# At most two decimal places, because the column is numeric(12, 2) and a third would
# be rounded away in silence. No limit on the integer digits - the column owns range.
_AMOUNT = re.compile(r"^-?\d+(?:\.\d{1,2})?$")

# The same path shape schema.sql states as a CHECK: one or more levels, none empty.
_CATEGORY_PATH = re.compile(r"\A[^:]+(:[^:]+)*\Z")

# ISO 4217 alpha-3, e.g. DKK.
_CURRENCY = re.compile(r"^[A-Z]{3}$")

# typeshed types yaml.safe_load as returning Any, which reportAny refuses, so it is
# reached through one cast rather than through a suppression at the call.
_safe_load: Callable[[bytes], object] = cast(Callable[[bytes], object], yaml.safe_load)


class ExpenseFileError(Exception):
    """A file could not be loaded, and the run stops."""


class LoadSummary(NamedTuple):
    """What one run did."""

    files_read: int
    files_skipped: int
    rows_inserted: int


def _text(value: object) -> str:
    """One field as the format writes it, or raises.

    YAML 1.1 resolves an unquoted 2438.47 to a float and an unquoted date-time to a
    datetime, and the format quotes both, so anything that is not text is refused rather
    than read through str().
    """
    if not isinstance(value, str):
        raise PydanticCustomError(
            "not_text",
            "must be text, not {kind}; quote it",
            {"kind": type(value).__name__},
        )
    return value


def _header_line(value: object) -> str:
    """The export header the file states, which is checked and then goes nowhere.

    Read so that a YAML file which is not a month file is refused rather than taken for
    one holding no expenses.
    """
    text = _text(value)
    if not text:
        raise PydanticCustomError("blank_header", "header is blank")
    return text


def _day(value: object) -> datetime.date:
    """One `datetime` field as the day it falls on, or raises.

    The offset is required but never applied: the date wanted is the one the file
    states, which is the date the bank's own statement shows.
    """
    text = _text(value)
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError as exc:
        raise PydanticCustomError(
            "not_a_datetime",
            "datetime {value} is not an RFC 3339 date-time ({problem})",
            {"value": repr(text), "problem": str(exc)},
        ) from exc
    if moment.tzinfo is None:
        raise PydanticCustomError(
            "naive_datetime",
            "datetime {value} has no UTC offset; one bank exports UTC and another"
            + " local time, so a bare wall clock would mean two different things",
            {"value": repr(text)},
        )
    return moment.date()


def _amount(value: object) -> Decimal:
    """One `amount` field as a Decimal, or raises."""
    text = _text(value)
    if not _AMOUNT.match(text):
        raise PydanticCustomError(
            "not_a_decimal",
            "amount {value} is not a number with at most two decimal places",
            {"value": repr(text)},
        )
    amount = Decimal(text)
    # Decimal("-0.00") and Decimal("0") both compare equal to zero, so this one
    # check covers every spelling the regex lets through.
    if amount == 0:
        raise PydanticCustomError(
            "zero_amount",
            "amount {value} is zero; an expense of nothing is not an entry",
            {"value": repr(text)},
        )
    return amount


def _currency(value: object) -> str:
    """One `currency` field, refused rather than uppercased."""
    text = _text(value)
    if not _CURRENCY.match(text):
        raise PydanticCustomError(
            "not_iso_4217",
            "currency {value} is not a three-letter ISO 4217 code",
            {"value": repr(text)},
        )
    return text


def _category(value: object) -> str:
    """One `category` field as a path, each level stripped and none of them empty."""
    # Every level, not the whole value: "Settlement : Alice" would otherwise store its
    # inner spaces and become a node that renders identically to Settlement:Alice while
    # never merging with it.
    text = strip_path(_text(value))
    if not text:
        raise PydanticCustomError("blank_category", "category is blank")
    if _CATEGORY_PATH.match(text) is None:
        # Before the database sees it: main() catches ExpenseFileError and nothing
        # else, so the CHECK alone would surface as a bare IntegrityError traceback.
        raise PydanticCustomError("not_a_category_path", "category is not a path")
    return text


def _details(value: object) -> str:
    """One `details` field. Stripped, and allowed to be empty."""
    return _text(value).strip()


class _Mapping(BaseModel):
    """A mapping the format writes, read for the fields this loader uses."""

    # Stated rather than left to pydantic's default: `key` is a field deliberately
    # skipped, and the format's mappings take new fields over time.
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")


class _Extracted(_Mapping):
    """What every record states, whatever was decided about it."""

    expense_date: Annotated[datetime.date, BeforeValidator(_day)] = Field(
        alias="datetime"
    )


class _Imported(_Extracted):
    """A record to load. An import states every field."""

    action: Literal["import"]
    amount: Annotated[Decimal, BeforeValidator(_amount)]
    currency: Annotated[str, BeforeValidator(_currency)]
    category: Annotated[str, BeforeValidator(_category)]
    details: Annotated[str, BeforeValidator(_details)]


class _Discarded(_Extracted):
    """A record the other repository dropped. A discard states only these two."""

    action: Literal["discard"]


class _Record(_Mapping):
    """One export record and what was decided about it. Only `extracted` is read."""

    extracted: Annotated[_Imported | _Discarded, Field(discriminator="action")]


class _MonthFile(_Mapping):
    """One month file: the export's header line, and its records in file order."""

    header: Annotated[str, BeforeValidator(_header_line)]
    records: list[_Record]


def parse_expense_records(filename: str, data: bytes) -> list[ExpenseRecord]:
    """Turns one month file's bytes into records, or raises ExpenseFileError.

    Takes bytes rather than a path so the caller hashes exactly what it parses. A
    discarded record yields nothing: it is one the other repository decided against.
    """
    try:
        # Bytes rather than decoded text: PyYAML's reader strips a byte-order mark and
        # decodes UTF-8 itself, and raises here on invalid bytes and on a second
        # document as it does on a syntax error.
        document = _safe_load(data)
    except yaml.YAMLError as exc:
        raise ExpenseFileError(f"{filename}: not valid YAML ({exc})") from exc

    # Both before the model, which would otherwise answer for the whole file with a
    # message naming a private class.
    if document is None:
        raise ExpenseFileError(f"{filename}: file is empty")
    if not isinstance(document, dict):
        raise ExpenseFileError(
            f"{filename}: must be a mapping holding 'header' and 'records', not"
            + f" {type(document).__name__}"
        )

    try:
        month = _MonthFile.model_validate(document)
    except ValidationError as exc:
        raise _refused_file_error(filename, exc) from exc

    return [
        ExpenseRecord(
            record.extracted.amount,
            record.extracted.currency,
            record.extracted.expense_date,
            record.extracted.category,
            record.extracted.details,
        )
        for record in month.records
        if isinstance(record.extracted, _Imported)
    ]


def _refused_file_error(filename: str, exc: ValidationError) -> ExpenseFileError:
    """A file that did not validate, named by its first problem and where that is.

    The first only, because a file this repository did not write is a file the one that
    did write it would have refused, and the location is what finds it: `records[12]` is
    the thirteenth entry under `records`.
    """
    first = exc.errors()[0]
    where = "".join(
        f"[{part}]" if isinstance(part, int) else f".{part}" for part in first["loc"]
    ).lstrip(".")
    problem = f"{where}: {first['msg']}" if where else first["msg"]
    return ExpenseFileError(f"{filename}: {problem}")


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


async def load_directory(directory: Path, url: URL) -> LoadSummary:
    """Loads every *.yaml in `directory`, in name order, one transaction per file."""
    # Before the engine is built, so a mistyped path fails without opening a socket.
    if not directory.is_dir():
        raise ExpenseFileError(f"{directory}: not a directory")
    paths = sorted(directory.glob("*.yaml"))

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

                records = parse_expense_records(path.name, data)
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
            + "`pixi run backend-load-expenses` passes $EXPENSE_DATA_DIR for you.",
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
