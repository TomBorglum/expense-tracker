import datetime
from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import make_url
from starlette.testclient import TestClient

from expense_tracker import CurrencyPayload, ExpensePayload, config, create_app
from expense_tracker.currency_repository import CurrencyRateRecord
from expense_tracker.expense_repository import ExpenseRecord

# The origin a browser would send. Any value works against a wildcard policy.
_ORIGIN = "http://localhost:5173"

# Parses a response body into typed models instead of casting it to dicts. Reads
# response.content, which is bytes, so Response.json()'s Any never enters the picture.
_EXPENSES = TypeAdapter(list[ExpensePayload])
_CURRENCIES = TypeAdapter(list[CurrencyPayload])

# What the requested_bounds fixture collects: every (from_date, to_date) the route
# handed the expense repository.
_Bounds = list[tuple[datetime.date | None, datetime.date | None]]


def test_security_headers_present(client: TestClient) -> None:
    response = client.get("/api/expenses")
    csp = response.headers["Content-Security-Policy"]
    # The API serves no document, so the policy grants nothing at all.
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_cors_allows_any_origin(client: TestClient) -> None:
    # Every real call is cross-origin, so this header is what makes the response
    # readable to the frontend.
    response = client.get("/api/expenses", headers={"Origin": _ORIGIN})
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"


