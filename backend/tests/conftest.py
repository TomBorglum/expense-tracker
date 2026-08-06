from typing import override

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from expense_tracker import create_app
from expense_tracker.db import GreetingRepository
from expense_tracker.deps import provide_greeting_repository


class _FakeGreetingRepository(GreetingRepository):
    """Stands in for the real repository without a session or a server.

    Subclasses the contract explicitly, like PostgresGreetingRepository does, so this
    line is what tells a reader the two are coupled and the type checker what to hold
    them to. Renaming or dropping the method below fails the build.
    """

    # Annotated at class level for the same reason PostgresGreetingRepository._session
    # is:
    # reportUnannotatedClassAttribute wants every attribute of a non-final class typed.
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


@pytest.fixture
def app(greeting_text: str) -> FastAPI:
    """An app whose greeting comes from memory instead of PostgreSQL.

    Overriding the dependency, rather than pointing the app at a test database, is what
    keeps this suite about the HTTP surface - CORS, security headers, 404s - and
    runnable with no server anywhere. provide_session is upstream of the override, so
    it never runs and no session is ever opened.
    """
    application = create_app()
    application.dependency_overrides[provide_greeting_repository] = lambda: (
        _FakeGreetingRepository(greeting_text)
    )
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # Deliberately not entered as a context manager: `with TestClient(...)` runs the
    # lifespan, which would build a real engine from DATABASE_URL. These tests want the
    # router and the middleware stack, not a database.
    return TestClient(app)
