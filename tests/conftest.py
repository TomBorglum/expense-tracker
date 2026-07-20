"""Shared pytest fixtures.

Every test gets its own application backed by a throwaway SQLite file, so the
instance folder is never touched by a test run.
"""

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from expense_tracker import create_app
from expense_tracker.db import init_db


@pytest.fixture
def app() -> Iterator[Flask]:
    """An application backed by a temporary, freshly initialized database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.sqlite"
        application = create_app({"TESTING": True, "DATABASE": str(db_path)})

        with application.app_context():
            init_db()

        yield application


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """A test client for the configured application."""
    return app.test_client()
