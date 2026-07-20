"""Smoke tests proving the application boots and serves its shell page."""

from flask import Flask
from flask.testing import FlaskClient


def test_app_factory_applies_test_config(app: Flask) -> None:
    assert app.testing


def test_index_renders(client: FlaskClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert b"Expense Tracker" in response.data
