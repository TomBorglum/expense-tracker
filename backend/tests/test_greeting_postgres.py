import asyncio
import os

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.testclient import TestClient

from expense_tracker import create_app
from expense_tracker.config import database_url
from expense_tracker.greeting_repository import Greeting

# Talks to the cluster `pixi run backend-db-init` creates. The marker is registered in
# pyproject.toml, which --strict-markers requires.
pytestmark = pytest.mark.postgres


async def _read_message() -> str | None:
    # A throwaway engine per call rather than the app's: this helper is what the
    # endpoint gets checked against, so it must not share the machinery under test.
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            return await session.scalar(
                select(Greeting.message).order_by(Greeting.id).limit(1)
            )
    finally:
        await engine.dispose()


async def _write_message(message: str) -> None:
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            _ = await session.execute(update(Greeting).values(message=message))
            await session.commit()
    finally:
        await engine.dispose()


async def _delete_row() -> None:
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            _ = await session.execute(delete(Greeting))
            await session.commit()
    finally:
        await engine.dispose()


async def _insert_row(message: str) -> None:
    engine = create_async_engine(database_url())
    try:
        async with AsyncSession(engine) as session:
            session.add(Greeting(id=1, message=message))
            await session.commit()
    finally:
        await engine.dispose()


@pytest.fixture(scope="module", autouse=True)
def require_postgres() -> None:
    """Skip locally when no server answers; fail under CI, so a database that did not
    come up cannot go green."""
    try:
        _ = asyncio.run(_read_message())
    except (RuntimeError, SQLAlchemyError, OSError) as exc:
        if os.environ.get("CI") == "true":
            raise
        pytest.skip(
            f"no PostgreSQL at DATABASE_URL; run `pixi run backend-db-init` ({exc})"
        )


def test_greeting_endpoint_matches_the_row_in_postgres() -> None:
    # Context-managed, unlike the HTTP suite: that runs the lifespan, so the app builds
    # a real engine and answers out of the real table.
    with TestClient(create_app()) as client:
        response = client.get("/api/greeting")
    assert response.status_code == 200
    assert response.json() == {"greeting": asyncio.run(_read_message())}


def test_greeting_follows_the_row_when_it_changes() -> None:
    """Changing the row and watching the endpoint follow, which is what proves the
    wording is not still a constant that happens to match the seed."""
    original = asyncio.run(_read_message())
    assert original is not None, (
        "schema.sql seeds one row; run `pixi run backend-db-init`"
    )
    probe = "Hello from row 1 of the greeting table!"
    asyncio.run(_write_message(probe))
    try:
        with TestClient(create_app()) as client:
            response = client.get("/api/greeting")
        assert response.status_code == 200
        assert response.json() == {"greeting": probe}
    finally:
        # Restored even on failure. If the process is killed before this runs,
        # `backend-db-reset && backend-db-init` is the cure.
        asyncio.run(_write_message(original))


def test_greeting_is_unavailable_when_the_row_is_missing() -> None:
    # The table exists but the seed row does not. A server fault, so 503 rather than
    # 404 or a null greeting.
    original = asyncio.run(_read_message())
    assert original is not None, (
        "schema.sql seeds one row; run `pixi run backend-db-init`"
    )
    asyncio.run(_delete_row())
    try:
        with TestClient(create_app()) as client:
            response = client.get("/api/greeting")
        assert response.status_code == 503
        assert response.json() == {"detail": "greeting unavailable"}
    finally:
        asyncio.run(_insert_row(original))
