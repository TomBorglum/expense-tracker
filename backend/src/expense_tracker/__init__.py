from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from .db import GreetingUnavailableError
from .deps import GreetingRepositoryDep, lifespan

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


def create_app() -> FastAPI:
    # No OpenAPI schema and no docs routes. One hand-written JSON route does not earn
    # a generated document, and /docs, /redoc and /openapi.json would be public surface
    # advertising it.
    #
    # Still a no-arg factory, and still cheap: the lifespan is what opens the
    # connection pool, so building an app touches no socket and reads no environment.
    # `uvicorn --factory` and the whole HTTP suite depend on that.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

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
    # two together. Only the shape is duplicated - the wording lives in one row of the
    # greeting table and is duplicated nowhere.
    #
    # Reading it through an injected repository rather than inline is what lets the
    # tests swap PostgreSQL for a fake; see deps.provide_greeting_repository.
    @app.get("/api/greeting")
    async def greeting(  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        greetings: GreetingRepositoryDep,
    ) -> JSONResponse:
        # no-store because the wording is now a row somebody can UPDATE: a cached copy
        # would outlive the change.
        return JSONResponse(
            {"greeting": await greetings.get_current_greeting()},
            headers={"Cache-Control": "no-store"},
        )

    # The one place the repository's failure becomes an HTTP status, which is what lets
    # db.py stay free of fastapi. Registered handlers run in starlette's
    # ExceptionMiddleware, which sits inside the middleware added above, so this
    # response still collects the security headers on its way out.
    @app.exception_handler(GreetingUnavailableError)
    async def handle_greeting_unavailable(  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        _request: Request, _exc: Exception
    ) -> JSONResponse:
        # Both causes - an unreachable server, and the table present with its seed row
        # gone - are server faults a client should retry, so both answer 503 rather
        # than 404. Neither argument is used: the detail is deliberately the same
        # either way, so a client learns nothing about the database from a failure.
        return JSONResponse({"detail": "greeting unavailable"}, status_code=503)

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
