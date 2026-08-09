from typing import cast

import pytest
from starlette.testclient import TestClient

from expense_tracker import create_app
from expense_tracker.db import ExpenseRecord

# The origin a browser would send. Any value works against a wildcard policy; a
# realistic one keeps the assertions readable.
_ORIGIN = "http://localhost:5173"


def test_greeting_endpoint_returns_json(client: TestClient, greeting_text: str) -> None:
    # The wording comes from the greeting dependency now, so the body is asserted
    # against what the fake returned rather than a second copy of it. What the real
    # dependency reads out of PostgreSQL is test_greeting_postgres.py's business.
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
    # The frontend is a separate app on its own origin, so every real call is
    # cross-origin and this header is what makes the response readable to it.
    response = client.get("/api/greeting", headers={"Origin": _ORIGIN})
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"


def test_cors_preflight_is_answered(client: TestClient) -> None:
    # Answered by the CORS middleware itself rather than the router, which has no
    # OPTIONS route -- the reason it is registered last and so sits outermost.
    response = client.options(
        "/api/greeting",
        headers={"Origin": _ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert "GET" in response.headers["Access-Control-Allow-Methods"]


def test_cors_does_not_allow_credentials(client: TestClient) -> None:
    # The spec forbids credentials alongside a wildcard origin. Pinned because the
    # combination is easy to add by habit and browsers reject it silently.
    response = client.get("/api/greeting", headers={"Origin": _ORIGIN})
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_root_is_not_served(client: TestClient) -> None:
    # This backend is a REST API: no route here returns HTML.
    assert client.get("/").status_code == 404


def test_static_files_are_not_served(client: TestClient) -> None:
    # The frontend owns its own build output, so there is no StaticFiles mount and
    # nothing from the bundle ships inside the wheel.
    assert client.get("/static/assets/index.js").status_code == 404


def test_unknown_api_routes_404(client: TestClient) -> None:
    # /api is one route, not a namespace to grow into by accident.
    assert client.get("/api/hello").status_code == 404


def test_openapi_docs_are_disabled(client: TestClient) -> None:
    # FastAPI publishes an OpenAPI schema and two docs UIs by default. One hand-written
    # route does not earn them, so create_app() turns them off and they must stay off.
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_greeting_is_unavailable_when_the_database_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Port 1 refuses instantly, so this exercises the real dependency against a real
    # unreachable server without needing one. Entered as a context manager on purpose:
    # that is what runs the lifespan and builds the engine, and it is the only test
    # here that does.
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
    assert response.json() == [
        {
            "amount": "1250.00",
            "currency": "DKK",
            "date": "2026-02-02",
            "category": "Housing",
            "details": "Rent",
        },
        {
            "amount": "775.37",
            "currency": "DKK",
            "date": "2026-01-02",
            "category": "Insurance",
            "details": "Accident / Car",
        },
    ]
    # The fixture is the other half of that literal; if it changes, this should fail
    # rather than quietly assert against itself.
    assert len(expense_records) == 2


def test_expense_amounts_are_strings_not_numbers(client: TestClient) -> None:
    """The property a float() would break. 1250.00 must not arrive as 1250.0.

    JSON has no decimal type and 775.37 has no exact binary form, so a float round trip
    is how a total drifts by a cent. The client parses the string.
    """
    # cast because Response.json() is Any, which recommended mode's reportAny rejects
    # the moment it is bound to a name - the same reason deps.provide_session casts.
    body = cast("list[dict[str, str]]", client.get("/api/expenses").json())
    assert [row["amount"] for row in body] == ["1250.00", "775.37"]


def test_expenses_endpoint_preserves_the_repository_order(client: TestClient) -> None:
    """Ordering belongs to the repository and its index, not to the route.

    The fake hands back what it was given, so this fails if the route ever sorts or
    reverses on its own.
    """
    body = cast("list[dict[str, str]]", client.get("/api/expenses").json())
    assert [row["date"] for row in body] == ["2026-02-02", "2026-01-02"]


def test_expenses_endpoint_returns_an_empty_list_when_nothing_is_loaded(
    empty_expenses_client: TestClient,
) -> None:
    """200 and [], deliberately not 503 - the asymmetry with the greeting.

    A greeting's missing row is a fault, because exactly one row is required. An empty
    expense table is a freshly initialised database nobody has run the loader against,
    which is a legitimate state; answering 503 would train a client to retry forever
    against a server that is working perfectly.
    """
    response = empty_expenses_client.get("/api/expenses")
    assert response.status_code == 200
    assert response.json() == []


def test_expenses_are_unavailable_when_the_database_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real dependency this time, not the fake, against a port that refuses
    # instantly. Context-managed so the lifespan runs and an engine is actually built.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nobody@127.0.0.1:1/none")
    with TestClient(create_app()) as client:
        response = client.get("/api/expenses")
    assert response.status_code == 503
    assert response.json() == {"detail": "expenses unavailable"}
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_missing_database_url_is_refused_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No silent default: a deployment that forgets the setting fails to boot rather
    # than quietly dialling its own loopback.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"), TestClient(create_app()):
        pass
