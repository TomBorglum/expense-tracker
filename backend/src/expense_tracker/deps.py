"""How the app is wired to PostgreSQL: engine lifetime and repository injection."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, TypedDict, cast

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import database_url
from .expense_repository import ExpenseRepository, PostgresExpenseRepository


class AppState(TypedDict):
    """What the lifespan hands to every request."""

    sessions: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[AppState]:
    """Owns the connection pool for as long as the process serves requests.

    Attached in create_app(). starlette runs it only when the app is actually served,
    which is what keeps a bare `TestClient(create_app())` free of a database.
    """
    engine = create_async_engine(database_url())
    try:
        yield {"sessions": async_sessionmaker(engine, expire_on_commit=False)}
    finally:
        await engine.dispose()


async def provide_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """One session per request, closed once the response has been generated."""
    # AppState cannot be used as the annotation that reads it back: starlette types
    # that as Request[AppState], and FastAPI rejects a subscripted generic as a
    # parameter annotation. The cast is where that Any is pinned down again.
    sessions = cast("async_sessionmaker[AsyncSession]", request.state["sessions"])
    async with sessions() as session:
        yield session


def provide_expense_repository(
    session: Annotated[AsyncSession, Depends(provide_session)],
) -> ExpenseRepository:
    """The seam tests/conftest.py overrides with a fake."""
    return PostgresExpenseRepository(session)
