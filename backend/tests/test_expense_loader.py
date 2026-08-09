"""The CSV half of the loader: what it accepts, and what it refuses and why.

No database anywhere in this module. parse_expense_rows takes bytes, so almost every
case here is a byte literal - no filesystem, no server, no fixtures. The two exceptions
are marked where they appear.
"""

import asyncio
import datetime
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from expense_tracker.loader import ExpenseFileError, load_directory, main
from expense_tracker.loader import parse_expense_rows as parse

# Points at the committed data/expenses/, from backend/tests/ up to the repo root. The
# one thing in this module that knows where the real files live.
_DATA = Path(__file__).resolve().parents[2] / "data" / "expenses"

_HEADER = b"Amount\tCurrency\tDate\tCategory\tDetails\n"

# Never reached: every test here fails before a connection would be opened. Port 1 is
# the same unreachable address the repository tests use, so a mistake surfaces as a
# refused connection rather than as a wait.
_UNREACHABLE = "postgresql+asyncpg://nobody@127.0.0.1:1/none"


def test_a_valid_file_parses() -> None:
    records = parse("x.csv", _HEADER + b"775.37\tDKK\t02/01/2026\tInsurance\tCar\n")
    assert records == [
        (Decimal("775.37"), "DKK", datetime.date(2026, 1, 2), "Insurance", "Car")
    ]


def test_the_date_is_day_first() -> None:
    """02/01/2026 is 2 January, not 1 February. The whole file set is Danish."""
    (record,) = parse("x.csv", _HEADER + b"1.00\tDKK\t02/01/2026\tCar\tFuel\n")
    assert record.expense_date == datetime.date(2026, 1, 2)


def test_a_negative_amount_is_accepted() -> None:
    """A refund is a negative expense, so there is no sign check anywhere."""
    (record,) = parse("x.csv", _HEADER + b"-450.00\tDKK\t02/01/2026\tCar\tRefund\n")
    assert record.amount == Decimal("-450.00")


def test_blank_details_are_accepted() -> None:
    """An empty memo column is a real thing an export produces, not an error."""
    (record,) = parse("x.csv", _HEADER + b"1.00\tDKK\t02/01/2026\tCar\t\n")
    assert record.details == ""


def test_a_byte_order_mark_is_tolerated() -> None:
    """A spreadsheet often leaves one. utf-8-sig eats it; utf-8 would not."""
    records = parse("x.csv", b"\xef\xbb\xbf" + _HEADER + b"1.00\tDKK\t2/1/2026\tC\tD\n")
    assert len(records) == 1


def test_blank_trailing_lines_are_ignored() -> None:
    records = parse(
        "x.csv", _HEADER + b"1.00\tDKK\t02/01/2026\tCar\tFuel\n\n\t\t\t\t\n"
    )
    assert len(records) == 1


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(ExpenseFileError, match="empty"):
        _ = parse("x.csv", b"")


def test_a_comma_separated_file_is_refused() -> None:
    """The header check doubling as a delimiter check - the reason it is strict."""
    body = b"Amount,Currency,Date,Category,Details\n1.00,DKK,02/01/2026,Car,Fuel\n"
    with pytest.raises(ExpenseFileError, match="tabs, not commas"):
        _ = parse("x.csv", body)


def test_a_renamed_column_is_refused() -> None:
    with pytest.raises(ExpenseFileError, match="header"):
        _ = parse("x.csv", b"Total\tCurrency\tDate\tCategory\tDetails\n")


def test_a_reordered_header_is_refused() -> None:
    """Same five names, wrong order: the columns would be silently transposed."""
    with pytest.raises(ExpenseFileError, match="header"):
        _ = parse("x.csv", b"Currency\tAmount\tDate\tCategory\tDetails\n")


def test_a_short_row_is_refused_by_line_number() -> None:
    body = _HEADER + b"1.00\tDKK\t02/01/2026\tCar\tFuel\n2.00\tDKK\t03/01/2026\n"
    with pytest.raises(ExpenseFileError, match="line 3: expected 5"):
        _ = parse("x.csv", body)


def test_three_decimal_places_are_refused() -> None:
    """numeric(12, 2) would round it away in silence, which is the thing to prevent."""
    with pytest.raises(ExpenseFileError, match="two decimal places"):
        _ = parse("x.csv", _HEADER + b"1.005\tDKK\t02/01/2026\tCar\tFuel\n")


def test_a_comma_decimal_separator_is_refused() -> None:
    """775,37 in a tab-separated file is a locale mistake, not a second delimiter."""
    with pytest.raises(ExpenseFileError, match="amount"):
        _ = parse("x.csv", _HEADER + b"775,37\tDKK\t02/01/2026\tCar\tFuel\n")


def test_a_bad_date_is_refused() -> None:
    with pytest.raises(ExpenseFileError, match="DD/MM/YYYY"):
        _ = parse("x.csv", _HEADER + b"1.00\tDKK\t2026-01-02\tCar\tFuel\n")


def test_a_month_first_date_is_refused() -> None:
    """13 cannot be a month, so a US-format file fails rather than shifting dates."""
    with pytest.raises(ExpenseFileError, match="DD/MM/YYYY"):
        _ = parse("x.csv", _HEADER + b"1.00\tDKK\t01/13/2026\tCar\tFuel\n")


def test_a_lowercase_currency_is_refused() -> None:
    with pytest.raises(ExpenseFileError, match="ISO 4217"):
        _ = parse("x.csv", _HEADER + b"1.00\tdkk\t02/01/2026\tCar\tFuel\n")


def test_a_blank_category_is_refused() -> None:
    with pytest.raises(ExpenseFileError, match="category is blank"):
        _ = parse("x.csv", _HEADER + b"1.00\tDKK\t02/01/2026\t\tFuel\n")


def test_invalid_utf8_is_refused() -> None:
    with pytest.raises(ExpenseFileError, match="UTF-8"):
        _ = parse("x.csv", _HEADER + b"1.00\tDKK\t02/01/2026\tCar\t\xff\xfe\n")


def test_the_committed_sample_files_parse() -> None:
    """The only thing that catches a malformed committed sample without a database.

    Reads data/expenses/ itself, so adding a file there puts it through the parser on
    the next `pixi run backend-test`.
    """
    paths = sorted(_DATA.glob("*.csv"))
    assert paths, f"no sample files under {_DATA}"
    for path in paths:
        assert parse(path.name, path.read_bytes()), f"{path.name} parsed to no rows"


def test_a_missing_directory_is_refused(tmp_path: Path) -> None:
    """Pins the ordering inside load_directory: is_dir() before create_async_engine.

    That is what lets this assert against an unreachable DSN without hanging - if the
    check ever moved below the engine, this test would fail on a connection error
    rather than on the message it asks for.
    """
    pending = load_directory(tmp_path / "nope", _UNREACHABLE)
    with pytest.raises(ExpenseFileError, match="not a directory"):
        _ = asyncio.run(pending)


def test_running_without_a_directory_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reaches no database: the arity check precedes everything, DATABASE_URL too."""
    monkeypatch.setattr(sys, "argv", ["loader"])
    assert main() == 2
    assert "usage:" in capsys.readouterr().err