def test_cors_preflight_is_answered(client: TestClient) -> None:
    # Answered by the CORS middleware itself; the router has no OPTIONS route.
    response = client.options(
        "/api/expenses",
        headers={"Origin": _ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert "GET" in response.headers["Access-Control-Allow-Methods"]


def test_cors_does_not_allow_credentials(client: TestClient) -> None:
    # The spec forbids credentials alongside a wildcard origin, and browsers reject the
    # pair silently.
    response = client.get("/api/expenses", headers={"Origin": _ORIGIN})
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_root_is_not_served(client: TestClient) -> None:
    assert client.get("/").status_code == 404


def test_static_files_are_not_served(client: TestClient) -> None:
    # The frontend owns its own build output; nothing from it ships in the wheel.
    assert client.get("/static/assets/index.js").status_code == 404


def test_unknown_api_routes_404(client: TestClient) -> None:
    # /api is the two routes below and nothing else, not a namespace to grow into by
    # accident.
    assert client.get("/api/hello").status_code == 404


def test_openapi_docs_are_disabled(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_expenses_endpoint_returns_json(
    client: TestClient, expense_records: list[ExpenseRecord]
) -> None:
    response = client.get("/api/expenses")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["Cache-Control"] == "no-store"
    assert _EXPENSES.validate_json(response.content) == [
        ExpensePayload(
            amount="1250.00",
            currency="DKK",
            date="2026-02-02",
            category="Housing",
            details="Rent",
        ),
        ExpensePayload(
            amount="775.37",
            currency="DKK",
            date="2026-01-02",
            category="Insurance",
            details="Accident / Car",
        ),
    ]
    # The fixture is the other half of that literal; if it changes, this should fail
    # rather than quietly assert against itself.
    assert len(expense_records) == 2


def test_expense_amounts_are_strings_not_numbers(client: TestClient) -> None:
    """1250.00 must not arrive as 1250.0.

    ExpensePayload types amount as str, so a route that emitted a JSON number fails to
    parse here rather than passing with a drifted value.
    """
    body = _EXPENSES.validate_json(client.get("/api/expenses").content)
    assert [row.amount for row in body] == ["1250.00", "775.37"]


def test_expenses_endpoint_preserves_the_repository_order(client: TestClient) -> None:
    """Ordering belongs to the repository, not the route. The fake hands back what it
    was given, so this fails if the route ever sorts on its own."""
    body = _EXPENSES.validate_json(client.get("/api/expenses").content)
    assert [row.date for row in body] == ["2026-02-02", "2026-01-02"]


def test_expenses_endpoint_returns_an_empty_list_when_nothing_is_loaded(
    empty_expenses_client: TestClient,
) -> None:
    """200 and [], deliberately not 503.

    An empty expense table is a database nobody has run the loader against yet, which
    is a legitimate state and not a fault. A 503 would train a client to retry forever
    against a server that is working perfectly.
    """
    response = empty_expenses_client.get("/api/expenses")
    assert response.status_code == 200
    assert _EXPENSES.validate_json(response.content) == []


def test_expenses_can_be_requested_in_another_currency(
    client: TestClient, currency_records: list[CurrencyRateRecord]
) -> None:
    """amount and currency are replaced in place: the payload shape is the same one
    the frontend already models, so ?currency needs no change over there."""
    response = client.get("/api/expenses", params={"currency": "EUR"})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert _EXPENSES.validate_json(response.content) == [
        ExpensePayload(
            # 1250.00 * 0.134048, and 775.37 * 0.134048 rounded half up.
            amount="167.56",
            currency="EUR",
            date="2026-02-02",
            category="Housing",
            details="Rent",
        ),
        ExpensePayload(
            amount="103.94",
            currency="EUR",
            date="2026-01-02",
            category="Insurance",
            details="Accident / Car",
        ),
    ]
    # The rate fixture is the other half of those two literals.
    assert currency_records[0] == CurrencyRateRecord("DKK", "EUR", Decimal("0.134048"))


def test_requesting_the_currency_the_expenses_already_use_changes_nothing(
    client: TestClient,
) -> None:
    """Byte for byte the bare response. The rates fixture holds no DKK -> DKK row, so
    this also fails if the route ever looks one up."""
    converted = client.get("/api/expenses", params={"currency": "DKK"})
    assert converted.status_code == 200
    assert converted.content == client.get("/api/expenses").content


def test_a_converted_amount_is_a_string_not_a_number(client: TestClient) -> None:
    """167.56 must not arrive as 167.56 the JSON number. Conversion is Decimal
    arithmetic, and quantize is what keeps the trailing zero on a round result."""
    body = _EXPENSES.validate_json(
        client.get("/api/expenses", params={"currency": "EUR"}).content
    )
    assert [row.amount for row in body] == ["167.56", "103.94"]


def test_a_currency_with_no_loaded_rate_is_refused(client: TestClient) -> None:
    """422 for the whole request rather than a list mixing converted and unconverted
    amounts, which is a column nobody can add up."""
    response = client.get("/api/expenses", params={"currency": "CHF"})
    assert response.status_code == 422
    assert response.json() == {"detail": "no exchange rate from DKK to CHF"}
    # A registered handler runs inside the middleware, so a 422 is decorated too.
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("value", ["euro", "eur", ""])
def test_a_currency_that_is_not_an_iso_4217_code_is_refused(
    client: TestClient, value: str
) -> None:
    """The same plain-string detail as the missing-rate 422, rather than FastAPI's
    list-shaped validation body: one endpoint, one error shape."""
    response = client.get("/api/expenses", params={"currency": value})
    assert response.status_code == 422
    assert response.json() == {"detail": "currency must be an ISO 4217 code"}


def test_nothing_loaded_is_still_an_empty_list_under_a_currency(
    empty_expenses_client: TestClient,
) -> None:
    """No rows means no rate is needed, so the empty state survives ?currency."""
    response = empty_expenses_client.get("/api/expenses", params={"currency": "EUR"})
    assert response.status_code == 200
    assert _EXPENSES.validate_json(response.content) == []


def test_no_loaded_rates_refuses_a_conversion(
    empty_currencies_client: TestClient,
) -> None:
    """An empty currency_rate table answers 200 [] on its own endpoint, but it cannot
    convert anything - and the bare request is unaffected."""
    response = empty_currencies_client.get("/api/expenses", params={"currency": "EUR"})
    assert response.status_code == 422
    assert response.json() == {"detail": "no exchange rate from DKK to EUR"}
    assert empty_currencies_client.get("/api/expenses").status_code == 200


def test_a_date_range_is_handed_to_the_repository_as_dates(
    client: TestClient, requested_bounds: _Bounds
) -> None:
    """Filtering is the repository's job, done in SQL, so what the route owes is two
    parsed dates and nothing else."""
    response = client.get(
        "/api/expenses", params={"from_date": "2026-01-01", "to_date": "2026-01-31"}
    )
    assert response.status_code == 200
    assert requested_bounds == [(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))]


def test_either_bound_may_be_given_on_its_own(
    client: TestClient, requested_bounds: _Bounds
) -> None:
    """The bound left out is open, not defaulted: None is what adds no clause."""
    first = client.get("/api/expenses", params={"from_date": "2026-01-01"})
    second = client.get("/api/expenses", params={"to_date": "2026-01-31"})
    assert (first.status_code, second.status_code) == (200, 200)
    assert requested_bounds == [
        (datetime.date(2026, 1, 1), None),
        (None, datetime.date(2026, 1, 31)),
    ]


def test_asking_for_no_range_is_the_request_that_was_there_before(
    client: TestClient, requested_bounds: _Bounds
) -> None:
    """Both bounds absent reaches the repository as no bounds at all, so a client that
    does not ask sees exactly what it saw before."""
    response = client.get("/api/expenses")
    assert response.status_code == 200
    assert requested_bounds == [(None, None)]


@pytest.mark.parametrize("value", ["", "yesterday", "20260102", "02/01/2026"])
def test_a_from_date_that_is_not_a_date_is_refused(
    client: TestClient, value: str
) -> None:
    """The same plain-string detail as the currency refusals, rather than FastAPI's
    list-shaped validation body: one endpoint, one error shape."""
    response = client.get("/api/expenses", params={"from_date": value})
    assert response.status_code == 422
    assert response.json() == {"detail": "from_date must be a date in YYYY-MM-DD form"}
    # A registered handler runs inside the middleware, so a 422 is decorated too.
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_a_to_date_that_is_not_a_date_is_refused(client: TestClient) -> None:
    """The message names the parameter, so a client knows which of the two to fix."""
    response = client.get("/api/expenses", params={"to_date": "yesterday"})
    assert response.status_code == 422
    assert response.json() == {"detail": "to_date must be a date in YYYY-MM-DD form"}


def test_a_range_that_ends_before_it_begins_is_refused(
    client: TestClient, requested_bounds: _Bounds
) -> None:
    """Refused rather than answered with an empty list, and refused before the query:
    a 200 would read as "no expenses then" for a range nobody can have meant."""
    response = client.get(
        "/api/expenses", params={"from_date": "2026-03-01", "to_date": "2026-01-01"}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "from_date must not be after to_date"}
    assert requested_bounds == []


def test_a_range_is_applied_before_the_amounts_are_converted(
    client: TestClient, requested_bounds: _Bounds
) -> None:
    """The two parameters compose, and the range is what the conversion runs over - so
    an expense outside it needs no rate."""
    response = client.get(
        "/api/expenses",
        params={"from_date": "2026-01-01", "to_date": "2026-12-31", "currency": "EUR"},
    )
    assert response.status_code == 200
    assert requested_bounds == [
        (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
    ]
    assert [item.currency for item in _EXPENSES.validate_json(response.content)] == [
        "EUR",
        "EUR",
    ]


def test_currencies_endpoint_returns_json(
    client: TestClient, currency_records: list[CurrencyRateRecord]
) -> None:
    response = client.get("/api/currencies")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["Cache-Control"] == "no-store"
    assert _CURRENCIES.validate_json(response.content) == [
        CurrencyPayload(
            from_currency="DKK", to_currency="EUR", exchange_rate="0.134048"
        ),
        CurrencyPayload(
            from_currency="EUR", to_currency="DKK", exchange_rate="7.460000"
        ),
    ]
    # The fixture is the other half of that literal; if it changes, this should fail
    # rather than quietly assert against itself.
    assert len(currency_records) == 2


def test_exchange_rates_are_strings_not_numbers(client: TestClient) -> None:
    """7.460000 must not arrive as 7.46.

    CurrencyPayload types exchange_rate as str, so a route that emitted a JSON number
    fails to parse here rather than passing with a drifted value.
    """
    body = _CURRENCIES.validate_json(client.get("/api/currencies").content)
    assert [row.exchange_rate for row in body] == ["0.134048", "7.460000"]


def test_currencies_endpoint_preserves_the_repository_order(client: TestClient) -> None:
    """Ordering belongs to the repository here too, so this fails if the route sorts."""
    body = _CURRENCIES.validate_json(client.get("/api/currencies").content)
    assert [row.from_currency for row in body] == ["DKK", "EUR"]


def test_currencies_endpoint_returns_an_empty_list_when_nothing_is_loaded(
    empty_currencies_client: TestClient,
) -> None:
    """200 and [], for the reason the expenses twin above gives."""
    response = empty_currencies_client.get("/api/currencies")
    assert response.status_code == 200
    assert _CURRENCIES.validate_json(response.content) == []


def test_currencies_are_unavailable_when_the_database_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real dependency, against a port that refuses instantly.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nobody@127.0.0.1:1/none")
    with TestClient(create_app()) as client:
        response = client.get("/api/currencies")
    assert response.status_code == 503
    # Its own detail: a client learns which endpoint failed and nothing more.
    assert response.json() == {"detail": "currencies unavailable"}


def test_expenses_are_unavailable_when_the_database_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real dependency this time, not the fake, against a port that refuses
    # instantly. Context-managed on purpose: that is what runs the lifespan and builds
    # the engine.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nobody@127.0.0.1:1/none")
    with TestClient(create_app()) as client:
        response = client.get("/api/expenses")
    assert response.status_code == 503
    assert response.json() == {"detail": "expenses unavailable"}
    # An error response is still decorated by the security-headers middleware.
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """The environment with every database setting removed.

    Handed back so a test can set what it reads. Whatever launched pytest exported these
    - poe does, from backend/.env - and none of it should reach a settings assertion.
    """
    for name in ("DATABASE_URL", "PGUSER", "PGHOST", "PGPORT", "PGDATABASE"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _set(env: pytest.MonkeyPatch, **values: str) -> None:
    """Exports each value under its upper-cased name, as the app reads it."""
    for name, value in values.items():
        env.setenv(name.upper(), value)


def test_the_dsn_is_composed_from_the_connection_settings(
    clean_env: pytest.MonkeyPatch,
) -> None:
    _set(
        clean_env,
        pguser="someone",
        pghost="10.0.0.1",
        pgport="6000",
        pgdatabase="somewhere",
    )
    assert config.DatabaseSettings().dsn.render_as_string() == (
        "postgresql+asyncpg://someone@10.0.0.1:6000/somewhere"
    )


def test_dsn_parts_needing_escaping_are_encoded_not_interpolated(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """A username carrying @ is escaped rather than emitted raw.

    Interpolating it would put a second @ in the authority and produce a URL that parses
    as a different host, so the round-trip is the assertion that matters.
    """
    _set(
        clean_env,
        pguser="user@corp",
        pghost="10.0.0.1",
        pgport="6000",
        pgdatabase="somewhere",
    )
    rendered = config.DatabaseSettings().dsn.render_as_string()
    assert "user%40corp" in rendered
    assert make_url(rendered).username == "user@corp"
    assert make_url(rendered).host == "10.0.0.1"


def test_a_password_is_redacted_when_the_dsn_is_rendered(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """What stops a deployment's credential reaching a log or a traceback."""
    _set(
        clean_env,
        database_url="postgresql+asyncpg://someone:s3cret@10.0.0.1:6000/somewhere",
    )
    dsn = config.DatabaseSettings().dsn
    assert "s3cret" not in str(dsn)
    assert "s3cret" not in repr(dsn)
    assert dsn.password == "s3cret"


def test_database_url_overrides_the_connection_settings(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Whole-DSN override, not a default: what a deployment is handed wins over the
    parts, which is why this still sets one of them."""
    _set(
        clean_env,
        database_url="postgresql+asyncpg://nobody@127.0.0.1:1/none",
        pgport="6000",
    )
    assert (
        config.DatabaseSettings().dsn.render_as_string()
        == "postgresql+asyncpg://nobody@127.0.0.1:1/none"
    )


def test_a_non_numeric_port_is_refused(clean_env: pytest.MonkeyPatch) -> None:
    _set(
        clean_env,
        pguser="someone",
        pghost="10.0.0.1",
        pgport="not-a-port",
        pgdatabase="somewhere",
    )
    with pytest.raises(ValidationError):
        _ = config.DatabaseSettings()


@pytest.mark.usefixtures("clean_env")
def test_missing_database_settings_are_refused_at_startup() -> None:
    # No silent default: a deployment that forgets the settings fails to boot rather
    # than dialling its own loopback. Nothing on disk can answer for them either - the
    # app reads the environment and opens no file - so an empty environment is the whole
    # of the case, in every pixi environment rather than only in prod.
    with pytest.raises(ValidationError, match="PGUSER"), TestClient(create_app()):
        pass
