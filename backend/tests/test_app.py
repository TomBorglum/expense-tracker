from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import make_url
from starlette.testclient import TestClient

from expense_tracker import ExpensePayload, config, create_app
from expense_tracker.expense_repository import ExpenseRecord

# The origin a browser would send. Any value works against a wildcard policy.
_ORIGIN = "http://localhost:5173"

# Parses a response body into typed models instead of casting it to dicts. Reads
# response.content, which is bytes, so Response.json()'s Any never enters the picture.
_EXPENSES = TypeAdapter(list[ExpensePayload])


def test_greeting_endpoint_returns_json(client: TestClient, greeting_text: str) -> None:
    response = client.get("/api/greeting")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"greeting": greeting_text}
    # The wording is a row somebody can UPDATE, so a cached copy would outlive it.
    assert response.headers["Cache-Control"] == "no-store"


def test_security_headers_present(client: TestClient) -> None:
    response = client.get("/api/greeting")
    csp = response.headers["Content-Security-Policy"]
    # The API serves no document, so the policy grants nothing at all.
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_cors_allows_any_origin(client: TestClient) -> None:
    # Every real call is cross-origin, so this header is what makes the response
    # readable to the frontend.
    response = client.get("/api/greeting", headers={"Origin": _ORIGIN})
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"


