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


def test_built_bundle_contains_greeting() -> None:
    # greeting.json is the single source of truth: the app reads it at import time and
    # vite bakes it into the bundle. If the committed build is stale relative to
    # greeting.json, this fails -- which is the point.
    bundles = list((STATIC_DIR / "assets").glob("index-*.js"))
    assert bundles, "no built JS bundle found; run `pixi run web-build`"
    assert any(GREETING in bundle.read_text(encoding="utf-8") for bundle in bundles)


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


def test_greeting_is_not_exposed_by_an_api() -> None:
    # The greeting is baked in at build time on purpose: the page is the only public
    # surface, so there must be no endpoint serving it.
    client = TestClient(create_app())
    assert client.get("/api/hello").status_code == 404
    assert client.get("/api/greeting").status_code == 404


def test_openapi_docs_are_disabled() -> None:
    # FastAPI publishes an OpenAPI schema and two docs UIs by default. The app has no
    # API to describe, so create_app() turns them off and they must stay off.
    client = TestClient(create_app())
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
