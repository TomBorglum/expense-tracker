"""Category paths, and the categories a request asks for read off a query string."""

from collections.abc import Sequence
from dataclasses import dataclass

# What joins one level of a category to the next, and the only declaration of it in
# Python. schema.sql states the same shape as a CHECK, which is what makes a level
# unable to contain it - so splitting and joining a path is lossless and nothing here,
# or on the wire, needs escaping.
SEPARATOR = ":"

# The two values ?category_default= takes, naming the root's own sign. Anything else is
# refused rather than ignored, the way validate_currency_code refuses rather than
# uppercases. Both are needed: without "all" a request could not keep one path while
# deselecting the root it sits under, the absent flag reading a selected path as
# "these and no others".
NO_CATEGORIES = "none"
ALL_CATEGORIES = "all"


class CategoryFilterError(Exception):
    """The expenses cannot be read over the requested categories."""


def split_path(path: str) -> tuple[str, ...]:
    """The levels of one fully-qualified category, outermost first."""
    return tuple(path.split(SEPARATOR))


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


@dataclass(frozen=True)
class CategorySelection:
    """What a request selects: the root's own sign, and the paths that flip it.

    A row is selected by the longest of those paths matching it, and by `default` when
    none of them does - so a selection costs one value per point it changes at, rather
    than one per category it covers.
    """

    selected: frozenset[str]
    deselected: frozenset[str]
    default: bool

    def __post_init__(self) -> None:
        # Every construction, not only the parsed one: this is what lets a repository
        # take the type and stop trusting its caller to have checked. An empty pair is
        # legal, unlike the filter this replaces - it is the default selection, which
        # every request made before anything could be deselected asked for.
        if any(not name.strip() for name in self.selected | self.deselected):
            raise CategoryFilterError("category must not be blank")
        both = sorted(self.selected & self.deselected)
        if both:
            # No reading resolves it: the two flips are the same length, so neither is
            # the longer one. Named in the detail, which goes out as the 422's body.
            raise CategoryFilterError(
                f"category both selected and deselected: {', '.join(both)}"
            )

    def flips(self) -> tuple[tuple[str, bool], ...]:
        """Every flipping path with the sign it imposes, longest path first.

        Longest first is the rule itself: read in this order the first match decides,
        so a child's own sign beats the parent it sits under. Depth in levels, never in
        characters, for the reason a match is by level. The path breaks a tie between
        two of the same depth, so the order - and the SQL built from it - is
        deterministic.
        """
        flips = [(path, True) for path in self.selected]
        flips.extend((path, False) for path in self.deselected)
        return tuple(
            sorted(flips, key=lambda flip: (-len(split_path(flip[0])), flip[0]))
        )

    def everything(self) -> bool:
        """Whether every category is selected: a query that needs no clause."""
        # Nothing deselected is what makes it everything: a path selected inside an
        # already selected root narrows nothing, so it needs no clause either.
        return self.default and not self.deselected


# What list_expenses reads as every category there is, which is the selection a request
# naming none of the three parameters makes.
EVERYTHING = CategorySelection(
    selected=frozenset(), deselected=frozenset(), default=True
)


def _paths(values: Sequence[str] | None) -> frozenset[str]:
    """One query key's values as paths, an absent key naming none."""
    if values is None:
        return frozenset()
    # The same strip the loader applies to every level, so a query value meets a stored
    # one on the terms it was stored under. A value the column could never hold is not
    # refused here: it simply matches nothing, as an unknown category already does.
    return frozenset(strip_path(value) for value in values)


def _default(value: str | None, selected: frozenset[str]) -> bool:
    """Whether the root is selected: what ?category_default= states, or works out to."""
    if value is None:
        # Selected unless the request names paths to select. That is what keeps
        # ?category=Food meaning Food and no others, which is what it meant before
        # there was a root to flip - so the flag is only ever needed where that
        # reading is the wrong one.
        return not selected
    if value not in {NO_CATEGORIES, ALL_CATEGORIES}:
        raise CategoryFilterError(f"unknown category_default: {value}")
    return value == ALL_CATEGORIES


def parse_category_selection(
    selected: Sequence[str] | None,
    deselected: Sequence[str] | None,
    default: str | None,
) -> CategorySelection:
    """The three query values as a selection, or CategoryFilterError.

    All three absent is every category, which is the request this endpoint answered
    before a category could be deselected.
    """
    chosen = _paths(selected)
    return CategorySelection(
        selected=chosen,
        deselected=_paths(deselected),
        default=_default(default, chosen),
    )
