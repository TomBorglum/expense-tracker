import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import override

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from expense_tracker import create_app
from expense_tracker.currency_repository import CurrencyRateRecord, CurrencyRepository
from expense_tracker.deps import provide_currency_repository, provide_expense_repository
from expense_tracker.expense_repository import ExpenseRecord, ExpenseRepository


class _FakeExpenseRepository(ExpenseRepository):
    """Stands in for the real repository without a session or a server."""

    # Annotated at class level for reportUnannotatedClassAttribute.
    _records: Sequence[ExpenseRecord]
    _bounds: list[tuple[datetime.date | None, datetime.date | None]]

    def __init__(
        self,
        records: Sequence[ExpenseRecord],
        bounds: list[tuple[datetime.date | None, datetime.date | None]],
    ) -> None:
        self._records = records
        self._bounds = bounds

    @override
    async def list_expenses(
        self,
        from_date: datetime.date | None = None,
        to_date: datetime.date | None = None,
    ) -> Sequence[ExpenseRecord]:
        # The bounds are recorded rather than applied, and the records are handed back
        # in the order they were given. Filtering and ordering are both the
        # repository's job, so a fake that did either would hide a route that did it
        # again.
        self._bounds.append((from_date, to_date))
        return self._records


class _FakeCurrencyRepository(CurrencyRepository):
    """Stands in for the real repository without a session or a server."""

    # Annotated at class level for reportUnannotatedClassAttribute.
    _records: Sequence[CurrencyRateRecord]

    def __init__(self, records: Sequence[CurrencyRateRecord]) -> None:
        self._records = records

    @override
    async def list_currencies(self) -> Sequence[CurrencyRateRecord]:
        # Handed back in the order it was given, for the reason above.
        return self._records


@pytest.fixture
def expense_records() -> list[ExpenseRecord]:
    """Two expenses, already newest first.

    One amount has a trailing zero, so a route reaching for float() instead of str()
    shows up as 1250.0 rather than 1250.00.
    """
    return [
        ExpenseRecord(
            Decimal("1250.00"), "DKK", datetime.date(2026, 2, 2), "Housing", "Rent"
        ),
        ExpenseRecord(
            Decimal("775.37"),
            "DKK",
            datetime.date(2026, 1, 2),
            "Insurance",
            "Accident / Car",
        ),
    ]


@pytest.fixture
def currency_records() -> list[CurrencyRateRecord]:
    """Two rates, in the pair order the repository sorts by.

    One rate carries trailing zeros, so a route reaching for float() instead of str()
    shows up as 7.46 rather than 7.460000.
    """
    return [
        CurrencyRateRecord("DKK", "EUR", Decimal("0.134048")),
        CurrencyRateRecord("EUR", "DKK", Decimal("7.460000")),
    ]


@pytest.fixture
def requested_bounds() -> list[tuple[datetime.date | None, datetime.date | None]]:
    """Every (from_date, to_date) the route hands the expense repository, in order.

    A list rather than an attribute on the fake, so a test reads what the route asked
    for without reaching into a private class.
    """
    return []


@pytest.fixture
def app(
    expense_records: list[ExpenseRecord],
    currency_records: list[CurrencyRateRecord],
    requested_bounds: list[tuple[datetime.date | None, datetime.date | None]],
) -> FastAPI:
    """An app whose data comes from memory instead of PostgreSQL.

    provide_session is upstream of both overrides, so it never runs and no session is
    ever opened.
    """
    application = create_app()
    application.dependency_overrides[provide_expense_repository] = lambda: (
        _FakeExpenseRepository(expense_records, requested_bounds)
    )
    application.dependency_overrides[provide_currency_repository] = lambda: (
        _FakeCurrencyRepository(currency_records)
    )
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # Not entered as a context manager: `with TestClient(...)` runs the lifespan, which
    # would build a real engine from DATABASE_URL.
    return TestClient(app)


@pytest.fixture
def empty_expenses_client(app: FastAPI) -> TestClient:
    """The same app with nothing loaded yet, which is a state and not a fault."""
    # Re-overriding on the app fixture rather than parametrising it indirectly:
    # request.param is an Any expression, which reportAny rejects.
    app.dependency_overrides[provide_expense_repository] = lambda: (
        _FakeExpenseRepository([], [])
    )
    return TestClient(app)


@pytest.fixture
def empty_currencies_client(app: FastAPI) -> TestClient:
    """The rates half of the same asymmetry: nothing loaded is still a 200."""
    app.dependency_overrides[provide_currency_repository] = lambda: (
        _FakeCurrencyRepository([])
    )
    return TestClient(app)
