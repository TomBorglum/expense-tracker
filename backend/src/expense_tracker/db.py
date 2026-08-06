"""PostgreSQL access for the one thing this API serves.

Everything here is async because the app runs on uvicorn's event loop: a blocking
driver would stall every other request while one waited on a socket. The engine is
built by the lifespan rather than at import time, so merely constructing an app -
which most of the test suite does - opens no socket and needs no database.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TypedDict, cast

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import Text, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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


class Base(DeclarativeBase):
    """Declarative root. It exists to give Greeting a typed metaclass, nothing more."""


class Greeting(Base):
    """The single row `GET /api/greeting` serves.

    Mirrors schema.sql, which is the authoritative definition - this class never
    creates the table, it only reads it.
    """

    # Annotated because recommended mode's reportUnannotatedClassAttribute wants every
    # attribute of a non-final class typed. `str` rather than `Mapped[str]` is what
    # keeps SQLAlchemy treating it as configuration instead of a column.
    __tablename__: str = "greeting"

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(Text)


class AppState(TypedDict):
    """What the lifespan hands to every request. The contract, written down.

    It cannot be used as the annotation that reads it back: starlette types that as
    Request[AppState], and FastAPI rejects a subscripted generic as a parameter
    annotation because it tests `isinstance(annotation, type)`. Hence the cast in
    provide_greeting below, which is the one place a framework Any is pinned back down.
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


async def provide_greeting(request: Request) -> str:
    """The greeting text, read from PostgreSQL. The seam the HTTP tests replace.

    tests/conftest.py overrides this with a constant, so the CORS, security-header and
    404 tests never touch a database; only tests/test_greeting_postgres.py, behind the
    `postgres` marker, exercises the body below.
    """
    sessions = cast("async_sessionmaker[AsyncSession]", request.state["sessions"])
    try:
        async with sessions() as session:
            # order_by/limit rather than get(1): the singleton CHECK lives in the
            # schema, and this stays correct without it.
            message = await session.scalar(
                select(Greeting.message).order_by(Greeting.id).limit(1)
            )
    except (SQLAlchemyError, OSError) as exc:
        # OSError as well as SQLAlchemyError: when nothing is listening, asyncpg lets
        # asyncio's ConnectionRefusedError out, and SQLAlchemy only wraps what its
        # DBAPI shim recognises, so the raw OSError arrives here unconverted.
        raise HTTPException(status_code=503, detail="greeting unavailable") from exc
    if message is None:
        # Table present, seed row gone. A deployment fault rather than a client one,
        # and the same status a client should retry on.
        raise HTTPException(status_code=503, detail="greeting unavailable")
    return message
