"""Tests for the pure query functions."""

from decimal import Decimal

from expense_tracker import queries


def test_grand_total(conn):
    assert queries.grand_total(conn) == Decimal("129.50")


def test_all_expenses_sorted_newest_first(conn):
    rows = queries.all_expenses(conn)
    assert [e.date for e in rows] == [
        "2026-06-28",
        "2026-06-15",
        "2026-05-07",
        "2026-05-03",
    ]
    assert rows[0].amount == Decimal("15.00")


def test_total_by_category_ordered_by_total_desc(conn):
    totals = queries.total_by_category(conn)
    assert totals[0].category == "Groceries"
    assert totals[0].total == Decimal("102.50")
    assert dict((c.category, c.total) for c in totals) == {
        "Groceries": Decimal("102.50"),
        "Entertainment": Decimal("15.00"),
        "Transport": Decimal("12.00"),
    }


def test_total_by_month(conn):
    by_month = {m.month: m.total for m in queries.total_by_month(conn)}
    assert by_month == {"2026-05": Decimal("66.20"), "2026-06": Decimal("63.30")}


def test_filter_by_category(conn):
    rows = queries.all_expenses(conn, category="Groceries")
    assert len(rows) == 2
    assert queries.grand_total(conn, category="Groceries") == Decimal("102.50")


def test_filter_by_date_range(conn):
    rows = queries.all_expenses(conn, date_from="2026-06-01", date_to="2026-06-30")
    assert [e.date for e in rows] == ["2026-06-28", "2026-06-15"]


def test_categories_distinct_sorted(conn):
    assert queries.categories(conn) == ["Entertainment", "Groceries", "Transport"]


def test_date_range(conn):
    assert queries.date_range(conn) == ("2026-05-03", "2026-06-28")


def test_date_range_empty(tmp_path):
    from expense_tracker import db, loader

    (tmp_path / "empty.csv").write_text(
        "date,amount,category,description\n", encoding="utf-8"
    )
    loader.build(data_dir=tmp_path, db_path=tmp_path / "e.sqlite")
    connection = db.connect(tmp_path / "e.sqlite")
    try:
        assert queries.date_range(connection) == (None, None)
        assert queries.grand_total(connection) == Decimal("0.00")
    finally:
        connection.close()
