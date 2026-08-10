"""The declarative root the ORM models are built on."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared metadata registry. Held here so the repository modules need not import
    each other to share one."""
