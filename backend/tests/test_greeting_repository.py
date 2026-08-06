import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from expense_tracker.db import GreetingRepository, GreetingUnavailableError

# Port 1 refuses instantly, so this reaches a real driver against a real unreachable
# server without needing one - and without the postgres marker, because nothing here
# expects a cluster to exist.
_UNREACHABLE = "postgresql+asyncpg://nobody@127.0.0.1:1/none"


async def _read_through_repository() -> str:
    engine = create_async_engine(_UNREACHABLE)
    try:
        async with AsyncSession(engine) as session:
            return await GreetingRepository(session).get_current_greeting()
    finally:
        await engine.dispose()


def test_query_failure_raises_the_domain_exception() -> None:
    """The property that lets db.py stay free of fastapi.

    A driver failure has to leave the repository as GreetingUnavailableError, not as an
    HTTPException and not as the raw OSError asyncpg lets out - create_app() is the only
    place that knows this is a 503.
    """
    # asyncio.run rather than an async test: there is no anyio or asyncio plugin in the
    # environment, which is the same reason test_greeting_postgres.py is written this
    # way.
    with pytest.raises(GreetingUnavailableError):
        _ = asyncio.run(_read_through_repository())
