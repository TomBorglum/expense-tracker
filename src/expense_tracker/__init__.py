from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def hello() -> str:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        return "Hello, World!"

    return app
