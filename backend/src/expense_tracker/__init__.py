import json
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
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


# Single source of truth for the greeting. It reaches the page over the API below, so
# this file is the one place the wording is written down.
GREETING = _load_greeting()


def create_app() -> FastAPI:
    # No OpenAPI schema and no docs routes. One hand-written JSON route does not earn
    # a generated document, and /docs, /redoc and /openapi.json would be public surface
    # advertising it. The app still reads no configuration of any kind.
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

    # Serves the shell. The page it boots fetches the greeting from /api/greeting; the
    # rest of what it needs is a static asset served by the /static mount below.
    @app.get("/")
    async def index() -> FileResponse:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        return FileResponse(STATIC_DIR / "index.html")

    # The whole API. The payload is built by hand rather than derived from a
    # response_model: with openapi_url=None there is no schema to publish, so the shape
    # is declared here and mirrored by hand in frontend/src/api/greeting.ts. Change the
    # two together. The page reaches this over the CSP's connect-src 'self'.
    @app.get("/api/greeting")
    async def greeting() -> JSONResponse:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        # no-store because the wording ships inside the wheel: a cached copy would
        # outlive the deploy that changed it.
        return JSONResponse(
            {"greeting": GREETING}, headers={"Cache-Control": "no-store"}
        )

    # vite emits asset URLs under this exact prefix (see `base` in vite.config.ts),
    # so the mount path must not change.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
