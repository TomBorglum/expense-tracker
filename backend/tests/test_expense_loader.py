"""The month-file half of the loader: what it accepts and what it refuses.

No database here. parse_expense_records takes bytes, so almost every case is a byte
literal - no filesystem and no server.
"""

import asyncio
import datetime
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import make_url

from expense_tracker.expense_loader import ExpenseFileError, load_directory, main
from expense_tracker.expense_loader import parse_expense_records as parse

# The committed backend/tests/data/expenses/, beside this file. The currency tests
# still reach up one level: their files are the app's, these are the suite's own.
_DATA = Path(__file__).resolve().parent / "data" / "expenses"

# Never reached: every test here fails before a connection would be opened.
_UNREACHABLE = make_url("postgresql+asyncpg://nobody@127.0.0.1:1/none")

_MOMENT = b"'2026-01-02T00:00:00+01:00'"

# One imported record's `extracted` fields, as the format writes them. Each test that
# bends one field passes the rest of this through.
_IMPORT = (
    b"      datetime: "
    + _MOMENT
    + b"\n"
    + b"      key: ACCIDENT\n"
    + b"      action: import\n"
    + b"      amount: '775.37'\n"
    + b"      currency: DKK\n"
    + b"      category: Insurance\n"
    + b"      details: Car\n"
)


def _month(*extracted: bytes) -> bytes:
    """One month file around the `extracted` blocks given, one record per block."""
    records = b"".join(
        b"  - record: 'line'\n    extracted:\n" + one for one in extracted
    )
    return b'---\nheader: \'"Date";"Amount";"Text";\'\nrecords:\n' + records


def _bend(field: bytes, value: bytes) -> bytes:
    """`_IMPORT` with one field given another value."""
    lines = [
        value if line.strip().startswith(field + b":") else line
        for line in _IMPORT.splitlines(keepends=True)
    ]
    return b"".join(lines)


def _bent(field: bytes, value: bytes) -> bytes:
    """A whole month file holding one record, with one field given another value.

    Built outside the `pytest.raises` blocks below rather than inside them, so the one
    call each block holds is the one expected to raise.
    """
    return _month(_bend(field, value))


def test_a_valid_file_parses() -> None:
    records = parse("x.yaml", _month(_IMPORT))
    assert records == [
        (Decimal("775.37"), "DKK", datetime.date(2026, 1, 2), "Insurance", "Car")
    ]


def test_the_date_is_the_one_the_file_states() -> None:
    """The offset is never applied: this is the date the bank's statement shows.

    Copenhagen midnight read as UTC would be 1 January, and the record would land
    outside the month file holding it.
    """
    (record,) = parse("x.yaml", _month(_IMPORT))
    assert record.expense_date == datetime.date(2026, 1, 2)


def test_a_utc_date_is_read_as_written_too() -> None:
    """The other bank's spelling: a `Z` offset, and still the date in the file."""
    body = _bent(b"datetime", b"      datetime: '2026-01-02T23:30:00Z'\n")
    (record,) = parse("x.yaml", body)
    assert record.expense_date == datetime.date(2026, 1, 2)


def test_a_negative_amount_is_accepted() -> None:
    """A credit is a negative expense, so there is no sign check."""
    body = _bent(b"amount", b"      amount: '-450.00'\n")
    (record,) = parse("x.yaml", body)
    assert record.amount == Decimal("-450.00")


@pytest.mark.parametrize("value", [b"0", b"0.00", b"-0.00", b"-0"])
def test_a_zero_amount_is_refused(value: bytes) -> None:
    """Every spelling of nothing, including the negative ones.

    The sign is what makes an expense a credit, so -0.00 is not a tiny credit - it
    is the same non-entry 0.00 is, and expense_amount_not_zero backstops it.
    """
    body = _bent(b"amount", b"      amount: '" + value + b"'\n")
    with pytest.raises(ExpenseFileError, match=r"amount .* is zero"):
        _ = parse("x.yaml", body)


def test_blank_details_are_accepted() -> None:
    (record,) = parse("x.yaml", _bent(b"details", b"      details: ''\n"))
    assert record.details == ""


