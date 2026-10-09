import pytest

from expense_tracker.category_filter import (
    CategoryFilter,
    CategoryFilterError,
    deepest_ancestor,
    parse_category_filter,
    path_name,
    path_parent,
    split_path,
    strip_path,
    top_level,
)

# Nothing here touches HTTP or a session: reading query values is string work, which
# is the whole reason it lives in a module of its own.

_FOOD = CategoryFilter(frozenset({"Food"}))


def test_one_value_is_a_filter_of_one_name() -> None:
    assert parse_category_filter(["Food"]) == _FOOD


def test_two_values_are_a_filter_of_both() -> None:
    """Either matches: the repository ORs one prefix clause per name together."""
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
    # Built outside the blocks, so the only call that can raise inside each is the
    # one being tested.
    blank = frozenset({" "})
    nothing: frozenset[str] = frozenset()
    with pytest.raises(CategoryFilterError, match="category must not be blank"):
        _ = CategoryFilter(blank)
    with pytest.raises(
        CategoryFilterError, match="category filter must name a category"
    ):
        _ = CategoryFilter(nothing)


def test_a_filter_is_frozen() -> None:
    """Immutable, so the validated names cannot be edited past the check."""
    categories = CategoryFilter(frozenset({"Food"}))
    with pytest.raises(AttributeError):
        categories.names = frozenset({""})  # pyright: ignore[reportAttributeAccessIssue]  # the point of the test


def test_a_name_with_no_separator_is_one_level() -> None:
    """The identity every backward-compatibility claim rests on: for a category that
    carries no path, each helper hands back the name itself."""
    assert split_path("Groceries") == ("Groceries",)
    assert top_level("Groceries") == "Groceries"
    assert path_name("Groceries") == "Groceries"
    assert path_parent("Groceries") is None


def test_a_path_is_taken_apart_at_every_separator() -> None:
    assert split_path("Settlement:Alice:Spain") == ("Settlement", "Alice", "Spain")
    assert top_level("Settlement:Alice:Spain") == "Settlement"
    assert path_name("Settlement:Alice:Spain") == "Spain"
    assert path_parent("Settlement:Alice:Spain") == "Settlement:Alice"


def test_a_root_has_no_parent_rather_than_an_empty_one() -> None:
    """None, so the payload drops the key altogether: an empty string would say the
    parent is a category whose name is nothing."""
    assert path_parent("Settlement") is None
    assert path_parent("Settlement:Alice") == "Settlement"


def test_every_level_is_stripped_not_just_the_whole_value() -> None:
    """A level keeping its inner spaces would be a node that renders identically to
    the real one - HTML collapses whitespace - and never merges with it."""
    assert strip_path(" Settlement : Alice ") == "Settlement:Alice"
    assert strip_path("Groceries") == "Groceries"


def test_the_deepest_selected_ancestor_is_the_one_that_wins() -> None:
    """What keeps a row out of two groups at once: Alice's expense is summed under
    Settlement:Alice, and only there, even though Settlement is selected too."""
    selected = frozenset({"Settlement", "Settlement:Alice"})
    assert deepest_ancestor("Settlement:Alice:Spain", selected) == "Settlement:Alice"
    assert deepest_ancestor("Settlement:Alice", selected) == "Settlement:Alice"
    assert deepest_ancestor("Settlement:Bob", selected) == "Settlement"


def test_a_node_counts_as_its_own_ancestor() -> None:
    assert deepest_ancestor("Groceries", frozenset({"Groceries"})) == "Groceries"


def test_a_path_under_nothing_selected_has_no_ancestor() -> None:
    """Unreachable through the real repository, which only returns rows the clause
    matched, but the HTTP suite's fake filters nothing - so aggregation falls back to
    the top level rather than raising."""
    assert deepest_ancestor("Groceries", frozenset({"Settlement"})) is None


def test_a_name_merely_starting_with_another_is_not_under_it() -> None:
    """By level and never by character: this is the whole reason the repository ORs
    `= path` with a LIKE on `path + separator` instead of one bare prefix match."""
    assert deepest_ancestor("SettlementFund", frozenset({"Settlement"})) is None


def test_a_level_of_a_filter_value_is_stripped_too() -> None:
    """The loader strips each level, so a query value meets a stored one on the same
    terms however the path was typed."""
    assert parse_category_filter(["Settlement : Alice"]) == CategoryFilter(
        frozenset({"Settlement:Alice"})
    )


@pytest.mark.parametrize("value", ["Food:", ":Food", "Food::Drink"])
def test_a_value_the_column_could_never_hold_is_not_refused(value: str) -> None:
    """Only blank is refused here. A malformed path is an unmatchable value, which is
    what an unknown category already is - and the filter is checked against the known
    list on neither side. `Food:` compiles to `= 'Food:' OR LIKE 'Food::%'`, so it
    matches nothing rather than acting as an undocumented "strictly below"."""
    assert parse_category_filter([value]) == CategoryFilter(frozenset({value}))
