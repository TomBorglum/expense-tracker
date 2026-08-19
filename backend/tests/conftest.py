import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import override

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from expense_tracker import create_app
from expense_tracker.deps import provide_expense_repository
from expense_tracker.expense_repository import ExpenseRecord, ExpenseRepository


class _FakeExpenseRepository(ExpenseRepository):
    """Stands in for the real repository without a session or a server."""

    # Annotated at class level for reportUnannotatedClassAttribute.
    _records: Sequence[ExpenseRecord]

    def __init__(self, records: Sequence[ExpenseRecord]) -> None:
        self._records = records

    @override
    async def list_expenses(self) -> Sequence[ExpenseRecord]:
        # Handed back in the order it was given. Ordering is the repository's job, so
        # a fake that sorted would hide a route that re-sorted.
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
def app(expense_records: list[ExpenseRecord]) -> FastAPI:
    """An app whose data comes from memory instead of PostgreSQL.

    provide_session is upstream of the override, so it never runs and no session is
    ever opened.
    """
    application = create_app()
    application.dependency_overrides[provide_expense_repository] = lambda: (
        _FakeExpenseRepository(expense_records)
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
        _FakeExpenseRepository([])
    )
    return TestClient(app)
