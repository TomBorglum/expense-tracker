from flask import Flask
from flask_wtf import CSRFProtect

csrf = CSRFProtect()


def create_app() -> Flask:
    app = Flask(__name__)
    # Load config from FLASK_-prefixed env vars, e.g. FLASK_SECRET_KEY -> SECRET_KEY.
    # Production must set FLASK_SECRET_KEY; the test/serve tasks supply a dev value.
    app.config.from_prefixed_env()
    csrf.init_app(app)  # pyright: ignore[reportUnknownMemberType]  # untyped lib

    @app.get("/")
    def hello() -> str:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        return "Hello, World!"

    return app
