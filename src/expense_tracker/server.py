"""Flask app: a single server-rendered dashboard page. No JSON API, no JS.

The route reads optional ``?from=&to=&category=`` query args, runs the pure
functions in :mod:`expense_tracker.queries`, and hands the results to Jinja2.
Filtering is driven entirely by an HTML ``<form method="get">`` that reloads the
page - there is no client-side JavaScript.
"""

from flask import Flask, render_template, request

from . import config, db, queries


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(config.ROOT_DIR / "templates"),
        static_folder=str(config.ROOT_DIR / "static"),
    )

    @app.get("/")
    def dashboard():
        # Normalize blank query args to None so filters are truly optional.
        date_from = request.args.get("from") or None
        date_to = request.args.get("to") or None
        category = request.args.get("category") or None
        filters = dict(date_from=date_from, date_to=date_to, category=category)

        conn = db.connect()
        try:
            context = dict(
                expenses=queries.all_expenses(conn, **filters),
                by_category=queries.total_by_category(conn, **filters),
                by_month=queries.total_by_month(conn, **filters),
                total=queries.grand_total(conn, **filters),
                all_categories=queries.categories(conn),
                min_date=queries.date_range(conn)[0],
                max_date=queries.date_range(conn)[1],
                # Echo current filter values back into the form.
                selected=dict(date_from=date_from or "", date_to=date_to or "", category=category or ""),
            )
        finally:
            conn.close()
        return render_template("index.html", **context)

    return app


def main() -> None:
    """Rebuild the database from CSV, then serve the dashboard."""
    from .loader import build

    count = build()
    print(f"Loaded {count} expense(s); serving on http://{config.HOST}:{config.PORT}")
    app = create_app()
    app.run(host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
