"""Category paths, and the categories a request asks for read off a query string."""

from collections.abc import Sequence
from dataclasses import dataclass

# What joins one level of a category to the next, and the only declaration of it in
# Python. schema.sql states the same shape as a CHECK, which is what makes a level
# unable to contain it - so splitting and joining a path is lossless and nothing here,
# or on the wire, needs escaping.
SEPARATOR = ":"


class CategoryFilterError(Exception):
    """The expenses cannot be read over the requested categories."""


def split_path(path: str) -> tuple[str, ...]:
    """The levels of one fully-qualified category, outermost first."""
    return tuple(path.split(SEPARATOR))


def top_level(path: str) -> str:
    """The outermost level alone, which is the whole of a depth-1 path."""
    return split_path(path)[0]


def path_parent(path: str) -> str | None:
    """The path minus its last level, or None for a depth-1 path, which has none."""
    levels = split_path(path)
    if len(levels) == 1:
        return None
    return SEPARATOR.join(levels[:-1])


def path_name(path: str) -> str:
    """The last level alone, which is what a picker shows under its parent."""
    return split_path(path)[-1]


def strip_path(path: str) -> str:
    """Each level stripped, which is what strip() meant when a path held one level."""
    return SEPARATOR.join(level.strip() for level in path.split(SEPARATOR))


def deepest_ancestor(path: str, selected: frozenset[str]) -> str | None:
    """The deepest selected path this one sits under, or None if it sits under none."""
    # The path's own ancestors, deepest first, rather than a scan of `selected`: two
    # distinct paths of equal length cannot both be ancestors of one path, so no tie is
    # possible, and walking needs no argument that none is.
    levels = split_path(path)
    for depth in range(len(levels), 0, -1):
        candidate = SEPARATOR.join(levels[:depth])
        if candidate in selected:
            return candidate
    return None


@dataclass(frozen=True)
class CategoryFilter:
    """One or more category paths, none of them blank."""

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
    # The same strip the loader applies to every level, so a query value meets a stored
    # one on the terms it was stored under. A value the column could never hold is not
    # refused here: it simply matches nothing, as an unknown category already does.
    return CategoryFilter(frozenset(strip_path(value) for value in values))
