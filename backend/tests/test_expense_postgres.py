"""The loader and the expenses endpoint against a real PostgreSQL server.

Every test here TRUNCATEs both tables, before and after. That wipes whatever
`pixi run backend-load-expenses` put in a developer's database - run it again
afterwards. Doing it before as well as after stops a killed run poisoning the next one.
"""

import asyncio
import datetime
import os
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel, TypeAdapter
from sqlalchemy import insert, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.testclient import TestClient

from expense_tracker import (
    CategoryPayload,
    ExpensePayload,
    PeriodTotalPayload,
    create_app,
)
from expense_tracker.config import database_url
from expense_tracker.expense_loader import ExpenseFileError, load_directory, main
from expense_tracker.expense_repository import Expense, LoadedExpenseFile

# Registered in pyproject.toml, which --strict-markers requires.
pytestmark = pytest.mark.postgres

_DATA = Path(__file__).resolve().parent / "data" / "expenses"


class _Collection[T](BaseModel):
    """The object every endpoint wraps its rows in, so each body can gain fields."""

    items: list[T]


# Each one validates the envelope, so `.items` at a call site is the rows inside it.
_EXPENSES = TypeAdapter(_Collection[ExpensePayload])
_CATEGORIES = TypeAdapter(_Collection[CategoryPayload])
_TOTALS = TypeAdapter(_Collection[PeriodTotalPayload])