def test_cors_preflight_is_answered(client: TestClient) -> None:
    # Answered by the CORS middleware itself; the router has no OPTIONS route.
    response = client.options(
        "/api/greeting",
        headers={"Origin": _ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert "GET" in response.headers["Access-Control-Allow-Methods"]


def test_cors_does_not_allow_credentials(client: TestClient) -> None:
    # The spec forbids credentials alongside a wildcard origin, and browsers reject the
    # pair silently.
    response = client.get("/api/greeting", headers={"Origin": _ORIGIN})
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_root_is_not_served(client: TestClient) -> None:
    assert client.get("/").status_code == 404


def test_static_files_are_not_served(client: TestClient) -> None:
    # The frontend owns its own build output; nothing from it ships in the wheel.
    assert client.get("/static/assets/index.js").status_code == 404


def test_unknown_api_routes_404(client: TestClient) -> None:
    # /api is two routes, not a namespace to grow into by accident.
    assert client.get("/api/hello").status_code == 404


def test_openapi_docs_are_disabled(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_greeting_is_unavailable_when_the_database_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Port 1 refuses instantly. Context-managed on purpose: that is what runs the
    # lifespan and builds the engine.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nobody@127.0.0.1:1/none")
    with TestClient(create_app()) as client:
        response = client.get("/api/greeting")
    assert response.status_code == 503
    assert response.json() == {"detail": "greeting unavailable"}
    # An error response is still decorated by the security-headers middleware.
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_expenses_endpoint_returns_json(
    client: TestClient, expense_records: list[ExpenseRecord]
) -> None:
    response = client.get("/api/expenses")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["Cache-Control"] == "no-store"
    assert _EXPENSES.validate_json(response.content) == [
        ExpensePayload(
            amount="1250.00",
            currency="DKK",
            date="2026-02-02",
            category="Housing",
            details="Rent",
        ),
        ExpensePayload(
            amount="775.37",
            currency="DKK",
            date="2026-01-02",
            category="Insurance",
            details="Accident / Car",
        ),
    ]
    # The fixture is the other half of that literal; if it changes, this should fail
    # rather than quietly assert against itself.
    assert len(expense_records) == 2


def test_expense_amounts_are_strings_not_numbers(client: TestClient) -> None:
    """1250.00 must not arrive as 1250.0.

    ExpensePayload types amount as str, so a route that emitted a JSON number fails to
    parse here rather than passing with a drifted value.
    """
    body = _EXPENSES.validate_json(client.get("/api/expenses").content)
    assert [row.amount for row in body] == ["1250.00", "775.37"]


def test_expenses_endpoint_preserves_the_repository_order(client: TestClient) -> None:
    """Ordering belongs to the repository, not the route. The fake hands back what it
    was given, so this fails if the route ever sorts on its own."""
    body = _EXPENSES.validate_json(client.get("/api/expenses").content)
    assert [row.date for row in body] == ["2026-02-02", "2026-01-02"]


def test_expenses_endpoint_returns_an_empty_list_when_nothing_is_loaded(
    empty_expenses_client: TestClient,
) -> None:
    """200 and [], deliberately not 503.

    A greeting's missing row is a fault, because exactly one row is required. An empty
    expense table is a database nobody has run the loader against, which is a
    legitimate state.
    """
    response = empty_expenses_client.get("/api/expenses")
    assert response.status_code == 200
    assert _EXPENSES.validate_json(response.content) == []


def test_expenses_are_unavailable_when_the_database_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real dependency this time, not the fake, against a port that refuses
    # instantly.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nobody@127.0.0.1:1/none")
    with TestClient(create_app()) as client:
        response = client.get("/api/expenses")
    assert response.status_code == 503
    assert response.json() == {"detail": "expenses unavailable"}
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def _detached_settings(**overrides: str) -> config.DatabaseSettings:
    """Settings built from `overrides` alone - no dotenv layer, so the committed
    backend/.env cannot answer for any of them."""
    return config.DatabaseSettings.load(None, **overrides)


def test_the_dsn_is_composed_from_the_connection_settings() -> None:
    settings = _detached_settings(
        pguser="someone", pghost="10.0.0.1", pgport="6000", pgdatabase="somewhere"
    )
    assert settings.dsn.render_as_string() == (
        "postgresql+asyncpg://someone@10.0.0.1:6000/somewhere"
    )


def test_dsn_parts_needing_escaping_are_encoded_not_interpolated() -> None:
    """A username carrying @ is escaped rather than emitted raw.

    Interpolating it would put a second @ in the authority and produce a URL that parses
    as a different host, so the round-trip is the assertion that matters.
    """
    settings = _detached_settings(
        pguser="user@corp", pghost="10.0.0.1", pgport="6000", pgdatabase="somewhere"
    )
    rendered = settings.dsn.render_as_string()
    assert "user%40corp" in rendered
    assert make_url(rendered).username == "user@corp"
    assert make_url(rendered).host == "10.0.0.1"


def test_a_password_is_redacted_when_the_dsn_is_rendered() -> None:
    """What stops a deployment's credential reaching a log or a traceback."""
    settings = _detached_settings(
        database_url="postgresql+asyncpg://someone:s3cret@10.0.0.1:6000/somewhere"
    )
    assert "s3cret" not in str(settings.dsn)
    assert "s3cret" not in repr(settings.dsn)
    assert settings.dsn.password == "s3cret"


def test_database_url_overrides_the_connection_settings() -> None:
    """Whole-DSN override, not a default: what a deployment is handed wins over the
    parts, which is why this still passes one of them."""
    settings = _detached_settings(
        database_url="postgresql+asyncpg://nobody@127.0.0.1:1/none", pgport="6000"
    )
    assert (
        settings.dsn.render_as_string()
        == "postgresql+asyncpg://nobody@127.0.0.1:1/none"
    )


def test_a_non_numeric_port_is_refused() -> None:
    with pytest.raises(ValidationError):
        _ = _detached_settings(
            pguser="someone",
            pghost="10.0.0.1",
            pgport="not-a-port",
            pgdatabase="somewhere",
        )


def test_missing_database_settings_are_refused_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No silent default: a deployment that forgets the settings fails to boot rather
    # than dialling its own loopback. Pointing _BACKEND_DIR at nothing is what the prod
    # environment's non-editable install does for real - no source tree in
    # site-packages means no backend/.env to answer with.
    monkeypatch.setattr(config, "_BACKEND_DIR", Path("/nonexistent"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for name in ("PGUSER", "PGHOST", "PGPORT", "PGDATABASE"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValidationError, match="PGUSER"), TestClient(create_app()):
        pass
