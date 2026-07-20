from expense_tracker import create_app


def test_hello_world() -> None:
    client = create_app().test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "Hello, World!"
