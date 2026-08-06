import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from expense_tracker import create_app
from expense_tracker.db import provide_greeting


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
    runnable with no server anywhere.
    """
    application = create_app()
    application.dependency_overrides[provide_greeting] = lambda: greeting_text
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # Deliberately not entered as a context manager: `with TestClient(...)` runs the
    # lifespan, which would build a real engine from DATABASE_URL. These tests want the
    # router and the middleware stack, not a database.
    return TestClient(app)