def test_a_discarded_record_is_skipped() -> None:
    """A discard states only its two fields, and yields no expense."""
    discard = b"      datetime: " + _MOMENT + b"\n      action: discard\n"
    assert parse("x.yaml", _month(discard, _IMPORT, discard)) == [
        (Decimal("775.37"), "DKK", datetime.date(2026, 1, 2), "Insurance", "Car")
    ]


def test_a_month_holding_no_records_parses_to_none() -> None:
    """`records: []` is what a month every record of which was discarded writes."""
    assert parse("x.yaml", b"---\nheader: 'H'\nrecords: []\n") == []


def test_a_byte_order_mark_is_tolerated() -> None:
    """PyYAML's own reader strips one, so the bytes are handed over undecoded."""
    assert len(parse("x.yaml", b"\xef\xbb\xbf" + _month(_IMPORT))) == 1


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(ExpenseFileError, match="empty"):
        _ = parse("x.yaml", b"")


def test_a_file_that_is_not_yaml_is_refused() -> None:
    with pytest.raises(ExpenseFileError, match="not valid YAML"):
        _ = parse("x.yaml", b"header: 'H'\nrecords: [\n")


def test_a_second_document_is_refused() -> None:
    """One file is one month, so a second document is a file of unknown shape."""
    body = b"---\nheader: 'H'\nrecords: []\n---\nheader: 'I'\nrecords: []\n"
    with pytest.raises(ExpenseFileError, match="not valid YAML"):
        _ = parse("x.yaml", body)


def test_a_root_that_is_not_a_mapping_is_refused() -> None:
    """A bare list was the shape before the two keys, and is not read as one."""
    with pytest.raises(ExpenseFileError, match="must be a mapping"):
        _ = parse("x.yaml", b"---\n- amount: '1.00'\n")


def test_a_missing_header_is_refused() -> None:
    """The one field read and not used: it is what says this is expense data."""
    with pytest.raises(ExpenseFileError, match="header"):
        _ = parse("x.yaml", b"---\nrecords: []\n")


def test_a_blank_header_is_refused() -> None:
    with pytest.raises(ExpenseFileError, match="header is blank"):
        _ = parse("x.yaml", b"---\nheader: ''\nrecords: []\n")


def test_records_that_are_not_a_list_is_refused() -> None:
    with pytest.raises(ExpenseFileError, match="records: Input should be a valid list"):
        _ = parse("x.yaml", b"---\nheader: 'H'\nrecords: {}\n")


def test_a_record_without_an_extracted_block_is_refused() -> None:
    with pytest.raises(ExpenseFileError, match=r"records\[0\].extracted"):
        _ = parse("x.yaml", b"---\nheader: 'H'\nrecords:\n  - record: 'line'\n")


def test_an_unknown_action_is_refused() -> None:
    """Neither import nor discard means a decision this loader cannot act on."""
    body = _month(b"      datetime: " + _MOMENT + b"\n      action: maybe\n")
    with pytest.raises(ExpenseFileError, match="'import', 'discard'"):
        _ = parse("x.yaml", body)


def test_an_import_missing_a_field_is_refused() -> None:
    """An import states every field, so a missing one is not an empty one."""
    body = _month(
        b"".join(
            line
            for line in _IMPORT.splitlines(keepends=True)
            if b"currency" not in line
        )
    )
    with pytest.raises(ExpenseFileError, match=r"currency: Field required"):
        _ = parse("x.yaml", body)


def test_a_refusal_names_the_record_it_is_about() -> None:
    """The index is what finds the record in a file of ninety."""
    body = _month(_IMPORT, _IMPORT, _bend(b"amount", b"      amount: '1.005'\n"))
    with pytest.raises(ExpenseFileError, match=r"records\[2\].extracted.import.amount"):
        _ = parse("x.yaml", body)


def test_an_unquoted_amount_is_refused() -> None:
    """YAML 1.1 resolves it to a float, and a float is how a total drifts a cent."""
    body = _bent(b"amount", b"      amount: 775.37\n")
    with pytest.raises(ExpenseFileError, match="must be text, not float; quote it"):
        _ = parse("x.yaml", body)


def test_an_unquoted_datetime_is_refused() -> None:
    """YAML 1.1 resolves it to a datetime, which is not what the format writes."""
    body = _bent(b"datetime", b"      datetime: 2026-01-02T00:00:00+01:00\n")
    with pytest.raises(ExpenseFileError, match="must be text, not datetime; quote it"):
        _ = parse("x.yaml", body)


