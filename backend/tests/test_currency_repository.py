import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from expense_tracker.currency_repository import (
    CurrenciesUnavailableError,
    PostgresCurrencyRepository,
)

# Port 1 refuses instantly, so this reaches a real driver against a real unreachable
# server without needing one - and without the postgres marker, because nothing here
# expects a cluster to exist.
_UNREACHABLE = "postgresql+asyncpg://nobody@127.0.0.1:1/none"


async def _read_through_repository() -> object:
    engine = create_async_engine(_UNREACHABLE)
    try:
        async with AsyncSession(engine) as session:
            return await PostgresCurrencyRepository(session).list_currencies()
    finally:
        await engine.dispose()


def test_query_failure_raises_the_domain_exception() -> None:
    """A driver failure leaves the repository as CurrenciesUnavailableError, not as an
    HTTPException and not as the raw OSError asyncpg lets out."""
    # asyncio.run because no anyio or asyncio plugin is configured.
    #
    # Binding the coroutine executes none of it, and leaves asyncio.run as the only
    # call in the block below that can raise (sonar python:S5778).
    pending_read = _read_through_repository()
    with pytest.raises(CurrenciesUnavailableError):
        _ = asyncio.run(pending_read)
