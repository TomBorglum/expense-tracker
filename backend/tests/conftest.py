import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import override

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from expense_tracker import create_app
from expense_tracker.db import ExpenseRecord, ExpenseRepository, GreetingRepository
from expense_tracker.deps import provide_expense_repository, provide_greeting_repository


class _FakeGreetingRepository(GreetingRepository):
    """Stands in for the real repository without a session or a server.

    Subclassing GreetingRepository is required, not a courtesy: renaming or dropping the
    method below fails the build.
    """

    # Annotated at class level for the same reason PostgresGreetingRepository._session
    # is: reportUnannotatedClassAttribute wants every attribute of a non-final class
    # typed.
    _message: str

    def __init__(self, message: str) -> None:
        self._message = message

    @override
    async def get_current_greeting(self) -> str:
        return self._message


@pytest.fixture
def greeting_text() -> str:
    """The fake greeting the HTTP suite asserts against.

    Deliberately not the wording schema.sql seeds: if the endpoint ever went back to
    serving a constant, a matching value here would let these tests pass anyway.
    """
    return "Hello from the test double!"


class _FakeExpenseRepository(ExpenseRepository):
    """Stands in for the real repository without a session or a server.

    Subclassing ExpenseRepository is required for the same reason the greeting's fake
    subclasses its own: dependency_overrides is an untyped dict and would accept a
    look-alike, so the ABC is what makes the coupling real.
    """

    _records: Sequence[ExpenseRecord]

    def __init__(self, records: Sequence[ExpenseRecord]) -> None:
        self._records = records

    @override
    async def list_expenses(self) -> Sequence[ExpenseRecord]:
        # Handed back in the order it was given, deliberately unsorted. Ordering is the
        # repository's job, so a fake that sorted would hide a route that re-sorted.
        return self._records


@pytest.fixture
def expense_records() -> list[ExpenseRecord]:
    """Two expenses, already newest first, as the real repository would return them.

    The amounts have two decimal places and one of them has a trailing zero, so a route
    that reached for float() instead of str() shows up as 1250.0 rather than 1250.00.
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
def app(greeting_text: str, expense_records: list[ExpenseRecord]) -> FastAPI:
    """An app whose data comes from memory instead of PostgreSQL.

    Overriding the dependencies, rather than pointing the app at a test database, is
    what keeps this suite about the HTTP surface - CORS, security headers, 404s - and
    runnable with no server anywhere. provide_session is upstream of both overrides, so
    it never runs and no session is ever opened.
    """
    application = create_app()
    application.dependency_overrides[provide_greeting_repository] = lambda: (
        _FakeGreetingRepository(greeting_text)
    )
    application.dependency_overrides[provide_expense_repository] = lambda: (
        _FakeExpenseRepository(expense_records)
    )
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # Deliberately not entered as a context manager: `with TestClient(...)` runs the
    # lifespan, which would build a real engine from DATABASE_URL. These tests want the
    # router and the middleware stack, not a database.
    return TestClient(app)


@pytest.fixture
def empty_expenses_client(app: FastAPI) -> TestClient:
    """The same app with nothing loaded yet, which is a state and not a fault.

    Re-overriding the dependency on the app fixture rather than parametrising it
    indirectly: request.param is an Any expression, which recommended mode rejects.
    """
    app.dependency_overrides[provide_expense_repository] = lambda: (
        _FakeExpenseRepository([])
    )
    return TestClient(app)