def test_three_decimal_places_are_refused() -> None:
    """numeric(12, 2) would round it away in silence."""
    body = _bent(b"amount", b"      amount: '1.005'\n")
    with pytest.raises(ExpenseFileError, match="two decimal places"):
        _ = parse("x.yaml", body)


def test_a_comma_decimal_separator_is_refused() -> None:
    """The bank writes 775,37 in the record beside it; the amount is not its copy."""
    body = _bent(b"amount", b"      amount: '775,37'\n")
    with pytest.raises(ExpenseFileError, match="amount"):
        _ = parse("x.yaml", body)


def test_a_bad_datetime_is_refused() -> None:
    body = _bent(b"datetime", b"      datetime: 'noon'\n")
    with pytest.raises(ExpenseFileError, match="RFC 3339"):
        _ = parse("x.yaml", body)


def test_a_datetime_without_an_offset_is_refused() -> None:
    """One bank exports UTC and another local time, so a bare clock is ambiguous."""
    body = _bent(b"datetime", b"      datetime: '2026-01-02T00:00:00'\n")
    with pytest.raises(ExpenseFileError, match="no UTC offset"):
        _ = parse("x.yaml", body)


def test_a_lowercase_currency_is_refused() -> None:
    body = _bent(b"currency", b"      currency: dkk\n")
    with pytest.raises(ExpenseFileError, match="ISO 4217"):
        _ = parse("x.yaml", body)


def test_a_blank_category_is_refused() -> None:
    body = _bent(b"category", b"      category: ' '\n")
    with pytest.raises(ExpenseFileError, match="category is blank"):
        _ = parse("x.yaml", body)


@pytest.mark.parametrize(
    "value", [b"'Food:'", b"':Food'", b"'Food::Drink'", b"':'", b"'Food: :Drink'"]
)
def test_a_category_that_is_not_a_path_is_refused(value: bytes) -> None:
    """Refused here and not only by the CHECK: main() catches ExpenseFileError and
    nothing else, so the constraint alone would surface as an IntegrityError traceback
    naming no file. `Food: :Drink` gets here because each level is stripped first."""
    body = _bent(b"category", b"      category: " + value + b"\n")
    with pytest.raises(ExpenseFileError, match="category is not a path"):
        _ = parse("x.yaml", body)


def test_a_category_path_is_stripped_level_by_level() -> None:
    """Not just the whole field: a level keeping its inner spaces would store a node
    that renders identically to the real one and never merges with it."""
    body = _bent(b"category", b"      category: ' Settlement : Alice '\n")
    assert [record.category for record in parse("x.yaml", body)] == ["Settlement:Alice"]


def test_a_category_path_of_several_levels_is_kept_whole() -> None:
    """The negative control for the refusals above, and the shape the feature exists
    for: the path is stored as written, one column, no second table."""
    body = _bent(b"category", b"      category: Settlement:Alice:Spain\n")
    assert [record.category for record in parse("x.yaml", body)] == [
        "Settlement:Alice:Spain"
    ]


def test_invalid_utf8_is_refused() -> None:
    body = _bent(b"details", b"      details: '\xff\xfe'\n")
    with pytest.raises(ExpenseFileError, match="not valid YAML"):
        _ = parse("x.yaml", body)


def test_a_field_this_loader_does_not_read_is_ignored() -> None:
    """`key` is one, and the format takes new fields over time."""
    body = _month(_IMPORT + b"      note: something later\n")
    assert len(parse("x.yaml", body)) == 1


def test_the_committed_sample_files_parse() -> None:
    """Reads backend/tests/data/expenses/ itself, so adding a file there puts it through
    the parser on the next `pixi run backend-test`."""
    paths = sorted(_DATA.glob("*.yaml"))
    assert paths, f"no sample files under {_DATA}"
    for path in paths:
        assert parse(path.name, path.read_bytes()), f"{path.name} parsed to no rows"


def test_a_missing_directory_is_refused(tmp_path: Path) -> None:
    """Pins the ordering inside load_directory: is_dir() before create_async_engine,
    which is what lets this assert against an unreachable DSN without hanging."""
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
