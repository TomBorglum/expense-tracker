from starlette.testclient import TestClient

from expense_tracker import GREETING, create_app

# The origin a browser would send. Any value works against a wildcard policy; a
# realistic one keeps the assertions readable.
_ORIGIN = "http://localhost:5173"


def test_greeting_endpoint_returns_json() -> None:
    # The hand-built payload. greeting.json stays the single source of truth, so the
    # body is asserted against GREETING rather than a literal.
    response = TestClient(create_app()).get("/api/greeting")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"greeting": GREETING}
    # The wording ships inside the wheel, so a cached copy would outlive its deploy.
    assert response.headers["Cache-Control"] == "no-store"


def test_security_headers_present() -> None:
    response = TestClient(create_app()).get("/api/greeting")
    csp = response.headers["Content-Security-Policy"]
    # The API serves no document, so the policy grants nothing at all.
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_cors_allows_any_origin() -> None:
    # The frontend is a separate app on its own origin, so every real call is
    # cross-origin and this header is what makes the response readable to it.
    client = TestClient(create_app())
    response = client.get("/api/greeting", headers={"Origin": _ORIGIN})
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"


def test_cors_preflight_is_answered() -> None:
    # Answered by the CORS middleware itself rather than the router, which has no
    # OPTIONS route -- the reason it is registered last and so sits outermost.
    response = TestClient(create_app()).options(
        "/api/greeting",
        headers={"Origin": _ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert "GET" in response.headers["Access-Control-Allow-Methods"]


def test_cors_does_not_allow_credentials() -> None:
    # The spec forbids credentials alongside a wildcard origin. Pinned because the
    # combination is easy to add by habit and browsers reject it silently.
    client = TestClient(create_app())
    response = client.get("/api/greeting", headers={"Origin": _ORIGIN})
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_root_is_not_served() -> None:
    # This backend is a REST API. It served a page shell once; nothing here should
    # ever grow a route that returns HTML again.
    assert TestClient(create_app()).get("/").status_code == 404


def test_static_files_are_not_served() -> None:
    # The vite bundle used to be mounted here and shipped inside the wheel. The
    # frontend owns its own build output now, so there is no mount to hit.
    assert TestClient(create_app()).get("/static/assets/index.js").status_code == 404


def test_unknown_api_routes_404() -> None:
    # /api is one route, not a namespace to grow into by accident.
    assert TestClient(create_app()).get("/api/hello").status_code == 404


def test_openapi_docs_are_disabled() -> None:
    # FastAPI publishes an OpenAPI schema and two docs UIs by default. One hand-written
    # route does not earn them, so create_app() turns them off and they must stay off.
    client = TestClient(create_app())
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
