import json
from pathlib import Path
from typing import cast

from flask import Flask, Response, send_from_directory
from flask_wtf import CSRFProtect

_PACKAGE_DIR = Path(__file__).parent
# Built by `pixi run web-build` (vite) and committed, so the wheel is self-contained
# and the lean prod environment never needs Node.
_STATIC_DIR = _PACKAGE_DIR / "static"
_GREETING_FILE = _PACKAGE_DIR / "greeting.json"

# Security headers applied to every response. The page loads only its own bundled
# script and stylesheet -- vite emits them as external files, never inline -- so the
# policy needs no 'unsafe-inline' escape hatch.
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
}

csrf = CSRFProtect()


def _load_greeting() -> str:
    # json.loads returns Any; cast once here so the module-level constant is typed.
    payload = cast(
        dict[str, str], json.loads(_GREETING_FILE.read_text(encoding="utf-8"))
    )
    return payload["greeting"]


# Single source of truth for the greeting: vite imports this same file at build time
# (see the "@data" alias in vite.config.ts), so the page and the app cannot disagree.
GREETING = _load_greeting()


def create_app() -> Flask:
    app = Flask(__name__)
    # Load config from FLASK_-prefixed env vars, e.g. FLASK_SECRET_KEY -> SECRET_KEY.
    # Production must set FLASK_SECRET_KEY; the test/serve tasks supply a dev value.
    app.config.from_prefixed_env()
    csrf.init_app(app)  # pyright: ignore[reportUnknownMemberType]  # untyped lib

    # The only public route. Everything else the page needs is a static asset served
    # by Flask's built-in /static/ route; the greeting is baked into the bundle at
    # build time, so no API endpoint is exposed.
    @app.get("/")
    def index() -> Response:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        return send_from_directory(_STATIC_DIR, "index.html")

    @app.after_request
    def add_security_headers(  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        response: Response,
    ) -> Response:
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    return app
