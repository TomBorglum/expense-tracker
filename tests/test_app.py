import re
from pathlib import Path

from expense_tracker import GREETING, create_app


def _static_dir() -> Path:
    static_folder = create_app().static_folder
    assert static_folder is not None
    return Path(static_folder)


def test_index_serves_built_page() -> None:
    client = create_app().test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    body = response.get_data(as_text=True)
    # vite emits the bundle as external files under the /static/ base.
    assert re.search(r'src="/static/assets/index-[^"]+\.js"', body)
    assert re.search(r'href="/static/assets/index-[^"]+\.css"', body)


def test_built_bundle_contains_greeting() -> None:
    # greeting.json is the single source of truth: Flask reads it at import time and
    # vite bakes it into the bundle. If the committed build is stale relative to
    # greeting.json, this fails -- which is the point.
    bundles = list((_static_dir() / "assets").glob("index-*.js"))
    assert bundles, "no built JS bundle found; run `pixi run web-build`"
    assert any(GREETING in bundle.read_text(encoding="utf-8") for bundle in bundles)


def test_stylesheet_contains_tailwind_utilities() -> None:
    stylesheets = list((_static_dir() / "assets").glob("index-*.css"))
    assert stylesheets, "no built stylesheet found; run `pixi run web-build`"
    css = "\n".join(sheet.read_text(encoding="utf-8") for sheet in stylesheets)
    # A class used by App.tsx, proving Tailwind actually scanned the sources.
    assert "tracking-tight" in css


def test_security_headers_present() -> None:
    response = create_app().test_client().get("/")
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    # The page has no inline script or style, so the policy must not need to allow any.
    assert "unsafe-inline" not in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_greeting_is_not_exposed_by_an_api() -> None:
    # The greeting is baked in at build time on purpose: the page is the only public
    # surface, so there must be no endpoint serving it.
    client = create_app().test_client()
    assert client.get("/api/hello").status_code == 404
    assert client.get("/api/greeting").status_code == 404


def test_csrf_protection_enabled() -> None:
    app = create_app()
    # Flask-WTF registers CSRFProtect under app.extensions["csrf"] and needs a
    # signing key; both being present means state-changing routes are protected.
    assert "csrf" in app.extensions
    assert app.secret_key  # signing key from FLASK_SECRET_KEY, set by the test task
