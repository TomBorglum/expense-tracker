"""Tests for the Flask dashboard route."""

from collections.abc import Iterator

import pytest
from flask.testing import FlaskClient

from expense_tracker import config, loader, server


@pytest.fixture
def client(data_dir, tmp_path, monkeypatch) -> Iterator[FlaskClient]:
    db_path = tmp_path / "server.sqlite"
    loader.build(data_dir=data_dir, db_path=db_path)
    # Point the app's default connection at the temporary database.
    monkeypatch.setattr(config, "DB_PATH", db_path)
    app = server.create_app()
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def test_dashboard_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Expense Tracker" in body
    assert "Groceries" in body
    # Grand total of the sample data (54.20 + 12.00 + 48.30 + 15.00).
    assert "129.50" in body


def test_dashboard_filter_by_category(client):
    resp = client.get("/?category=Groceries")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Filtered total for Groceries (54.20 + 48.30).
    assert "102.50" in body
