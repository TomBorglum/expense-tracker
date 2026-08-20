from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from .currency_repository import CurrenciesUnavailableError, CurrencyRepository
from .deps import lifespan, provide_currency_repository, provide_expense_repository
from .expense_repository import ExpenseRepository, ExpensesUnavailableError

# Applied to every response. This app serves JSON and nothing else, so the policy
# grants nothing at all.
_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


class ExpensePayload(BaseModel):
    """One expense as GET /api/expenses sends it.

    Every field is a string, amount included: JSON has no decimal type, so a float
    round trip is how a total drifts by a cent. These are the wire types, which is
    what lets the tests parse a response back into this class.
    """

    amount: str
    currency: str
    date: str
    category: str
    details: str


class CurrencyPayload(BaseModel):
    """One exchange rate as GET /api/currencies sends it.

    Every field is a string here too, for the reason ExpensePayload gives: an amount
    multiplied by a rate that made a float round trip is an amount that has drifted.
    """

    from_currency: str
    to_currency: str
    exchange_rate: str


def create_app() -> FastAPI:
    # No OpenAPI schema and no docs routes: /docs, /redoc and /openapi.json would be
    # public surface for two hand-written routes.
    #
    # The lifespan is what opens the connection pool, so building an app touches no
    # socket and reads no environment. `uvicorn --factory` and the HTTP suite rely on
    # that.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    # Registered before the CORS middleware below, which makes it the inner of the two.
    @app.middleware("http")
    async def add_security_headers(  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            # `_ =` because setdefault returns the existing value and we have no use
            # for it; reportUnusedCallResult wants that said out loud.
            _ = response.headers.setdefault(header, value)
        return response

    # Read-only: rows arrive through `pixi run backend-load-expenses` and nowhere
    # else, so there is no POST, PUT or DELETE.
    @app.get("/api/expenses")
    async def expenses(  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        expenses: Annotated[ExpenseRepository, Depends(provide_expense_repository)],
    ) -> JSONResponse:
        payload = [
            ExpensePayload(
                # str(), never float(): the column is numeric(12, 2) and arrives as a
                # Decimal.
                amount=str(record.amount),
                currency=record.currency,
                date=record.expense_date.isoformat(),
                category=record.category,
                details=record.details,
            )
            # The repository's order, reproduced untouched. Sorting again here would
            # hide a repository that stopped sorting.
            for record in await expenses.list_expenses()
        ]
        return JSONResponse(
            [item.model_dump() for item in payload],
            headers={"Cache-Control": "no-store"},
        )

    # Read-only: rates arrive through `pixi run backend-load-currencies` and nowhere
    # else.
    @app.get("/api/currencies")
    async def currencies(  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        currencies: Annotated[CurrencyRepository, Depends(provide_currency_repository)],
    ) -> JSONResponse:
        payload = [
            CurrencyPayload(
                from_currency=record.from_currency,
                to_currency=record.to_currency,
                # str(), never float(): the column is numeric(18, 6) and arrives as a
                # Decimal.
                exchange_rate=str(record.exchange_rate),
            )
            # The repository's order, reproduced untouched.
            for record in await currencies.list_currencies()
        ]
        return JSONResponse(
            [item.model_dump() for item in payload],
            headers={"Cache-Control": "no-store"},
        )

    # The only place a repository failure becomes an HTTP status, which is what lets
    # the repository module stay free of fastapi. Registered handlers run inside the
    # middleware above, so this response still collects the security headers.
    @app.exception_handler(ExpensesUnavailableError)
    async def handle_expenses_unavailable(  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        _request: Request, _exc: Exception
    ) -> JSONResponse:
        # Neither argument is used: the detail is the same either way, so a client
        # learns nothing about the database from a failure. An empty table is not this
        # case at all: it answers 200 with [].
        return JSONResponse({"detail": "expenses unavailable"}, status_code=503)

    @app.exception_handler(CurrenciesUnavailableError)
    async def handle_currencies_unavailable(  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        _request: Request, _exc: Exception
    ) -> JSONResponse:
        # The expenses handler's twin, and separate for the same reason the
        # repositories are: neither endpoint learns anything from the other's failure.
        return JSONResponse({"detail": "currencies unavailable"}, status_code=503)

    # Added last, so it is the outermost middleware and can answer a preflight itself
    # instead of passing OPTIONS to a router that has no such route.
    #
    # Open to every origin because the frontend is served from its own dev server.
    # allow_credentials must stay False while the origin is a wildcard - the CORS spec
    # forbids the pair - so the day this API grows cookies or an Authorization header,
    # the wildcard is what has to become a real origin list.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app
