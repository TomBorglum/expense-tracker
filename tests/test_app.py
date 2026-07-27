from expense_tracker import create_app


def test_hello_world() -> None:
    client = create_app().test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "Hello, World!"


def test_csrf_protection_enabled() -> None:
    app = create_app()
    # Flask-WTF registers CSRFProtect under app.extensions["csrf"] and needs a
    # signing key; both being present means state-changing routes are protected.
    assert "csrf" in app.extensions
    assert app.secret_key  # signing key from FLASK_SECRET_KEY, set by the test task
