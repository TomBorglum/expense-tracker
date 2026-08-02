import json
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

_PACKAGE_DIR = Path(__file__).parent
# Built by `pixi run web-build` (vite) and committed, so the wheel is self-contained
# and the lean prod environment never needs Node. Public so the tests can locate the
# bundle without going through the app object.
STATIC_DIR = _PACKAGE_DIR / "static"
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


def _load_greeting() -> str:
    # json.loads returns Any; cast once here so the module-level constant is typed.
    payload = cast(
        dict[str, str], json.loads(_GREETING_FILE.read_text(encoding="utf-8"))
    )
    return payload["greeting"]


# Single source of truth for the greeting: vite imports this same file at build time
# (see the "@data" alias in vite.config.ts), so the page and the app cannot disagree.
GREETING = _load_greeting()


def create_app() -> FastAPI:
    # No OpenAPI schema and no docs routes: the app exposes no API, so /docs, /redoc
    # and /openapi.json would be public surface describing nothing. The app reads no
    # configuration -- the greeting is baked into the bundle at build time.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    # Wraps the whole ASGI app, so the static mount below gets the headers too.
    @app.middleware("http")
    async def add_security_headers(  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    # The only public route. Everything else the page needs is a static asset served
    # by the /static mount below; the greeting is baked into the bundle at build time,
    # so no API endpoint is exposed.
    @app.get("/")
    async def index() -> FileResponse:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        return FileResponse(STATIC_DIR / "index.html")

    # vite emits asset URLs under this exact prefix (see `base` in vite.config.ts),
    # so the mount path must not change.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
