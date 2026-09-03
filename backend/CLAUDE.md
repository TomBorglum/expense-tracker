# backend/CLAUDE.md

Invariants for the backend stack. Repo-wide rules and [what earns a place
here](../CLAUDE.md#adding-to-these-files) are in the root [`CLAUDE.md`](../CLAUDE.md).
**This file stays under 200 lines.** Break one of these and either CI goes red on an
otherwise correct change, or nothing does; each bullet says which.

## The HTTP surface

- **The backend serves no frontend and publishes no OpenAPI.** The whole surface is
  `GET /api/expenses`, `GET /api/expenses/totals` and `GET /api/currencies`: no `/` route,
  no `StaticFiles` mount, no build artifact, and `docs_url`, `redoc_url` and `openapi_url`
  stay `None`. Pinned by `test_root_is_not_served` and its three surface neighbours.
- **All three endpoints are read-only over HTTP.** Rows arrive through
  `backend-load-expenses` and `backend-load-currencies` and nowhere else, so there is no
  POST, PUT or DELETE. The tables are a view of `*.tsv` files from `$EXPENSE_DATA_DIR` and
  `data/currencies/`: columns checked strictly, dates `DD/MM/YYYY`. Nothing checks this.
- **CORS is wildcard with `allow_credentials=False`.** The spec forbids the pair, so the
  day the API grows cookies or an `Authorization` header the wildcard has to become a real
  origin list. It is registered outermost, after the security-headers middleware, so it
  answers preflights itself. Pinned by `test_cors_does_not_allow_credentials`.
- **`create_app()` opens no socket.** The engine is built by the lifespan in `deps.py`,
  which keeps `TestClient(app)` (without `with`) database-free and `uvicorn --factory`
  working. Moving engine creation into the factory breaks the entire HTTP suite.
- **An empty table is 200 with `[]`, not 503.** A database nobody has loaded yet is a
  legitimate state, and a 503 would train a client to retry forever against a working
  server, so both repositories raise only from their `except` arm. Pinned by
  `test_expenses_endpoint_returns_an_empty_list_when_nothing_is_loaded` and its twins.
- **`amount` goes out as `str(Decimal)`** so no float round trip can drift a total by a
  cent, and `date` as a bare `YYYY-MM-DD`. The frontend renders both verbatim. Pinned by
  `test_expense_amounts_are_strings_not_numbers` and its totals and rates twins.

## Module layering

- **Only the HTTP layer knows about HTTP.** `__init__.py` and `deps.py` are that layer;
  every other module imports no fastapi and no starlette. A failed read leaves a repository
  raising `ExpensesUnavailableError` or `CurrenciesUnavailableError`, which the
  `create_app()` handlers alone turn into a 503 - putting an `HTTPException` back in a
  repository is what this prevents. Pinned by the import-linter contracts, not by a test.
- **A new module goes in three lists, not one:** the `layers` contract, where
  `exhaustive = true` fails the gate by itself, and the `source_modules` of *both*
  `forbidden` contracts, which have no `exhaustive` option and so leave an unnamed module
  silently uncovered. The layer order lives in `[tool.importlinter]`; read it there.
- **Every refusal is a plain-string `detail`, and the module raising it knows no status
  code.** `ConversionError`, `DateRangeError` and `AggregationError` each become a 422 in a
  `create_app()` handler, as the repository errors become 503s, which is why the query
  parameters are typed `str` rather than `date` or `Literal`: a parameter FastAPI itself
  refuses answers with a list of errors instead. Only the 422 handlers read their
  exception, the message being about the client's own input.
- **`db.py` holds `Base` and nothing else.** A shared `DeclarativeBase` in its own module
  is what lets a second repository arrive without importing the first, which the `|`
  between siblings forbids. A new model goes in the repository module that reads it. Pinned
  by the layers contract.
- **Every repository subclasses its ABC and carries `@override`**, the two fakes in
  `tests/conftest.py` included, because `dependency_overrides` is an untyped dict that
  would accept a look-alike matching the shape without inheriting. Keep `@abstractmethod`
  and its same-line `...`: without it an empty subclass passes. Pinned by the `ABC`, and by
  ruff's `B027` and `B024`.

## The loaders

- **The two loaders differ on reloading, and that difference is the design.**
  `expense_loader` is append-only: the `loaded_expense_file` ledger skips a file whose
  sha256 matches and *refuses* one that changed, two identical expense lines being two real
  purchases. `currency_loader` has no ledger and replaces the whole `currency_rate` table
  every run, a rate being a current fact rather than an event, so editing `rates.tsv` and
  reloading is supported. It parses every file before deleting anything, in one
  transaction. Pinned by `test_an_edited_rate_replaces_the_old_one`.

## Conversion

- **`?currency=` converts in `conversion.py`, and four refusals are the design, not gaps to
  fill in later.** A rate is used **only** in the direction `rates.tsv` states it, never
  inverted, never composed through a third currency. A pair loaded twice is refused rather
  than picked between, and only when needed. One unconvertible expense refuses the
  **whole** request: a list mixing converted and unconverted amounts is a column nobody can
  add up. A code that is not `\A[A-Z]{3}\Z` is refused rather than uppercased. Pinned by
  the refusal tests in `test_conversion.py`.
- **The identity is the one thing it does not refuse:** `record.currency == target` returns
  the record before any lookup, which is why no `DKK DKK 1.000000` row exists. Pinned by
  `test_an_expense_already_in_the_target_currency_is_untouched`.
- **Arithmetic is `Decimal` throughout**,
  `quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)` - spelled out because `Decimal`
  rounds half to **even** by default. Pinned by
  `test_a_half_cent_rounds_up_rather_than_to_even`.

## Aggregation

- **`GET /api/expenses/totals` sums the rows `/api/expenses` lists**, grouped by
  `(period, currency, category)` - `currency` stays in the key whatever was asked for,
  because DKK added to EUR means nothing - and takes the same three query parameters. It
  adds **no repository method** - `list_expenses` is what it reads, so the fakes are
  untouched and the grouping needs no database. Pinned by
  `test_two_currencies_in_one_month_stay_two_totals`.
- **The conversion runs before the summing, and the order is the point.**
  `convert_expenses` quantizes to cents, so converting then adding differs by cents from
  adding then converting, and only the first makes a total equal what a reader adds up from
  `/api/expenses?currency=EUR`. That is what puts the summing in Python rather than a SQL
  `GROUP BY`. Pinned by `test_a_total_is_the_sum_of_the_rows_the_list_endpoint_shows`.
- **`period`, `from_date` and `to_date` are on every row; `amount`, `currency` and
  `category` only when they have a value** - never `null`, never `""`. `exclude_none=True`
  on the route dump is the whole rule, not `exclude_unset` - `_total_payload` sets all six
  fields. `?group_by=category` is what puts `category` in the key, and takes one value.
  Pinned by `test_totals_drop_the_category_key_when_it_was_not_grouped_by` and its
  neighbours, read as plain dicts because parsing proves nothing about a key's presence.
- **The response is a dense calendar: one row per period from the oldest matching expense
  to the newest**, spent in or not, and **absent is not `0.00`** - a month of refunds can
  net to zero. The extent is `min`/`max` over the records returned, so it relies on no
  ordering of the repository's. **Dense in periods only**: a date range has a defined
  universe of periods and categories do not. Pinned by
  `test_a_month_nobody_spent_in_is_still_a_row`.
- **A requested bound narrows a period only when it falls inside it**, which keeps
  `?from_date=2026-01-01` honoured as the 1st even when nothing was spent until the 7th.
  Load-bearing rather than an optimisation of an intersection: the fake filters nothing, so
  it *can* hand a March period a January range, and a plain `max`/`min` would end the span
  before it began. A period's `to_date` is inclusive, from `calendar.monthrange`. Pinned by
  `test_a_range_that_cannot_touch_a_period_leaves_it_whole` and
  `test_a_leap_february_ends_on_the_twenty_ninth`.
- **`?period=` is required and refuses rather than defaulting**, because a grain nobody
  chose is an assumption inside a sum. `month` is the only grain, which is why the payload
  field is the grain-neutral `period`. Pinned by `test_a_total_without_a_period_is_refused`
  and its unknown-grain twin.

## The date range

- **`?from_date=` and `?to_date=` filter in SQL, not in the route.** The `DateRange` goes
  to `list_expenses`, which adds one `>=` and one `<=` clause and only for the bounds that
  are set. Both ends are **inclusive** and each is open on its own; `None` adds no clause,
  so an absent parameter and an empty one are not the same request. Pinned by the four
  range tests in `test_expense_postgres.py`.
- **`DateRange` validates in `__post_init__`, so the repository does not.** The frozen
  dataclass refuses `start > end` at **every** construction, which lets `list_expenses`
  take the type and stop trusting its caller; checking again there would give one rule two
  homes. Pinned by `test_the_type_refuses_an_inverted_range_however_it_is_built`.
- **`\A\d{4}-\d{2}-\d{2}\Z` is the accepted form, and the only one.** `date.fromisoformat`
  also takes `20260102` and `2026-W01-1`, which this API never sends, so the regex refuses
  them before parsing, as `validate_currency_code` refuses a lowercase code rather than
  uppercasing it. Both bounds are read before either is compared, so an unreadable value is
  refused as itself. Pinned by
  `test_a_malformed_bound_is_refused_before_the_two_are_compared`.

## Database and configuration

- **The HTTP suite never touches PostgreSQL.** `tests/conftest.py` overrides both
  repository dependencies with fakes; only the two `*_postgres.py` modules, behind the
  registered `postgres` marker, connect, and a new test that hits an endpoint takes the
  `client` fixture. They skip when no server answers and **fail** under `CI=true`, so a
  database that did not come up cannot go green. They TRUNCATE what they read, so the suite
  empties a developer's loaded data and the loaders put it back.
- **`schema.sql` is the only DDL.** No Alembic, no `Base.metadata.create_all`, and every
  statement stays idempotent because `db-init` re-runs against live clusters. New tables
  use `GENERATED ALWAYS AS IDENTITY`, not `serial`, and `IF NOT EXISTS` never alters, so
  changing a table means `backend-db-reset` and a reload. Nothing checks this.
- **The app reads the environment; loading `.env` is a launcher's job.** `config.py` opens
  no file and resolves no path: no `__file__`, no `env_file=`, no `parents[N]`.
  Reintroducing dotenv reading is the regression this prevents: a wheel-installed package
  has no project directory to derive a path from. There is **no `.env.local` layer**, a
  dotenv **overwrites** the environment so `export PGPORT=...` is not an override, and
  `[tool.poe]` declares **no `envfile`**. Pinned by
  `test_missing_database_settings_are_refused_at_startup`.
- **CI is a cross-repo dependency, and that is the price of the single loader.**
  `setup-direnv` activates `.envrc` and forwards the result to `$GITHUB_ENV`, which every
  later `pixi run` depends on. A `PGPORT` failure in CI means checking that pin in
  `.github/workflows/ci.yml` first, before anything in this repo.
- **`.env` is the single source of the connection settings**, and `pixi.toml` declares no
  `[activation.env]` by design. **The DSN is stored nowhere**: `DatabaseSettings.dsn`
  builds it with `sqlalchemy.URL`, which stops the port being written into a URL string
  twice and escapes parts containing `@`, `:` or `/`. `DATABASE_URL` overrides the four
  wholesale. Do not reintroduce a literal DSN, or f-string interpolation.
- **`database_url()` returns a `URL`, not a `str`.** `str()` and `repr()` of it redact the
  password as `***`, which stops a deployment credential reaching a log or a traceback; a
  `str` return would silently give that up. Nothing checks this.
- **The dev server's port is `UVICORN_PORT` in `.env`, and `dev` passes no `--port`.**
  uvicorn's CLI carries `auto_envvar_prefix="UVICORN"`, so uvicorn resolves the flag
  itself. It takes **no `${UVICORN_PORT:?}` guard**, unlike the db tasks, because a lost
  name makes uvicorn *bind* 8000 rather than silently *reach* the wrong server. Pinned by
  `test_a_non_numeric_port_is_refused`.
- **Nothing here falls back to port 5432.** `config.py` refuses to start without its
  settings (`_needs_a_source`), and `db-create` and `db-init` open with a
  `: "${PGPORT:?...}"` guard: initdb, psql and createdb each default to 5432 and the OS
  username, so a task that lost those names would reach whatever cluster answers there and
  report success. Any new task reaching a server without an explicit `--port` takes the
  guard too; the `pg_ctl` tasks read the port from `.pgdata/postgresql.conf`.
- **`feature.prod` installs the app as a wheel; only `feature.dev` installs it editable.**
  An editable install ships the source tree, `tests/` and `data/`, and pins a container to
  a directory layout rather than an artifact. **No correctness property rests on this** -
  the app reads the environment either way. Pinned by no test; `pixi run -e prod` is the
  check, described in [`README.md`](../README.md#environments).

## Quality gates

- **basedpyright's `recommended` mode sets `failOnWarnings`**, which is what makes a
  warning fail the build like an error. It and ruff are configured in `pyproject.toml` and
  nowhere else.
- **Module layering is import-linter**, run by `backend-lint` as the second half of that
  task; `lint-fix` is ruff alone, because where a new module belongs in the layer order is
  a design decision, not a mechanical edit. In a layer list `|` joins siblings that may
  **not** import each other and `:` joins siblings that **may** - easy to transpose, and
  only one enforces anything. ruff builds no cross-module graph.
