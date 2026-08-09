import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from expense_tracker.db import ExpensesUnavailableError, PostgresExpenseRepository

# Port 1 refuses instantly, so this reaches a real driver against a real unreachable
# server without needing one - and without the postgres marker, because nothing here
# expects a cluster to exist. Same address, same reasoning, as the greeting's.
_UNREACHABLE = "postgresql+asyncpg://nobody@127.0.0.1:1/none"


async def _read_through_repository() -> object:
    engine = create_async_engine(_UNREACHABLE)
    try:
        async with AsyncSession(engine) as session:
            return await PostgresExpenseRepository(session).list_expenses()
    finally:
        await engine.dispose()


def test_query_failure_raises_the_domain_exception() -> None:
    """The property that lets db.py stay free of fastapi.

    A driver failure has to leave the repository as ExpensesUnavailableError, not as an
    HTTPException and not as the raw OSError asyncpg lets out - create_app() is the only
    place that knows this is a 503.
    """
    # asyncio.run because there is no anyio or asyncio plugin configured, which is also
    # why test_expense_postgres.py is written this way.
    #
    # Binding the coroutine executes none of it, and leaves asyncio.run as the only call
    # in the block below that can raise (sonar python:S5778).
    pending_read = _read_through_repository()
    with pytest.raises(ExpensesUnavailableError):
        _ = asyncio.run(pending_read)
