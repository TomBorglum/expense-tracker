"""SQLite access helpers.

Uses the stdlib sqlite3 module, so there is no dependency to pin. The connection
is created lazily per request and closed when the application context tears down.
"""

import sqlite3
from pathlib import Path
from typing import cast

import click
from flask import Flask, current_app, g


def get_db() -> sqlite3.Connection:
    """Return the connection for the current app context, opening it if needed."""
    if "db" not in g:
        connection = sqlite3.connect(
            cast(str, current_app.config["DATABASE"]),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        # Rows addressable by column name rather than position.
        connection.row_factory = sqlite3.Row
        # Not on by default in sqlite3; required for foreign keys to be enforced.
        _ = connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection

    return cast(sqlite3.Connection, g.db)


def close_db(_exception: BaseException | None = None) -> None:
    """Close the connection if one was opened during this app context."""
    db = cast(sqlite3.Connection | None, g.pop("db", None))
    if db is not None:
        db.close()


def init_db() -> None:
    """Create the schema, dropping any existing tables."""
    # Read via pathlib rather than Flask's open_resource(): the latter is typed
    # as IO[Unknown], which basedpyright's strict mode rejects.
    schema = Path(current_app.root_path) / "schema.sql"
    _ = get_db().executescript(schema.read_text(encoding="utf-8"))


@click.command("init-db")
def init_db_command() -> None:
    """Clear existing data and create fresh tables."""
    init_db()
    click.echo("Initialized the database.")


def init_app(app: Flask) -> None:
    """Register database teardown and CLI commands on the application."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