async def _truncate() -> None:
    """Both tables in one statement: PostgreSQL refuses to truncate a referenced one
    alone, and RESTART IDENTITY keeps ids predictable across tests."""
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            _ = await session.execute(
                text("TRUNCATE expense, loaded_expense_file RESTART IDENTITY")
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _expenses() -> list[tuple[Decimal, str, datetime.date, str, str]]:
    """Every expense as plain tuples, oldest first.

    Mapped instances rather than a Row, so the columns keep the model's types;
    flattened inside the session, because the instances detach when it closes.
    """
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            rows = await session.scalars(
                select(Expense).order_by(Expense.expense_date, Expense.id)
            )
            return [
                (r.amount, r.currency, r.expense_date, r.category, r.details)
                for r in rows
            ]
    finally:
        await engine.dispose()


async def _ledger() -> list[tuple[str, str, int]]:
    """The loaded_expense_file rows as (filename, sha256, row_count), by filename."""
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            rows = await session.scalars(
                select(LoadedExpenseFile).order_by(LoadedExpenseFile.filename)
            )
            return [(r.filename, r.sha256, r.row_count) for r in rows]
    finally:
        await engine.dispose()


async def _insert_expense(amount: Decimal, category: str = "Car") -> None:
    """One expense inserted past the loader, so a CHECK answers for itself."""
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            file_id = (
                await session.execute(
                    insert(LoadedExpenseFile)
                    .values(filename="direct.yaml", sha256="0" * 64, row_count=1)
                    .returning(LoadedExpenseFile.id)
                )
            ).scalar_one()
            _ = await session.execute(
                insert(Expense).values(
                    loaded_expense_file_id=file_id,
                    amount=amount,
                    currency="DKK",
                    expense_date=datetime.date(2026, 1, 2),
                    category=category,
                    details="Nothing",
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.fixture(scope="module", autouse=True)
def require_postgres() -> None:
    """Skip locally when no server answers; fail under CI, so a database that did not
    come up cannot go green."""
    try:
        _ = asyncio.run(_expenses())
    except (RuntimeError, SQLAlchemyError, OSError) as exc:
        if os.environ.get("CI") == "true":
            raise
        pytest.skip(
            f"no PostgreSQL at DATABASE_URL; run `pixi run backend-db-init` ({exc})"
        )


@pytest.fixture(autouse=True)
def empty_tables() -> Iterator[None]:
    asyncio.run(_truncate())
    yield
    asyncio.run(_truncate())


def _month_file(*rows: str) -> str:
    """A month file holding one imported record per row.

    A row is the five fields the database holds, tab-separated, in the order
    ExpenseRecord names them and with the date as `DD/MM/YYYY` - so a test reads as its
    expenses rather than as YAML. The offset the `datetime` is written with is stated
    because the format requires one and is never applied, winter being when every date
    below falls.
    """
    records = ""
    for row in rows:
        amount, currency, day, category, details = row.split("\t")
        when = datetime.datetime.strptime(day, "%d/%m/%Y").date()
        records += (
            "  - record: 'line'\n"
            + "    extracted:\n"
            + f"      datetime: '{when.isoformat()}T00:00:00+01:00'\n"
            + "      action: import\n"
            + f"      amount: '{amount}'\n"
            + f"      currency: '{currency}'\n"
            + f"      category: '{category}'\n"
            + f"      details: '{details}'\n"
        )
    return "---\nheader: 'H'\nrecords:\n" + records


def _write(directory: Path, name: str, *rows: str) -> Path:
    path = directory / name
    _ = path.write_text(_month_file(*rows), encoding="utf-8")
    return path


def test_loading_a_directory_inserts_every_row(tmp_path: Path) -> None:
    _ = _write(tmp_path, "01.yaml", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    _ = _write(
        tmp_path,
        "02.yaml",
        "1250.00\tDKK\t02/02/2026\tHousing\tRent",
        "99.95\tDKK\t19/02/2026\tUtilities\tInternet",
    )

    summary = asyncio.run(load_directory(tmp_path, database_url()))

    assert summary == (2, 0, 3)
    assert len(asyncio.run(_expenses())) == 3
    assert [(name, count) for name, _sha, count in asyncio.run(_ledger())] == [
        ("01.yaml", 1),
        ("02.yaml", 2),
    ]


def test_identical_rows_in_one_file_both_survive(tmp_path: Path) -> None:
    """The property the whole design exists for: two fuel stops of the same amount on
    the same day are two purchases, and a content-hash key would collapse them."""
    row = "611.23\tDKK\t14/01/2026\tCar\tFuel"
    _ = _write(tmp_path, "01.yaml", row, row)

    summary = asyncio.run(load_directory(tmp_path, database_url()))

    assert summary.rows_inserted == 2
    assert len(asyncio.run(_expenses())) == 2


def test_reloading_an_unchanged_directory_skips_every_file(tmp_path: Path) -> None:
    _ = _write(tmp_path, "01.yaml", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    _ = _write(tmp_path, "02.yaml", "1250.00\tDKK\t02/02/2026\tHousing\tRent")
    first = asyncio.run(load_directory(tmp_path, database_url()))

    second = asyncio.run(load_directory(tmp_path, database_url()))

    assert first == (2, 0, 2)
    assert second == (2, 2, 0)
    # The point of the ledger: a second run is a no-op, not a doubling.
    assert len(asyncio.run(_expenses())) == 2


def test_a_new_file_beside_a_loaded_one_is_still_loaded(tmp_path: Path) -> None:
    """Appending is the supported workflow, so it must not be caught by the skip."""
    _ = _write(tmp_path, "01.yaml", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    _ = asyncio.run(load_directory(tmp_path, database_url()))
    _ = _write(tmp_path, "02.yaml", "1250.00\tDKK\t02/02/2026\tHousing\tRent")

    summary = asyncio.run(load_directory(tmp_path, database_url()))

    assert summary == (2, 1, 1)
    assert len(asyncio.run(_expenses())) == 2


def test_an_edited_file_is_refused_by_name_and_load_date(tmp_path: Path) -> None:
    path = _write(tmp_path, "01.yaml", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    _ = asyncio.run(load_directory(tmp_path, database_url()))
    # A typo fix, which is exactly the case that must not pass silently.
    _ = path.write_text(
        _month_file("775.38\tDKK\t02/01/2026\tInsurance\tCar"), encoding="utf-8"
    )

    pending = load_directory(tmp_path, database_url())
    with pytest.raises(ExpenseFileError, match=r"01\.yaml changed since it was loaded"):
        _ = asyncio.run(pending)

    # Neither skipped nor re-read: the database is exactly as it was.
    assert [amount for amount, *_rest in asyncio.run(_expenses())] == [
        Decimal("775.37")
    ]


def test_a_file_that_fails_midway_leaves_earlier_files_committed(
    tmp_path: Path,
) -> None:
    """Per-file atomicity in both directions.

    02's amount passes the parser - the regex constrains decimal places, not magnitude
    - and overflows numeric(12, 2) at the database, so this exercises a rollback rather
    than a parse error. Its ledger row is in the same transaction, so it goes too.
    """
    _ = _write(tmp_path, "01-good.yaml", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    _ = _write(tmp_path, "02-bad.yaml", "1234567890123.45\tDKK\t02/02/2026\tHousing\tR")

    pending = load_directory(tmp_path, database_url())
    with pytest.raises(SQLAlchemyError):
        _ = asyncio.run(pending)

    assert len(asyncio.run(_expenses())) == 1
    # 02-bad.yaml left no ledger row, so re-running after fixing the file retries it.
    assert [name for name, _sha, _count in asyncio.run(_ledger())] == ["01-good.yaml"]


def test_the_committed_sample_files_load(tmp_path: Path) -> None:
    """Puts backend/tests/data/expenses/ through the real database path inside
    `backend-test`. tmp_path is unused but keeps the signature uniform."""
    assert tmp_path.is_dir()
    summary = asyncio.run(load_directory(_DATA, database_url()))

    assert summary.files_read == len(sorted(_DATA.glob("*.yaml")))
    assert summary.files_skipped == 0
    assert summary.rows_inserted == len(asyncio.run(_expenses()))


def test_the_endpoint_returns_the_rows_oldest_first(tmp_path: Path) -> None:
    # Written newest first, so the expected order is the ORDER BY's doing and not the
    # order the loader read the lines in.
    _ = _write(
        tmp_path,
        "01.yaml",
        "1250.00\tDKK\t02/02/2026\tHousing\tRent",
        "775.37\tDKK\t02/01/2026\tInsurance\tCar",
    )
    _ = asyncio.run(load_directory(tmp_path, database_url()))

    # Context-managed, so the lifespan builds a real engine against the real database.
    with TestClient(create_app()) as client:
        response = client.get("/api/expenses")

    assert response.status_code == 200
    body = _EXPENSES.validate_json(response.content).items
    assert [row.date for row in body] == ["2026-01-02", "2026-02-02"]
    # Decimal out of numeric, string into JSON, trailing zero intact.
    assert [row.amount for row in body] == ["775.37", "1250.00"]


def test_the_endpoint_returns_an_empty_list_when_nothing_is_loaded() -> None:
    """The empty table answering 200, against a real one rather than a fake."""
    with TestClient(create_app()) as client:
        response = client.get("/api/expenses")

    assert response.status_code == 200
    assert _EXPENSES.validate_json(response.content).items == []


def test_the_categories_endpoint_lists_each_category_once_in_name_order(
    tmp_path: Path,
) -> None:
    # One category repeats and none is written in name order, so both the DISTINCT
    # and the ORDER BY are the query's doing and not the file's.
    _ = _write(
        tmp_path,
        "01.yaml",
        "1250.00\tDKK\t02/01/2026\tHousing\tRent",
        "775.37\tDKK\t03/01/2026\tInsurance\tCar",
        "35.00\tDKK\t04/01/2026\tHousing\tLight bulbs",
        "100.00\tDKK\t05/01/2026\tCar\tFuel",
    )
    _ = asyncio.run(load_directory(tmp_path, database_url()))

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses/categories")

    assert response.status_code == 200
    body = _CATEGORIES.validate_json(response.content).items
    assert [row.category for row in body] == ["Car", "Housing", "Insurance"]


def test_the_categories_endpoint_returns_an_empty_list_when_nothing_is_loaded() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/expenses/categories")

    assert response.status_code == 200
    assert _CATEGORIES.validate_json(response.content).items == []


def _load_four_days(directory: Path) -> None:
    """One expense on each of four days, so a range can leave rows on either side."""
    _ = _write(
        directory,
        "01.yaml",
        "100.00\tDKK\t01/01/2026\tCar\tFuel",
        "200.00\tDKK\t15/01/2026\tCar\tFuel",
        "300.00\tDKK\t31/01/2026\tCar\tFuel",
        "400.00\tDKK\t01/02/2026\tCar\tFuel",
    )
    _ = asyncio.run(load_directory(directory, database_url()))


def test_a_date_range_returns_only_the_expenses_inside_it(tmp_path: Path) -> None:
    """The WHERE clause itself, which the HTTP suite's fake cannot show: it records the
    bounds and filters nothing."""
    _load_four_days(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/expenses", params={"from_date": "2026-01-02", "to_date": "2026-01-31"}
        )

    assert response.status_code == 200
    body = _EXPENSES.validate_json(response.content).items
    # Oldest first still, and the 01/01 and 01/02 rows left out on either side.
    assert [row.date for row in body] == ["2026-01-15", "2026-01-31"]


def test_both_bounds_of_a_date_range_are_inclusive(tmp_path: Path) -> None:
    """An expense dated exactly on either bound is in: picking the first and last of a
    month is how a client asks for that month."""
    _load_four_days(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/expenses", params={"from_date": "2026-01-01", "to_date": "2026-01-31"}
        )

    assert [row.date for row in _EXPENSES.validate_json(response.content).items] == [
        "2026-01-01",
        "2026-01-15",
        "2026-01-31",
    ]


def test_one_bound_alone_leaves_the_other_side_open(tmp_path: Path) -> None:
    _load_four_days(tmp_path)

    with TestClient(create_app()) as client:
        from_only = client.get("/api/expenses", params={"from_date": "2026-01-31"})
        to_only = client.get("/api/expenses", params={"to_date": "2026-01-01"})

    assert [row.date for row in _EXPENSES.validate_json(from_only.content).items] == [
        "2026-01-31",
        "2026-02-01",
    ]
    assert [row.date for row in _EXPENSES.validate_json(to_only.content).items] == [
        "2026-01-01"
    ]


def test_a_date_range_matching_nothing_is_still_an_empty_list(tmp_path: Path) -> None:
    """A range with no expenses in it is the empty table's case again: a state, not a
    fault."""
    _load_four_days(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/expenses", params={"from_date": "2026-06-01", "to_date": "2026-06-30"}
        )

    assert response.status_code == 200
    assert _EXPENSES.validate_json(response.content).items == []


def _load_three_categories(directory: Path) -> None:
    """Three categories over two months, so a filter can leave rows out on either
    side of a month and the totals' extent can shrink with it."""
    _ = _write(
        directory,
        "01.yaml",
        "100.00\tDKK\t05/01/2026\tFood\tGroceries",
        "1250.00\tDKK\t01/02/2026\tHousing\tRent",
        "200.00\tDKK\t10/02/2026\tFood\tGroceries",
        "611.23\tDKK\t14/02/2026\tCar\tFuel",
    )
    _ = asyncio.run(load_directory(directory, database_url()))


def _load_a_tree(directory: Path) -> None:
    """A three-level subtree beside a depth-1 category, and a name that merely starts
    with the subtree's own - so a prefix of levels is told from one of characters."""
    _ = _write(
        directory,
        "01.yaml",
        "100.00\tDKK\t05/01/2026\tGroceries\tFood",
        "200.00\tDKK\t06/01/2026\tSettlement:Alice\tDinner",
        "300.00\tDKK\t07/01/2026\tSettlement:Alice:Spain\tHotel",
        "400.00\tDKK\t08/01/2026\tSettlement:Bob\tTaxi",
        "500.00\tDKK\t09/01/2026\tSettlementFund\tShares",
    )
    _ = asyncio.run(load_directory(directory, database_url()))


def test_a_category_returns_only_the_expenses_in_it(tmp_path: Path) -> None:
    """The IN clause itself, which the HTTP suite's fake cannot show: it records the
    filter and filters nothing."""
    _load_three_categories(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses", params={"category": "Food"})

    assert response.status_code == 200
    body = _EXPENSES.validate_json(response.content).items
    # Oldest first still, with the Housing and Car rows between them left out.
    assert [(row.date, row.category) for row in body] == [
        ("2026-01-05", "Food"),
        ("2026-02-10", "Food"),
    ]


def test_two_categories_return_the_expenses_in_either(tmp_path: Path) -> None:
    _load_three_categories(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses", params={"category": ["Food", "Car"]})

    assert [
        (row.date, row.category)
        for row in _EXPENSES.validate_json(response.content).items
    ] == [
        ("2026-01-05", "Food"),
        ("2026-02-10", "Food"),
        ("2026-02-14", "Car"),
    ]


def test_a_category_nobody_spent_in_is_still_an_empty_list(tmp_path: Path) -> None:
    """A category with no expenses is the empty table's case again: a state, not a
    fault. The filter is not checked against /api/expenses/categories first."""
    _load_three_categories(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses", params={"category": "Travel"})

    assert response.status_code == 200
    assert _EXPENSES.validate_json(response.content).items == []


def test_a_category_narrows_what_the_totals_are_taken_over(tmp_path: Path) -> None:
    """The filter is applied in SQL, so the other categories are not in the sum and
    the calendar runs over the rows that were left, as it does for a date range."""
    _load_three_categories(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/expenses/totals", params={"period": "month", "category": "Car"}
        )

    # Only February holds a Car row, so January is not a period at all.
    assert _TOTALS.validate_json(response.content).items == [
        PeriodTotalPayload(
            period="2026-02",
            from_date="2026-02-01",
            to_date="2026-02-28",
            amount="611.23",
            currency="DKK",
        )
    ]


def test_a_category_matches_its_descendants_as_well(tmp_path: Path) -> None:
    """The clause the whole feature turns on, and the one thing the HTTP suite cannot
    show. SettlementFund is the control: it shares every character of the prefix and
    is still not under Settlement, because the match is by level."""
    _load_a_tree(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses", params={"category": "Settlement"})

    assert response.status_code == 200
    body = _EXPENSES.validate_json(response.content).items
    assert [(row.date, row.category) for row in body] == [
        ("2026-01-06", "Settlement:Alice"),
        ("2026-01-07", "Settlement:Alice:Spain"),
        ("2026-01-08", "Settlement:Bob"),
    ]


def test_a_depth_one_category_still_matches_exactly_what_it_did(
    tmp_path: Path,
) -> None:
    """Prefix matching over a category that carries no path is plain equality, which
    is why every request written before paths existed still means what it meant."""
    _load_a_tree(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses", params={"category": "Groceries"})

    body = _EXPENSES.validate_json(response.content).items
    assert [(row.date, row.category) for row in body] == [("2026-01-05", "Groceries")]


def test_a_mid_level_node_matches_itself_and_everything_below(tmp_path: Path) -> None:
    _load_a_tree(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses", params={"category": "Settlement:Alice"})

    body = _EXPENSES.validate_json(response.content).items
    assert [row.category for row in body] == [
        "Settlement:Alice",
        "Settlement:Alice:Spain",
    ]


def test_a_leaf_matches_only_itself(tmp_path: Path) -> None:
    _load_a_tree(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/expenses", params={"category": "Settlement:Alice:Spain"}
        )

    body = _EXPENSES.validate_json(response.content).items
    assert [row.category for row in body] == ["Settlement:Alice:Spain"]


def test_a_node_and_its_own_child_return_each_row_once(tmp_path: Path) -> None:
    """The names are OR'd into one WHERE, so overlapping subtrees cannot duplicate a
    row - a property someone might later "fix" with a DISTINCT that is not needed."""
    _load_a_tree(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/expenses",
            params=[("category", "Settlement"), ("category", "Settlement:Alice")],
        )

    body = _EXPENSES.validate_json(response.content).items
    assert [row.category for row in body] == [
        "Settlement:Alice",
        "Settlement:Alice:Spain",
        "Settlement:Bob",
    ]


def test_a_wildcard_in_a_category_name_is_matched_literally(tmp_path: Path) -> None:
    """autoescape=True, which nothing else in the suite reaches. Without it the LIKE
    reads the % in the name as a wildcard, and 1005:Fees - which starts with 100 and
    has a separator later - would come back as though it sat under 100%."""
    _ = _write(
        tmp_path,
        "01.yaml",
        "100.00\tDKK\t05/01/2026\t100%\tOne",
        "200.00\tDKK\t06/01/2026\t100%:Fees\tTwo",
        "300.00\tDKK\t07/01/2026\t1005:Fees\tThree",
    )
    _ = asyncio.run(load_directory(tmp_path, database_url()))

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses", params={"category": "100%"})

    body = _EXPENSES.validate_json(response.content).items
    assert [row.category for row in body] == ["100%", "100%:Fees"]


def test_a_node_with_no_expense_of_its_own_is_still_listed(tmp_path: Path) -> None:
    """Settlement is where nobody filed anything directly, so only the per-level
    truncation puts it in the list - and without it the node could not be picked."""
    _load_a_tree(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses/categories", params={"to_level": "2"})

    body = _CATEGORIES.validate_json(response.content).items
    assert [(row.category, row.name, row.parent) for row in body] == [
        ("Groceries", "Groceries", None),
        ("Settlement", "Settlement", None),
        ("Settlement:Alice", "Alice", "Settlement"),
        ("Settlement:Bob", "Bob", "Settlement"),
        ("SettlementFund", "SettlementFund", None),
    ]


def test_a_bare_categories_request_lists_the_top_level_only(tmp_path: Path) -> None:
    """What a client that never heard of the parameters gets, over data that has
    depth: the outermost level of every path, once each."""
    _load_a_tree(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses/categories")

    body = _CATEGORIES.validate_json(response.content).items
    assert [row.category for row in body] == [
        "Groceries",
        "Settlement",
        "SettlementFund",
    ]


def test_from_level_two_lists_exactly_the_second_level(tmp_path: Path) -> None:
    """One generation: no depth-1 name and nothing from the third level. Pins the
    array_length guard - without it, a slice past the end returns the whole array and
    Groceries would be listed here as well."""
    _load_a_tree(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses/categories", params={"from_level": "2"})

    body = _CATEGORIES.validate_json(response.content).items
    assert [row.category for row in body] == ["Settlement:Alice", "Settlement:Bob"]


def test_a_level_range_lists_every_level_in_it_once_each(tmp_path: Path) -> None:
    """Settlement is derived at levels 1, 2 and 3 alike, so this is also what proves
    the UNION deduplicates across the legs. The order is byte order, the cluster being
    initdb --locale=C: ':' is 0x3A and sorts before every letter, which is why the
    whole Settlement subtree precedes SettlementFund."""
    _load_a_tree(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses/categories", params={"to_level": "3"})

    body = _CATEGORIES.validate_json(response.content).items
    assert [row.category for row in body] == [
        "Groceries",
        "Settlement",
        "Settlement:Alice",
        "Settlement:Alice:Spain",
        "Settlement:Bob",
        "SettlementFund",
    ]


def test_a_level_nobody_goes_that_deep_is_still_an_empty_list(tmp_path: Path) -> None:
    """The empty-table rule again: a level with no category at it is an answer."""
    _load_a_tree(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses/categories", params={"from_level": "4"})

    assert response.status_code == 200
    assert _CATEGORIES.validate_json(response.content).items == []


def test_totals_group_on_the_deepest_selected_node(tmp_path: Path) -> None:
    """The partition claim end to end, through the real WHERE clause: Alice's subtree
    sums to 500 under her own node, Settlement keeps Bob's 400, and the two add up to
    the 900 the same request returns when it is not grouped at all."""
    _load_a_tree(tmp_path)

    with TestClient(create_app()) as client:
        grouped = client.get(
            "/api/expenses/totals",
            params=[
                ("period", "month"),
                ("group_by", "category"),
                ("category", "Settlement"),
                ("category", "Settlement:Alice"),
            ],
        )
        ungrouped = client.get(
            "/api/expenses/totals",
            params=[
                ("period", "month"),
                ("category", "Settlement"),
                ("category", "Settlement:Alice"),
            ],
        )

    rows = _TOTALS.validate_json(grouped.content).items
    assert [(row.amount, row.category) for row in rows] == [
        ("400.00", "Settlement"),
        ("500.00", "Settlement:Alice"),
    ]
    assert [row.amount for row in _TOTALS.validate_json(ungrouped.content).items] == [
        "900.00"
    ]


def test_totals_group_the_loaded_expenses_by_month(tmp_path: Path) -> None:
    """The whole path against real rows: three January expenses become one total.

    No new SQL is involved - list_expenses reads the same rows the list endpoint does
    and the summing happens after - so this confirms the path rather than a clause.
    """
    _load_four_days(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/expenses/totals", params={"period": "month", "group_by": "category"}
        )

    assert response.status_code == 200
    assert _TOTALS.validate_json(response.content).items == [
        # 100.00 + 200.00 + 300.00, the three rows on either side of mid-January.
        PeriodTotalPayload(
            period="2026-01",
            from_date="2026-01-01",
            to_date="2026-01-31",
            amount="600.00",
            currency="DKK",
            category="Car",
        ),
        PeriodTotalPayload(
            period="2026-02",
            from_date="2026-02-01",
            to_date="2026-02-28",
            amount="400.00",
            currency="DKK",
            category="Car",
        ),
    ]


def test_a_date_range_narrows_what_the_totals_are_taken_over(tmp_path: Path) -> None:
    """The range is applied in SQL, so the row outside it is not in the sum at all."""
    _load_four_days(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/expenses/totals",
            params={
                "period": "month",
                "group_by": "category",
                "from_date": "2026-01-02",
                "to_date": "2026-01-31",
            },
        )

    # 100.00 on 01/01 is outside the range, so January totals 500.00 and February,
    # having no rows left, is not a period at all. The span states the range asked
    # for rather than the whole month, because both bounds fall inside January.
    assert _TOTALS.validate_json(response.content).items == [
        PeriodTotalPayload(
            period="2026-01",
            from_date="2026-01-02",
            to_date="2026-01-31",
            amount="500.00",
            currency="DKK",
            category="Car",
        )
    ]


def test_a_range_the_expenses_fall_outside_totals_to_an_empty_list(
    tmp_path: Path,
) -> None:
    """No rows in range is no extent, so there is no calendar of empty periods."""
    _load_four_days(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/expenses/totals",
            params={
                "period": "month",
                "from_date": "2026-06-01",
                "to_date": "2026-06-30",
            },
        )

    assert response.status_code == 200
    assert _TOTALS.validate_json(response.content).items == []


def test_main_prints_a_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _write(tmp_path, "01.yaml", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    monkeypatch.setattr(sys, "argv", ["loader", str(tmp_path)])

    assert main() == 0
    assert capsys.readouterr().out.strip() == "1 files read, 0 skipped, 1 rows inserted"


def test_main_reports_a_bad_file_without_a_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A data problem is not a crash: exit 1 and the message the parser wrote."""
    _ = (tmp_path / "01.yaml").write_text(
        _month_file("1.00\tDKK\t02/01/2026\tCar\tFuel").replace(
            "'2026-01-02T00:00:00+01:00'", "'noon'"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["loader", str(tmp_path)])

    assert main() == 1
    assert "RFC 3339" in capsys.readouterr().err


def test_a_refund_nets_its_purchase_out_over_the_real_database(tmp_path: Path) -> None:
    """A purchase and its full refund through the loader, the table and the route.

    Transport nets to 0.00 and stays a row; Housing is untouched beside it. The
    amount arrives as a string with its cents intact, out of numeric(12, 2).
    """
    _ = _write(
        tmp_path,
        "01.yaml",
        "1250.00\tDKK\t01/12/2026\tHousing\tRent",
        "430.00\tDKK\t22/12/2026\tTransport\tTrain ticket",
        "-430.00\tDKK\t29/12/2026\tTransport\tRefund / Train ticket",
    )
    _ = asyncio.run(load_directory(tmp_path, database_url()))

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/expenses/totals",
            params={"period": "month", "group_by": "category"},
        )

    assert response.status_code == 200
    assert _TOTALS.validate_json(response.content).items == [
        PeriodTotalPayload(
            period="2026-12",
            from_date="2026-12-01",
            to_date="2026-12-31",
            amount="1250.00",
            currency="DKK",
            category="Housing",
        ),
        PeriodTotalPayload(
            period="2026-12",
            from_date="2026-12-01",
            to_date="2026-12-31",
            amount="0.00",
            currency="DKK",
            category="Transport",
        ),
    ]


def test_a_negative_amount_survives_the_round_trip(tmp_path: Path) -> None:
    """numeric(12, 2) keeps the sign, and the route sends it as it was stored."""
    _ = _write(tmp_path, "01.yaml", "-450.00\tDKK\t28/01/2026\tInsurance\tRefund")
    _ = asyncio.run(load_directory(tmp_path, database_url()))

    assert [row[0] for row in asyncio.run(_expenses())] == [Decimal("-450.00")]

    with TestClient(create_app()) as client:
        response = client.get("/api/expenses")

    assert [row.amount for row in _EXPENSES.validate_json(response.content).items] == [
        "-450.00"
    ]


def test_the_database_refuses_a_zero_amount() -> None:
    """expense_amount_not_zero, reached past the loader that refuses it first.

    The loader is what a data file meets; this is the backstop schema.sql promises,
    and the only thing that exercises it.
    """
    # Built outside the block, the way the two refusal tests above build theirs, so
    # the only call that can raise inside it is the one being tested.
    pending = _insert_expense(Decimal("0.00"))
    with pytest.raises(SQLAlchemyError, match="expense_amount_not_zero"):
        asyncio.run(pending)


@pytest.mark.parametrize("category", [":", "Food:", ":Food", "Food::Drink"])
def test_the_database_refuses_a_category_that_is_not_a_path(category: str) -> None:
    """expense_category_is_a_path, reached past the loader that refuses it first - the
    backstop schema.sql promises, and the only thing that exercises it."""
    pending = _insert_expense(Decimal("1.00"), category)
    with pytest.raises(SQLAlchemyError, match="expense_category_is_a_path"):
        asyncio.run(pending)


def test_a_path_of_several_levels_passes_the_same_constraint() -> None:
    """The negative control: depth is what the column is for, so the refusals above
    refuse for the reason they name rather than because any colon is unwelcome."""
    asyncio.run(_insert_expense(Decimal("1.00"), "Settlement:Alice:Spain"))

    assert [row[3] for row in asyncio.run(_expenses())] == ["Settlement:Alice:Spain"]


def test_a_nonzero_amount_passes_the_same_constraint() -> None:
    """The negative control: the helper inserts fine, so the test above refuses for
    the reason it names rather than because the insert was malformed."""
    asyncio.run(_insert_expense(Decimal("-450.00")))

    assert [row[0] for row in asyncio.run(_expenses())] == [Decimal("-450.00")]
