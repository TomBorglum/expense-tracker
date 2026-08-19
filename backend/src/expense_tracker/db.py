"""The declarative root the ORM models are built on."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared metadata registry. Held in a module of its own so a second repository
    module can share it without importing the first."""
