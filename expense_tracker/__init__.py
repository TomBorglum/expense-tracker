"""Expense Tracker application package.

Exposes the application factory. Nothing is created at import time so tests can
build isolated app instances with their own configuration.
"""

import os
from collections.abc import Mapping
from typing import Any

from flask import Flask

from expense_tracker.config import Config


def create_app(test_config: Mapping[str, Any] | None = None) -> Flask:
    """Build and configure a Flask application.

    Args:
        test_config: Overrides applied after the default config. Tests pass a
            throwaway DATABASE path here so they never touch the instance folder.
    """
    # instance_relative_config keeps generated state (the SQLite file) in
    # instance/, outside the package and outside version control.
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.config["DATABASE"] = Config.database_path(app.instance_path)

    if test_config is not None:
        # Assigned key by key rather than via config.update(): Flask types the
        # config mapping loosely enough that update() trips basedpyright's
        # strict reportUnknownMemberType.
        for key, value in test_config.items():
            app.config[key] = value

    # Flask does not create the instance folder itself.
    os.makedirs(app.instance_path, exist_ok=True)

    from expense_tracker import db
    from expense_tracker.routes import dashboard

    db.init_app(app)
    app.register_blueprint(dashboard.bp)

    return app
