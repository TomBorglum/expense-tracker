"""The currency loader and the currencies endpoint against a real PostgreSQL server.

Every test here TRUNCATEs currency_rate, before and after. That wipes whatever
`pixi run backend-load-currencies` put in a developer's database - run it again
afterwards. Doing it before as well as after stops a killed run poisoning the next one.
"""

import asyncio
import os
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import TypeAdapter
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.testclient import TestClient

from expense_tracker import CurrencyPayload, create_app
from expense_tracker.config import database_url
from expense_tracker.currency_loader import CurrencyFileError, load_directory, main
from expense_tracker.currency_repository import CurrencyRate

# Registered in pyproject.toml, which --strict-markers requires.
pytestmark = pytest.mark.postgres

_DATA = Path(__file__).resolve().parents[1] / "data" / "currencies"

_HEADER = "FROM_CURRENCY\tTO_CURRENCY\tEXCHANGE_RATE\n"

_CURRENCIES = TypeAdapter(list[CurrencyPayload])


async def _truncate() -> None:
    """RESTART IDENTITY keeps ids predictable across tests. currency_rate references
    nothing and nothing references it, so it truncates alone."""
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            _ = await session.execute(text("TRUNCATE currency_rate RESTART IDENTITY"))
            await session.commit()
    finally:
        await engine.dispose()


async def _rates() -> list[tuple[str, str, Decimal]]:
    """Every rate as plain tuples, by pair.

    Mapped instances rather than a Row, so the columns keep the model's types;
    flattened inside the session, because the instances detach when it closes.
    """
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            rows = await session.scalars(
                select(CurrencyRate).order_by(
                    CurrencyRate.from_currency,
                    CurrencyRate.to_currency,
                    CurrencyRate.id,
                )
            )
            return [(r.from_currency, r.to_currency, r.exchange_rate) for r in rows]
    finally:
        await engine.dispose()


@pytest.fixture(scope="module", autouse=True)
def require_postgres() -> None:
    """Skip locally when no server answers; fail under CI, so a database that did not
    come up cannot go green."""
    try:
        _ = asyncio.run(_rates())
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
    _ = _write(tmp_path, "01.tsv", "DKK\tEUR\t0.134048")
    _ = _write(tmp_path, "02.tsv", "DKK\tUSD\t0.145200", "EUR\tDKK\t7.460000")

    summary = asyncio.run(load_directory(tmp_path, database_url()))

    assert summary == (2, 0, 3)
    assert asyncio.run(_rates()) == [
        ("DKK", "EUR", Decimal("0.134048")),
        ("DKK", "USD", Decimal("0.145200")),
        ("EUR", "DKK", Decimal("7.460000")),
    ]


def test_an_edited_rate_replaces_the_old_one(tmp_path: Path) -> None:
    """The property this loader exists for, and the one the expense loader refuses:
    rates change, so the file is a snapshot and reloading it is the workflow."""
    path = _write(tmp_path, "rates.tsv", "DKK\tEUR\t0.134048")
    first = asyncio.run(load_directory(tmp_path, database_url()))
    _ = path.write_text(_HEADER + "DKK\tEUR\t0.135000\n", encoding="utf-8")

    second = asyncio.run(load_directory(tmp_path, database_url()))

    assert first == (1, 0, 1)
    assert second == (1, 1, 1)
    # Replaced, not doubled.
    assert asyncio.run(_rates()) == [("DKK", "EUR", Decimal("0.135000"))]


def test_a_pair_dropped_from_the_file_is_dropped_from_the_table(tmp_path: Path) -> None:
    _ = _write(tmp_path, "rates.tsv", "DKK\tEUR\t0.134048", "DKK\tUSD\t0.145200")
    _ = asyncio.run(load_directory(tmp_path, database_url()))
    _ = _write(tmp_path, "rates.tsv", "DKK\tEUR\t0.134048")

    _ = asyncio.run(load_directory(tmp_path, database_url()))

    assert [(f, t) for f, t, _rate in asyncio.run(_rates())] == [("DKK", "EUR")]


