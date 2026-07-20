import os

from flask import Flask
from flask_wtf import CSRFProtect

csrf = CSRFProtect()


def create_app() -> Flask:
    app = Flask(__name__)
    # CSRF token signing key. Set SECRET_KEY in the environment for real
    # deployments (a stable key shared across workers/restarts); fall back to an
    # ephemeral random key for local dev so the app still boots. Never hardcode one.
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32)
    csrf.init_app(app)  # pyright: ignore[reportUnknownMemberType]  # untyped lib

    @app.get("/")
    def hello() -> str:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        return "Hello, World!"

    return app
