"""The categories a request asks for, and reading them off a query string."""

from collections.abc import Sequence
from dataclasses import dataclass


class CategoryFilterError(Exception):
    """The expenses cannot be read over the requested categories."""


@dataclass(frozen=True)
class CategoryFilter:
    """One or more category names, none of them blank."""

    names: frozenset[str]

    def __post_init__(self) -> None:
        # Every construction, not only the parsed one: this is what lets a repository
        # take the type and stop trusting its caller to have checked.
        if not self.names:
            raise CategoryFilterError("category filter must name a category")
        if any(not name.strip() for name in self.names):
            raise CategoryFilterError("category must not be blank")


def parse_category_filter(values: Sequence[str] | None) -> CategoryFilter | None:
    """The values as a filter, or CategoryFilterError. None is no filter at all."""
    if values is None:
        return None
    # The same strip the loader applies to every field, so a query value meets a
    # stored one on the terms it was stored under. Duplicates collapse.
    return CategoryFilter(frozenset(value.strip() for value in values))
