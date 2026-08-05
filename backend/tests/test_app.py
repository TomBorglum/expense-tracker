import pytest
from starlette.testclient import TestClient

from expense_tracker import create_app

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


def test_missing_database_url_is_refused_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No silent default: a deployment that forgets the setting fails to boot rather
    # than quietly dialling its own loopback.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"), TestClient(create_app()):
        pass
