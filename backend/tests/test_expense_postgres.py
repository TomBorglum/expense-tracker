"""The loader and the expenses endpoint against a real PostgreSQL server.

The only expense module in the suite that connects; everything else runs against byte
literals or a fake repository. Skips when no server answers, and fails instead of
skipping under CI, so a database that did not come up cannot go green.

Every test here TRUNCATEs both tables, before and after. That wipes whatever
`pixi run backend-load-expenses` put in a developer's database - run it again
afterwards. Doing it before as well as after is what stops a killed run poisoning the
next one.
"""

import asyncio
import datetime
import os
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.testclient import TestClient

from expense_tracker import create_app
from expense_tracker.config import database_url
from expense_tracker.db import Expense, LoadedFile
from expense_tracker.loader import ExpenseFileError, load_directory, main

# Same reasoning as test_greeting_postgres.py: the marker is registered in
# pyproject.toml, which --strict-markers requires.
pytestmark = pytest.mark.postgres

_DATA = Path(__file__).resolve().parents[2] / "data" / "expenses"

_HEADER = "Amount\tCurrency\tDate\tCategory\tDetails\n"


async def _truncate() -> None:
    """Both tables in one statement: PostgreSQL refuses to truncate a referenced one
    alone, and RESTART IDENTITY keeps ids predictable across tests."""
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            _ = await session.execute(
                text("TRUNCATE expense, loaded_file RESTART IDENTITY")
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _expenses() -> list[tuple[Decimal, str, datetime.date, str, str]]:
    """Every expense as plain tuples, oldest first, read back through a fresh engine.

    Mapped instances rather than a Row, so the columns keep the model's types; flattened
    inside the session, because the instances detach when it closes.
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
    """The loaded_file rows as (filename, sha256, row_count), by filename."""
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            rows = await session.scalars(
                select(LoadedFile).order_by(LoadedFile.filename)
            )
            return [(r.filename, r.sha256, r.row_count) for r in rows]
    finally:
        await engine.dispose()


@pytest.fixture(scope="module", autouse=True)
def require_postgres() -> None:
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


def _write(directory: Path, name: str, *rows: str) -> Path:
    path = directory / name
    _ = path.write_text(_HEADER + "".join(row + "\n" for row in rows), encoding="utf-8")
    return path


def test_loading_a_directory_inserts_every_row(tmp_path: Path) -> None:
    _ = _write(tmp_path, "01.csv", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    _ = _write(
        tmp_path,
        "02.csv",
        "1250.00\tDKK\t02/02/2026\tHousing\tRent",
        "99.95\tDKK\t19/02/2026\tUtilities\tInternet",
    )

    summary = asyncio.run(load_directory(tmp_path, database_url()))

    assert summary == (2, 0, 3)
    assert len(asyncio.run(_expenses())) == 3
    assert [(name, count) for name, _sha, count in asyncio.run(_ledger())] == [
        ("01.csv", 1),
        ("02.csv", 2),
    ]


def test_identical_rows_in_one_file_both_survive(tmp_path: Path) -> None:
    """The property the whole design exists for.

    Two fuel stops of the same amount on the same day are two purchases. A content hash
    as the primary key would have collapsed them and made the month's total short.
    """
    row = "611.23\tDKK\t14/01/2026\tCar\tFuel"
    _ = _write(tmp_path, "01.csv", row, row)

    summary = asyncio.run(load_directory(tmp_path, database_url()))

    assert summary.rows_inserted == 2
    assert len(asyncio.run(_expenses())) == 2


def test_reloading_an_unchanged_directory_skips_every_file(tmp_path: Path) -> None:
    _ = _write(tmp_path, "01.csv", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    _ = _write(tmp_path, "02.csv", "1250.00\tDKK\t02/02/2026\tHousing\tRent")
    first = asyncio.run(load_directory(tmp_path, database_url()))

    second = asyncio.run(load_directory(tmp_path, database_url()))

    assert first == (2, 0, 2)
    assert second == (2, 2, 0)
    # The point of the ledger: a second run is a no-op, not a doubling.
    assert len(asyncio.run(_expenses())) == 2


def test_a_new_file_beside_a_loaded_one_is_still_loaded(tmp_path: Path) -> None:
    """Appending is the supported workflow, so it must not be caught by the skip."""
    _ = _write(tmp_path, "01.csv", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    _ = asyncio.run(load_directory(tmp_path, database_url()))
    _ = _write(tmp_path, "02.csv", "1250.00\tDKK\t02/02/2026\tHousing\tRent")

    summary = asyncio.run(load_directory(tmp_path, database_url()))

    assert summary == (2, 1, 1)
    assert len(asyncio.run(_expenses())) == 2


def test_an_edited_file_is_refused_by_name_and_load_date(tmp_path: Path) -> None:
    path = _write(tmp_path, "01.csv", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    _ = asyncio.run(load_directory(tmp_path, database_url()))
    # A typo fix, which is exactly the case that must not pass silently.
    _ = path.write_text(
        _HEADER + "775.38\tDKK\t02/01/2026\tInsurance\tCar\n", encoding="utf-8"
    )

    pending = load_directory(tmp_path, database_url())
    with pytest.raises(ExpenseFileError, match=r"01\.csv changed since it was loaded"):
        _ = asyncio.run(pending)

    # Neither skipped nor re-read: the database is exactly as it was.
    assert [amount for amount, *_rest in asyncio.run(_expenses())] == [
        Decimal("775.37")
    ]


def test_a_file_that_fails_midway_leaves_earlier_files_committed(
    tmp_path: Path,
) -> None:
    """Per-file atomicity, in both directions at once.

    01 commits and stays committed while 02 fails. 02's amount passes the parser - the
    regex constrains decimal places, not magnitude - and overflows numeric(12, 2) at
    the database, which is what makes this exercise a rollback rather than a parse
    error. Its ledger row is in the same transaction, so it goes too.
    """
    _ = _write(tmp_path, "01-good.csv", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    _ = _write(tmp_path, "02-bad.csv", "1234567890123.45\tDKK\t02/02/2026\tHousing\tR")

    pending = load_directory(tmp_path, database_url())
    with pytest.raises(SQLAlchemyError):
        _ = asyncio.run(pending)

    assert len(asyncio.run(_expenses())) == 1
    # 02-bad.csv left no ledger row, so re-running after fixing the file will retry it.
    assert [name for name, _sha, _count in asyncio.run(_ledger())] == ["01-good.csv"]


def test_the_committed_sample_files_load(tmp_path: Path) -> None:
    """Puts data/expenses/ through the real database path inside `backend-test`.

    tmp_path is unused on purpose - this one reads the committed directory - but the
    fixture keeps the signature uniform with its neighbours.
    """
    assert tmp_path.is_dir()
    summary = asyncio.run(load_directory(_DATA, database_url()))

    assert summary.files_read == len(sorted(_DATA.glob("*.csv")))
    assert summary.files_skipped == 0
    assert summary.rows_inserted == len(asyncio.run(_expenses()))


def test_the_endpoint_returns_the_rows_newest_first(tmp_path: Path) -> None:
    _ = _write(
        tmp_path,
        "01.csv",
        "775.37\tDKK\t02/01/2026\tInsurance\tCar",
        "1250.00\tDKK\t02/02/2026\tHousing\tRent",
    )
    _ = asyncio.run(load_directory(tmp_path, database_url()))

    # Context-managed, so the lifespan builds a real engine against the real database.
    with TestClient(create_app()) as client:
        response = client.get("/api/expenses")

    assert response.status_code == 200
    body = cast("list[dict[str, str]]", response.json())
    assert [row["date"] for row in body] == ["2026-02-02", "2026-01-02"]
    # Decimal out of numeric, string into JSON, trailing zero intact.
    assert [row["amount"] for row in body] == ["1250.00", "775.37"]


def test_the_endpoint_returns_an_empty_list_when_nothing_is_loaded() -> None:
    """The empty table answering 200, against a real one rather than a fake."""
    with TestClient(create_app()) as client:
        response = client.get("/api/expenses")

    assert response.status_code == 200
    assert response.json() == []


def test_main_prints_a_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _write(tmp_path, "01.csv", "775.37\tDKK\t02/01/2026\tInsurance\tCar")
    monkeypatch.setattr(sys, "argv", ["loader", str(tmp_path)])

    assert main() == 0
    assert capsys.readouterr().out.strip() == "1 files read, 0 skipped, 1 rows inserted"


def test_main_reports_a_bad_file_without_a_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A data problem is not a crash: exit 1 and the message the parser wrote."""
    _ = _write(tmp_path, "01.csv", "1.00\tDKK\t2026-01-02\tCar\tFuel")
    monkeypatch.setattr(sys, "argv", ["loader", str(tmp_path)])

    assert main() == 1
    assert "DD/MM/YYYY" in capsys.readouterr().err
