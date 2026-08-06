"""How the app is wired to PostgreSQL: configuration, lifetime, injection.

Nothing here knows how to read a greeting - that is db.py's job, and the dependency
below hands its repository to a route. The import goes one way only: this module
imports db, db imports nothing from here.

The engine is built by the lifespan rather than at import time, so merely constructing
an app - which most of the test suite does - opens no socket and needs no database.
Everything is async because the app runs on uvicorn's event loop: a blocking driver
would stall every other request while one waited on a socket.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, TypedDict, cast

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .db import GreetingRepository


def database_url() -> str:
    """The DSN to connect with. Required, with deliberately no fallback.

    The development value is declared once, in pixi.toml's
    [feature.test.activation.env], so `pixi run` hands it to serve, test and the editor
    alike. A default here would be that value written a second time, and in a
    deployment it would turn a forgotten setting into a silent connection attempt
    against the deployment's own loopback.
    """
    url = os.environ.get("DATABASE_URL")
    if url is None:
        raise RuntimeError(
            "DATABASE_URL is not set; `pixi run` supplies the development value"
        )
    return url


class AppState(TypedDict):
    """What the lifespan hands to every request. The contract, written down.

    It cannot be used as the annotation that reads it back: starlette types that as
    Request[AppState], and FastAPI rejects a subscripted generic as a parameter
    annotation because it tests `isinstance(annotation, type)`. Hence the cast in
    provide_session below, which is the one place a framework Any is pinned back down.
    """

    sessions: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[AppState]:
    """Own the connection pool for exactly as long as the process serves requests.

    Attached in create_app(). starlette runs it only when the app is actually served -
    or when a test enters TestClient as a context manager - which is what keeps a bare
    `TestClient(create_app())` free of any database at all.

    The app argument is unused (the pool is per-process, not per-app) but starlette
    passes it positionally, hence the underscore rather than a dropped parameter. The
    return type is AsyncGenerator, not AsyncIterator: basedpyright deprecates the
    latter under @asynccontextmanager.
    """
    engine = create_async_engine(database_url())
    try:
        # Merged into every request's state by starlette. expire_on_commit=False
        # because nothing here writes; it only keeps loaded rows usable after a commit.
        yield {"sessions": async_sessionmaker(engine, expire_on_commit=False)}
    finally:
        # Returns the pooled sockets rather than leaving uvicorn to be killed with
        # connections still open on the server side.
        await engine.dispose()


async def provide_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """One session per request, closed once the response has been generated.

    Opening a session connects to nothing - SQLAlchemy dials on the first statement -
    so an unreachable server still fails inside the repository, where it is converted.
    """
    sessions = cast("async_sessionmaker[AsyncSession]", request.state["sessions"])
    async with sessions() as session:
        yield session


def provide_greeting_repository(
    session: Annotated[AsyncSession, Depends(provide_session)],
) -> GreetingRepository:
    """The seam the HTTP tests replace.

    tests/conftest.py overrides this with a fake repository, so the CORS,
    security-header and 404 tests never touch a database; only
    tests/test_greeting_postgres.py, behind the `postgres` marker, gets the real one.
    """
    return GreetingRepository(session)


# The annotation routes actually write. Declaring it here rather than at each use keeps
# Depends out of the router entirely, and is the form FastAPI's own docs use.
GreetingRepositoryDep = Annotated[
    GreetingRepository, Depends(provide_greeting_repository)
]