def test_a_bad_file_leaves_the_loaded_rates_intact(tmp_path: Path) -> None:
    """Parsing happens before the delete, so a typo cannot empty the table."""
    _ = _write(tmp_path, "01.tsv", "DKK\tEUR\t0.134048")
    _ = asyncio.run(load_directory(tmp_path, database_url()))
    _ = _write(tmp_path, "02.tsv", "DKK\tUSD\t0,145200")

    pending = load_directory(tmp_path, database_url())
    with pytest.raises(CurrencyFileError, match="exchange rate"):
        _ = asyncio.run(pending)

    assert asyncio.run(_rates()) == [("DKK", "EUR", Decimal("0.134048"))]


def test_a_row_the_database_refuses_takes_the_delete_with_it(tmp_path: Path) -> None:
    """Delete and insert share one transaction. The rate passes the parser - the regex
    constrains decimal places, not magnitude - and overflows numeric(18, 6)."""
    _ = _write(tmp_path, "01.tsv", "DKK\tEUR\t0.134048")
    _ = asyncio.run(load_directory(tmp_path, database_url()))
    _ = _write(tmp_path, "01.tsv", "DKK\tEUR\t1234567890123.456789")

    pending = load_directory(tmp_path, database_url())
    with pytest.raises(SQLAlchemyError):
        _ = asyncio.run(pending)

    assert asyncio.run(_rates()) == [("DKK", "EUR", Decimal("0.134048"))]


def test_the_committed_sample_files_load(tmp_path: Path) -> None:
    """Puts backend/data/currencies/ through the real database path inside
    `backend-test`. tmp_path is unused but keeps the signature uniform."""
    assert tmp_path.is_dir()
    summary = asyncio.run(load_directory(_DATA, database_url()))

    assert summary.files_read == len(sorted(_DATA.glob("*.tsv")))
    assert summary.rows_deleted == 0
    assert summary.rows_inserted == len(asyncio.run(_rates()))


def test_the_endpoint_returns_the_rows_by_pair(tmp_path: Path) -> None:
    _ = _write(tmp_path, "rates.tsv", "EUR\tDKK\t7.460000", "DKK\tEUR\t0.134048")
    _ = asyncio.run(load_directory(tmp_path, database_url()))

    # Context-managed, so the lifespan builds a real engine against the real database.
    with TestClient(create_app()) as client:
        response = client.get("/api/currencies")

    assert response.status_code == 200
    body = _CURRENCIES.validate_json(response.content)
    assert [(row.from_currency, row.to_currency) for row in body] == [
        ("DKK", "EUR"),
        ("EUR", "DKK"),
    ]
    # Decimal out of numeric, string into JSON, trailing zeros intact.
    assert [row.exchange_rate for row in body] == ["0.134048", "7.460000"]


def test_the_endpoint_returns_an_empty_list_when_nothing_is_loaded() -> None:
    """The empty table answering 200, against a real one rather than a fake."""
    with TestClient(create_app()) as client:
        response = client.get("/api/currencies")

    assert response.status_code == 200
    assert _CURRENCIES.validate_json(response.content) == []


def test_main_prints_a_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _write(tmp_path, "rates.tsv", "DKK\tEUR\t0.134048")
    monkeypatch.setattr(sys, "argv", ["loader", str(tmp_path)])

    assert main() == 0
    out = capsys.readouterr().out.strip()
    assert out == "1 files read, 0 rows deleted, 1 rows inserted"


def test_main_reports_a_bad_file_without_a_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A data problem is not a crash: exit 1 and the message the parser wrote."""
    _ = _write(tmp_path, "rates.tsv", "DKK\tEUR\t0.1340485")
    monkeypatch.setattr(sys, "argv", ["loader", str(tmp_path)])

    assert main() == 1
    assert "six decimal places" in capsys.readouterr().err
