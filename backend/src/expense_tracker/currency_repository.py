"""The currency rate table and how to read it."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from decimal import Decimal
from typing import NamedTuple, override

from sqlalchemy import Identity, Numeric, Text, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class CurrenciesUnavailableError(Exception):
    """The rates could not be read. Not raised for an empty table."""


class CurrencyRate(Base):
    """One row per data line of one rate file. Mirrors schema.sql."""

    __tablename__: str = "currency_rate"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    from_currency: Mapped[str] = mapped_column(Text)
    to_currency: Mapped[str] = mapped_column(Text)
    # Numeric so asyncpg hands back Decimal rather than float: an amount gets
    # multiplied by this.
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))


class CurrencyRateRecord(NamedTuple):
    """One rate detached from the session that read it."""

    from_currency: str
    to_currency: str
    exchange_rate: Decimal


class CurrencyRepository(ABC):
    """The contract a caller depends on in order to read exchange rates."""

    @abstractmethod
    async def list_currencies(self) -> Sequence[CurrencyRateRecord]: ...


class PostgresCurrencyRepository(CurrencyRepository):
    """Reads rates through a session it is given and does not own."""

    _session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def list_currencies(self) -> Sequence[CurrencyRateRecord]:
        """Every rate, by pair. An empty table returns an empty sequence."""
        try:
            rows = await self._session.execute(
                select(
                    CurrencyRate.from_currency,
                    CurrencyRate.to_currency,
                    CurrencyRate.exchange_rate,
                ).order_by(
                    CurrencyRate.from_currency,
                    CurrencyRate.to_currency,
                    CurrencyRate.id,
                )
            )
        except (SQLAlchemyError, OSError) as exc:
            # OSError as well: asyncpg lets asyncio's ConnectionRefusedError out
            # unwrapped when nothing is listening.
            raise CurrenciesUnavailableError("currency rate query failed") from exc
        # The select names the columns in CurrencyRateRecord's field order.
        return [CurrencyRateRecord(*row) for row in rows.all()]
