import re

from starlette.testclient import TestClient

from expense_tracker import GREETING, STATIC_DIR, create_app


def test_index_serves_built_page() -> None:
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    # vite emits the bundle as external files under the /static/ base.
    assert re.search(r'src="/static/assets/index-[^"]+\.js"', body)
    assert re.search(r'href="/static/assets/index-[^"]+\.css"', body)


def test_built_bundle_calls_the_greeting_endpoint() -> None:
    # The wording is no longer shared with the bundle, so the request path is what the
    # two stacks have to agree on. Both write it down by hand; this pins them together
    # and fails if the committed build is stale relative to src/api/greeting.ts.
    bundles = list((STATIC_DIR / "assets").glob("index-*.js"))
    assert bundles, "no built JS bundle found; run `pixi run web-build`"
    assert any(
        "/api/greeting" in bundle.read_text(encoding="utf-8") for bundle in bundles
    )


def test_stylesheet_contains_tailwind_utilities() -> None:
    stylesheets = list((STATIC_DIR / "assets").glob("index-*.css"))
    assert stylesheets, "no built stylesheet found; run `pixi run web-build`"
    css = "\n".join(sheet.read_text(encoding="utf-8") for sheet in stylesheets)
    # A class used by App.tsx, proving Tailwind actually scanned the sources.
    assert "tracking-tight" in css


def test_security_headers_present() -> None:
    response = TestClient(create_app()).get("/")
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    # The page has no inline script or style, so the policy must not need to allow any.
    assert "unsafe-inline" not in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_static_assets_get_security_headers() -> None:
    # The headers come from middleware wrapping the whole app, so the /static mount
    # must be covered too -- the CSP is what keeps the bundle from loading anything
    # it did not ship with.
    client = TestClient(create_app())
    bundles = list((STATIC_DIR / "assets").glob("index-*.js"))
    assert bundles, "no built JS bundle found; run `pixi run web-build`"
    response = client.get(f"/static/assets/{bundles[0].name}")
    assert response.status_code == 200
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_greeting_endpoint_returns_json() -> None:
    # The hand-built payload. greeting.json stays the single source of truth, so the
    # body is asserted against GREETING rather than a literal.
    response = TestClient(create_app()).get("/api/greeting")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"greeting": GREETING}
    # The wording ships inside the wheel, so a cached copy would outlive its deploy.
    assert response.headers["Cache-Control"] == "no-store"


def test_greeting_endpoint_gets_security_headers() -> None:
    # Same middleware, but worth pinning separately: the page fetches this route, so it
    # is the one place connect-src 'self' has to hold.
    response = TestClient(create_app()).get("/api/greeting")
    assert "connect-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


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
