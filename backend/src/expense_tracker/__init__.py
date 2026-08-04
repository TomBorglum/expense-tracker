import json
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

_PACKAGE_DIR = Path(__file__).parent
_GREETING_FILE = _PACKAGE_DIR / "greeting.json"

# Security headers applied to every response. This app serves JSON and nothing else,
# so the page-oriented directives a browser shell would need (script-src, style-src,
# connect-src, COOP) have nothing to describe here. What is left says "this response
# is not a document and must not be treated as one".
_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _load_greeting() -> str:
    # json.loads returns Any; cast once here so the module-level constant is typed.
    payload = cast(
        dict[str, str], json.loads(_GREETING_FILE.read_text(encoding="utf-8"))
    )
    return payload["greeting"]


# Single source of truth for the greeting. It reaches any client over the API below,
# so this file is the one place the wording is written down.
GREETING = _load_greeting()


def create_app() -> FastAPI:
    # No OpenAPI schema and no docs routes. One hand-written JSON route does not earn
    # a generated document, and /docs, /redoc and /openapi.json would be public surface
    # advertising it. The app still reads no configuration of any kind.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    # Wraps the whole ASGI app. Registered before the CORS middleware below, which
    # makes it the inner of the two -- see the ordering note there.
    @app.middleware("http")
    async def add_security_headers(  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            # `_ =` because setdefault returns the header's existing value and we have
            # no use for it; recommended mode's reportUnusedCallResult wants that said
            # out loud rather than left to the reader.
            _ = response.headers.setdefault(header, value)
        return response

    # The whole API. The payload is built by hand rather than derived from a
    # response_model: with openapi_url=None there is no schema to publish, so the shape
    # is declared here and mirrored by hand in frontend/src/api/greeting.ts. Change the
    # two together.
    @app.get("/api/greeting")
    async def greeting() -> JSONResponse:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        # no-store because the wording ships inside the wheel: a cached copy would
        # outlive the deploy that changed it.
        return JSONResponse(
            {"greeting": GREETING}, headers={"Cache-Control": "no-store"}
        )

    # Added last, so it is the outermost middleware: that is what lets it answer a
    # preflight itself instead of passing OPTIONS down to a router that has no such
    # route. The consequence is that a preflight response carries the CORS headers but
    # not the ones above, which is correct -- there is no body to protect.
    #
    # Open to every origin because the frontend is a separate app served from its own
    # dev server (vite on 5173), and packaging the two into one deployable is out of
    # scope. This is a deliberate dev-time posture, not a default to ship: the day the
    # API grows cookies or an Authorization header, the wildcard is what has to be
    # replaced with a real origin list, because it cannot be combined with
    # allow_credentials=True -- the CORS spec forbids the pair and browsers reject it.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app
