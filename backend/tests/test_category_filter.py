import pytest

from expense_tracker.category_filter import (
    CategoryFilter,
    CategoryFilterError,
    parse_category_filter,
)

# Nothing here touches HTTP or a session: reading query values is string work, which
# is the whole reason it lives in a module of its own.

_FOOD = CategoryFilter(frozenset({"Food"}))


def test_one_value_is_a_filter_of_one_name() -> None:
    assert parse_category_filter(["Food"]) == _FOOD


def test_two_values_are_a_filter_of_both() -> None:
    """Either matches: the repository turns the set into one IN clause."""
    assert parse_category_filter(["Food", "Housing"]) == CategoryFilter(
        frozenset({"Food", "Housing"})
    )


def test_no_values_is_no_filter_at_all() -> None:
    """None is what the repository reads as "no clause", and what a request made
    before the parameter existed asks for."""
    assert parse_category_filter(None) is None


def test_a_repeated_value_collapses() -> None:
    assert parse_category_filter(["Food", "Food"]) == _FOOD


def test_a_value_is_stripped_the_way_the_loader_strips_a_field() -> None:
    """A stored category never carries surrounding whitespace, because the loader
    strips every field, so a query value is met on the same terms."""
    assert parse_category_filter([" Food "]) == _FOOD
    assert parse_category_filter([" Food", "Food"]) == _FOOD


def test_the_case_is_kept() -> None:
    """Stripped and nothing else: the loader stores the case it read."""
    assert parse_category_filter(["food"]) == CategoryFilter(frozenset({"food"}))


@pytest.mark.parametrize("values", [[""], [" "], ["Food", ""]])
def test_a_blank_value_is_refused(values: list[str]) -> None:
    """Blank after the strip, as the loader refuses one in a file. An empty value is
    malformed rather than absent, matching ?from_date=."""
    with pytest.raises(CategoryFilterError, match="category must not be blank"):
        _ = parse_category_filter(values)


def test_no_values_at_all_is_refused() -> None:
    """A filter naming nothing is a mistake, not "match nothing": absent is None."""
    with pytest.raises(
        CategoryFilterError, match="category filter must name a category"
    ):
        _ = parse_category_filter([])


def test_the_type_refuses_a_blank_however_it_is_built() -> None:
    """The check lives in __post_init__ rather than in the parser, which is what lets
    list_expenses take the type and stop trusting whoever called it."""
    with pytest.raises(CategoryFilterError, match="category must not be blank"):
        _ = CategoryFilter(frozenset({" "}))
    with pytest.raises(
        CategoryFilterError, match="category filter must name a category"
    ):
        _ = CategoryFilter(frozenset())


def test_a_filter_is_frozen() -> None:
    """Immutable, so the validated names cannot be edited past the check."""
    with pytest.raises(AttributeError):
        _FOOD.names = frozenset({""})  # pyright: ignore[reportAttributeAccessIssue]  # the point of the test
