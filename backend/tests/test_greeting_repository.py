import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from expense_tracker.db import GreetingUnavailableError, PostgresGreetingRepository

# Port 1 refuses instantly, so this reaches a real driver against a real unreachable
# server without needing one - and without the postgres marker, because nothing here
# expects a cluster to exist.
_UNREACHABLE = "postgresql+asyncpg://nobody@127.0.0.1:1/none"


async def _read_through_repository() -> str:
    engine = create_async_engine(_UNREACHABLE)
    try:
        async with AsyncSession(engine) as session:
            return await PostgresGreetingRepository(session).get_current_greeting()
    finally:
        await engine.dispose()


def test_query_failure_raises_the_domain_exception() -> None:
    """The property that lets db.py stay free of fastapi.

    A driver failure has to leave the implementation as GreetingUnavailableError, not as
    an HTTPException and not as the raw OSError asyncpg lets out - create_app() is the
    only place that knows this is a 503. Exercises PostgresGreetingRepository
    specifically; GreetingRepository is abstract and has no behaviour to test.
    """
    # asyncio.run rather than an async test: there is no anyio or asyncio plugin in the
    # environment, which is the same reason test_greeting_postgres.py is written this
    # way.
    #
    # Building the coroutine executes none of it, so it is bound here rather than inline
    # below. That leaves asyncio.run as the only call inside the block that can raise,
    # which is what makes the assertion unambiguous (sonar python:S5778).
    pending_read = _read_through_repository()
    with pytest.raises(GreetingUnavailableError):
        _ = asyncio.run(pending_read)
