"""The TSV half of the currency loader: what it accepts and what it refuses.

No database here. parse_currency_rows takes bytes, so almost every case is a byte
literal - no filesystem and no server.
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import make_url

from expense_tracker.currency_loader import CurrencyFileError, load_directory, main
from expense_tracker.currency_loader import parse_currency_rows as parse

# The committed backend/data/currencies/, from backend/tests/ up one level.
_DATA = Path(__file__).resolve().parents[1] / "data" / "currencies"

_HEADER = b"FROM_CURRENCY\tTO_CURRENCY\tEXCHANGE_RATE\n"

# Never reached: every test here fails before a connection would be opened.
_UNREACHABLE = make_url("postgresql+asyncpg://nobody@127.0.0.1:1/none")


def test_a_valid_file_parses() -> None:
    records = parse("x.tsv", _HEADER + b"DKK\tEUR\t0.134048\n")
    assert records == [("DKK", "EUR", Decimal("0.134048"))]


def test_trailing_zeros_survive() -> None:
    """7.460000 stays six decimal places: Decimal keeps the scale a float would drop."""
    (record,) = parse("x.tsv", _HEADER + b"EUR\tDKK\t7.460000\n")
    assert str(record.exchange_rate) == "7.460000"


def test_a_whole_number_rate_is_accepted() -> None:
    (record,) = parse("x.tsv", _HEADER + b"DKK\tDKK\t1\n")
    assert record.exchange_rate == Decimal(1)


def test_a_byte_order_mark_is_tolerated() -> None:
    """A spreadsheet often leaves one. utf-8-sig eats it; utf-8 would not."""
    records = parse("x.tsv", b"\xef\xbb\xbf" + _HEADER + b"DKK\tEUR\t0.134048\n")
    assert len(records) == 1


def test_blank_trailing_lines_are_ignored() -> None:
    records = parse("x.tsv", _HEADER + b"DKK\tEUR\t0.134048\n\n\t\t\n")
    assert len(records) == 1


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(CurrencyFileError, match="empty"):
        _ = parse("x.tsv", b"")


def test_a_comma_separated_file_is_refused() -> None:
    """The header check doubling as a delimiter check."""
    body = b"FROM_CURRENCY,TO_CURRENCY,EXCHANGE_RATE\nDKK,EUR,0.134048\n"
    with pytest.raises(CurrencyFileError, match="tabs, not commas"):
        _ = parse("x.tsv", body)


def test_a_renamed_column_is_refused() -> None:
    with pytest.raises(CurrencyFileError, match="header"):
        _ = parse("x.tsv", b"FROM\tTO_CURRENCY\tEXCHANGE_RATE\n")


def test_a_reordered_header_is_refused() -> None:
    """Same three names, wrong order: the pair would be silently inverted."""
    with pytest.raises(CurrencyFileError, match="header"):
        _ = parse("x.tsv", b"TO_CURRENCY\tFROM_CURRENCY\tEXCHANGE_RATE\n")


def test_a_short_row_is_refused_by_line_number() -> None:
    body = _HEADER + b"DKK\tEUR\t0.134048\nDKK\tUSD\n"
    with pytest.raises(CurrencyFileError, match="line 3: expected 3"):
        _ = parse("x.tsv", body)


def test_seven_decimal_places_are_refused() -> None:
    """numeric(18, 6) would round it away in silence."""
    with pytest.raises(CurrencyFileError, match="six decimal places"):
        _ = parse("x.tsv", _HEADER + b"DKK\tEUR\t0.1340485\n")


def test_a_comma_decimal_separator_is_refused() -> None:
    """0,134048 in a tab-separated file is a locale mistake, not a second delimiter."""
    with pytest.raises(CurrencyFileError, match="exchange rate"):
        _ = parse("x.tsv", _HEADER + b"DKK\tEUR\t0,134048\n")


def test_a_negative_rate_is_refused() -> None:
    """Unlike an expense amount, where a negative is a refund."""
    with pytest.raises(CurrencyFileError, match="exchange rate"):
        _ = parse("x.tsv", _HEADER + b"DKK\tEUR\t-0.134048\n")


def test_a_zero_rate_is_refused() -> None:
    with pytest.raises(CurrencyFileError, match="zero"):
        _ = parse("x.tsv", _HEADER + b"DKK\tEUR\t0.000000\n")


def test_a_lowercase_currency_is_refused() -> None:
    with pytest.raises(CurrencyFileError, match="ISO 4217"):
        _ = parse("x.tsv", _HEADER + b"dkk\tEUR\t0.134048\n")


def test_a_blank_target_currency_is_refused() -> None:
    """Named by side, so the message says which of the two columns is wrong."""
    with pytest.raises(CurrencyFileError, match="to currency"):
        _ = parse("x.tsv", _HEADER + b"DKK\t\t0.134048\n")


def test_invalid_utf8_is_refused() -> None:
    with pytest.raises(CurrencyFileError, match="UTF-8"):
        _ = parse("x.tsv", _HEADER + b"DKK\tEUR\t\xff\xfe\n")


def test_the_committed_sample_files_parse() -> None:
    """Reads backend/data/currencies/ itself, so adding a file there puts it through
    the parser on the next `pixi run backend-test`."""
    paths = sorted(_DATA.glob("*.tsv"))
    assert paths, f"no sample files under {_DATA}"
    for path in paths:
        assert parse(path.name, path.read_bytes()), f"{path.name} parsed to no rows"


def test_a_missing_directory_is_refused(tmp_path: Path) -> None:
    """Pins the ordering inside load_directory: is_dir() before create_async_engine,
    which is what lets this assert against an unreachable DSN without hanging."""
    pending = load_directory(tmp_path / "nope", _UNREACHABLE)
    with pytest.raises(CurrencyFileError, match="not a directory"):
        _ = asyncio.run(pending)


def test_a_bad_file_is_refused_before_the_database_is_touched(tmp_path: Path) -> None:
    """Every file is parsed before anything is deleted, so a typo cannot empty the
    table. The unreachable DSN is the assertion: reaching it would raise something
    else."""
    _ = (tmp_path / "rates.tsv").write_bytes(_HEADER + b"DKK\tEUR\t0,134048\n")

    pending = load_directory(tmp_path, _UNREACHABLE)
    with pytest.raises(CurrencyFileError, match="exchange rate"):
        _ = asyncio.run(pending)


def test_running_without_a_directory_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reaches no directory: the arity check precedes everything, DATABASE_URL too."""
    monkeypatch.setattr(sys, "argv", ["loader"])
    assert main() == 2
    assert "usage:" in capsys.readouterr().err
