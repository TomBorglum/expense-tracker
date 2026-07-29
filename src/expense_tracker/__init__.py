from flask import Flask, render_template
from flask_wtf import CSRFProtect

csrf = CSRFProtect()

# Single source of truth for the greeting, shared by the rendered page and the
# plain-text endpoint so the two cannot drift apart.
GREETING = "Hello, World!"


def create_app() -> Flask:
    app = Flask(__name__)
    # Load config from FLASK_-prefixed env vars, e.g. FLASK_SECRET_KEY -> SECRET_KEY.
    # Production must set FLASK_SECRET_KEY; the test/serve tasks supply a dev value.
    app.config.from_prefixed_env()
    csrf.init_app(app)  # pyright: ignore[reportUnknownMemberType]  # untyped lib

    @app.get("/")
    def index() -> str:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        return render_template("index.html", greeting=GREETING)

    @app.get("/api/hello")
    def hello() -> str:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        return GREETING

    return app
