# backend/CLAUDE.md

Invariants for the backend stack. Repo-wide rules - branching, ASCII-only, version
pinning, the command layers and the gate sequence - are in the root
[`CLAUDE.md`](../CLAUDE.md).

Break one of these and CI goes red on an otherwise correct change.

## The HTTP surface

- **The backend serves no frontend.** It is a REST API whose whole surface is
  `GET /api/expenses` and `GET /api/currencies`: no `/` route, no `StaticFiles` mount, no
  build artifact under `backend/`. Pinned by `test_root_is_not_served`,
  `test_static_files_are_not_served` and `test_unknown_api_routes_404`.
- **Both endpoints are read-only over HTTP.** Rows arrive through
  `pixi run backend-load-expenses` and `pixi run backend-load-currencies` and nowhere
  else, so there is no POST, PUT or DELETE and no plan for one. The database is a view of
  the files in `data/expenses/` and `data/currencies/`, which are `*.tsv`: tab-separated,
  named columns checked strictly, expense dates `DD/MM/YYYY`.
- **No OpenAPI.** `docs_url`, `redoc_url` and `openapi_url` stay `None` in `create_app()`.
  Pinned by `test_openapi_docs_are_disabled`.
- **CORS is wildcard with `allow_credentials=False`.** The spec forbids the pair, so the
  day the API grows cookies or an `Authorization` header the wildcard is what has to
  become a real origin list. Pinned by `test_cors_does_not_allow_credentials`. It is
  registered after the security-headers middleware, which makes it outermost and lets it
  answer preflights itself.
- **`create_app()` opens no socket.** The engine is built by the lifespan in
  `src/expense_tracker/deps.py`, not by the factory, which is what keeps
  `TestClient(app)` (without `with`) database-free and `uvicorn --factory` working. Moving
  engine creation into `create_app()` breaks the entire HTTP suite.
- **An empty `expense` table is 200 with `[]`, not 503.** A database nobody has run the
  loader against yet is a legitimate state and not a fault, and a 503 would train a client
  to retry forever against a server that is working perfectly. So
  `PostgresExpenseRepository` raises only from its `except` arm, with no
  `if not rows: raise` counterpart. Pinned by
  `test_expenses_endpoint_returns_an_empty_list_when_nothing_is_loaded` in `test_app.py`
  and `test_the_endpoint_returns_an_empty_list_when_nothing_is_loaded` in
  `test_expense_postgres.py`, and by the `currencies` twins of both -
  `PostgresCurrencyRepository` keeps the same shape. The frontend keeps its half of that
  asymmetry; see [`frontend/CLAUDE.md`](../frontend/CLAUDE.md).
- **`amount` goes out as `str(Decimal)`**, precisely so no float round trip can drift a
  total by a cent, and `date` as a bare `YYYY-MM-DD`. Pinned by
  `test_expense_amounts_are_strings_not_numbers` and
  `test_exchange_rates_are_strings_not_numbers`. The frontend renders both verbatim for
  reasons in its own file.

## Module layering

- **Only `deps.py` imports fastapi, and nothing imports `deps`.** The wiring points one
  way: `deps.py` imports the two repository modules, never the reverse, and those plus
  `db.py`, `config.py` and the two loaders know no HTTP at all. A failed read leaves the
  repository as `ExpensesUnavailableError` or `CurrenciesUnavailableError`, and the two
  handlers registered in `create_app()` are the only place that turn them into a 503.
  Putting an `HTTPException` back in a repository is what this split exists to prevent.
  Pinned by the import-linter contracts in `pyproject.toml`, not by a test.
- **A new module under `src/expense_tracker/` goes in three lists, not one:** the `layers`
  contract (where `exhaustive = true` fails the gate by itself), and the `source_modules`
  of *both* `forbidden` contracts - a `forbidden` contract has no `exhaustive` option, so
  an unnamed module is silently uncovered by them.
- **`db.py` holds `Base` and nothing else.** Every repository module needs the same
  `DeclarativeBase`, and giving it a module of its own is what lets a second one arrive
  without importing the first - which the `|` between siblings in a layer forbids.
  `currency_repository.py` is that second one, and it imports `Base` from `db`, never from
  `expense_repository`. A new model goes in the repository module that reads it, not in
  `db.py`.
- **Every repository subclasses its ABC and carries `@override`.**
  `PostgresExpenseRepository` and `PostgresCurrencyRepository`, and the two fakes in
  `tests/conftest.py`, all do; a new implementation or test double does too. The base class
  is an `ABC`, so this is enforced, not a convention - a look-alike that matches the shape
  without inheriting is rejected. It has to be enforced somewhere, because
  `dependency_overrides` is an untyped dict and would accept anything.
- **`@abstractmethod` on each repository ABC is load-bearing.** Without it the `...` body
  is an ordinary method returning `None` and an empty subclass passes. Removing it fails
  `pixi run backend-lint` three ways: `B027` on the method, `B024` on the class, `F401` on
  the unused import. That gate is why no test asserts it. Keep the body a same-line `...`;
  `raise NotImplementedError` would be a statement coverage counts and nothing executes.

## The loaders

- **The two loaders differ on reloading, and that difference is the design.**
  `expense_loader` is append-only: the `loaded_expense_file` ledger skips a file whose
  sha256 matches and *refuses* one that changed, because two identical expense lines are
  two real purchases and nothing in a row says whether it has been loaded before.
  `currency_loader` has no ledger and replaces the whole `currency_rate` table on every
  run, because a rate for a pair is a current fact rather than an event - so editing
  `data/currencies/rates.tsv` and reloading is the supported workflow, not the refused one.
  It parses every file before it deletes anything, so a typo leaves the loaded rates
  untouched, and the delete and the insert share one transaction. Pinned by
  `test_an_edited_rate_replaces_the_old_one` and
  `test_a_bad_file_leaves_the_loaded_rates_intact`.

## Conversion

- **`?currency=` converts in `conversion.py`, and refuses rather than approximates.** The
  module is pure - it takes `ExpenseRecord`s and `CurrencyRateRecord`s and returns
  `ExpenseRecord`s, so `amount` and `currency` are replaced in place and the payload shape
  is the same with the parameter as without it. That is what keeps the payload half of the
  frontend out of this: the `Expense` interface and its guard are untouched, and only the
  request URL and the query key gained the parameter.
- **Four refusals are the design, not gaps to fill in later.** A rate is used **only** in
  the direction `data/currencies/rates.tsv` states it, never inverted and never composed
  through a third currency. A pair loaded twice is refused rather than picked between, and
  only when that pair is needed, so an unrelated duplicate refuses nothing. One
  unconvertible expense refuses the **whole** request, because a list mixing converted and
  unconverted amounts is a column nobody can add up. A code that is not `\A[A-Z]{3}\Z` is
  refused rather than uppercased, matching the loaders.
- **The identity is the one thing it does not refuse:** `record.currency == target`
  returns the record before any lookup, which is why no `DKK DKK 1.000000` row exists.
- **Arithmetic is `Decimal` throughout**, `quantize(Decimal("0.01"),
  rounding=ROUND_HALF_UP)` - spelled out because `Decimal` rounds half to **even** by
  default.
- **`ConversionError` is the repositories' pattern reused:** the module knows no status
  code, and the handler in `create_app()` is the only place it becomes a 422. That handler
  reads its exception, unlike the two 503s, because the message is about the client's own
  input and names nothing of the database.
- **`conversion.py` took a layer of its own.** It imports both repository modules, so it
  sits over them, and the entry points may import it, so it sits under them; a `|` sibling
  of `deps` could be neither.

## Database and configuration

- **The HTTP suite never touches PostgreSQL.** `tests/conftest.py` overrides the
  `provide_expense_repository` and `provide_currency_repository` dependencies with fake
  repositories; only `test_expense_postgres.py` and `test_currency_postgres.py`, behind the
  registered `postgres` marker, connect. A new test that hits an endpoint takes the
  `client` fixture. Those modules skip when no server answers and **fail** under `CI=true`,
  so a database that did not come up cannot go green. They TRUNCATE the tables they read
  before and after every test, so running the suite empties a developer's loaded data -
  `pixi run backend-load-expenses` and `pixi run backend-load-currencies` put it back.
- **`schema.sql` is the only DDL.** No Alembic, no `Base.metadata.create_all`, and every
  statement in it stays idempotent because `db-init` re-runs against live clusters. The
  loader issues DML only. New tables use `GENERATED ALWAYS AS IDENTITY`, not
  `serial`/`bigserial`, which PostgreSQL's own "Don't Do This" page advises against for new
  applications. `IF NOT EXISTS` adds what is missing but never renames or alters, so a
  change to an existing table means `backend-db-reset` and a reload, not another `db-init`.
- **The app reads the environment; loading `.env` is a launcher's job.** `config.py` opens
  no file and resolves no path - no `__file__`, no `env_file=`, no `parents[N]`.
  Reintroducing dotenv reading into the package is the specific regression this rule exists
  to prevent: a wheel-installed package has no project directory to derive a path from, so
  the code either finds nothing or finds a developer's settings, depending on how it
  happened to be installed. direnv is the one launcher that puts those names there. There
  is **no `.env.local` layer** - one file, loaded once - and a dotenv **overwrites** the
  ambient environment, so `export PGPORT=...` is not an override; moving the cluster off a
  taken port means editing `.env` and rebuilding. `[tool.poe]` declares **no `envfile`**,
  and adding one back would be a second loader for one file.
- **CI is a cross-repo dependency, and that is the price of the single loader.**
  `setup-direnv` activates `.envrc` and then forwards the resulting environment to
  `$GITHUB_ENV`; that forwarding arrived in **v1.4.1**, and the pin in `ci.yml` is what
  every later `pixi run` depends on for those names. A `PGPORT` failure in CI means
  checking that pin first, before anything in this repo.
- **`.env` is the single source of the connection settings.** `PGHOST`, `PGPORT`, `PGUSER`
  and `PGDATABASE` live there and nowhere else - `pixi.toml` declares no
  `[activation.env]`, and that absence is deliberate rather than an omission. **The DSN is
  stored nowhere**: `DatabaseSettings.dsn` builds it with `sqlalchemy.URL`, which stops the
  port being written into a URL string a second time and escapes parts containing `@`, `:`
  or `/`. `DATABASE_URL` overrides the four wholesale. Do not reintroduce a literal DSN in
  any manifest, and do not go back to f-string interpolation.
- **`database_url()` returns a `URL`, not a `str`.** `str()` and `repr()` of it redact the
  password as `***`, which is what stops a deployment credential reaching a log or a
  traceback; a `str` return would silently give that up. `create_async_engine` and
  `load_directory` both take the `URL` unchanged.
- **The dev server's port is `UVICORN_PORT` in `.env`, and `dev` passes no `--port`.**
  uvicorn's CLI is a click command carrying
  `context_settings={"auto_envvar_prefix": "UVICORN"}`, so uvicorn itself resolves `--port`
  from that name - the same shape as `PGHOST` and `psql`, which is the whole reason the
  port belongs in that file rather than in a flag. It is not a connection setting:
  `DatabaseSettings` never sees it and `DATABASE_URL` has nothing to do with it. It also
  takes **no `${UVICORN_PORT:?}` guard**, unlike the db tasks: a lost name makes uvicorn
  *bind* 8000 rather than silently *reach* the wrong server, and `dev` aborts on the
  `${PGPORT:?}` in the `db-init` behind it before uvicorn is ever reached.
- **Nothing here falls back to port 5432.** `config.py` refuses to start without its
  settings (`_needs_a_source`), and `db-create` and `db-init` open with a
  `: "${PGPORT:?...}"` guard for the same reason: initdb, psql and createdb each default to
  5432 and the OS username on their own, so a task that lost the four names would reach
  whatever cluster answers there - applying `schema.sql` to it and reporting success -
  instead of failing. Any new task that reaches a server without passing `--port`
  explicitly takes the guard too. The `pg_ctl` tasks do not need it: the port is baked into
  `.pgdata/postgresql.conf` by `db-create`, not passed at launch.
- **`prod` installs the app as a wheel; only `default` installs it editable.** The two
  `[feature.*.pypi-dependencies]` blocks in `pixi.toml` are why `[dependencies]` holds
  runtime *libraries* and not the app. An editable install is a redirect to `src`, so it
  ships the source tree, `tests/` and `data/` and pins a container to a directory layout
  rather than an artifact. **No correctness property rests on this** - the app reads the
  environment either way, so a misconfigured process refuses to start in both environments.
  It is about shipping the right thing. Pinned by no test - `pixi run -e prod` is the
  check, described in [`README.md`](../README.md#environments).

## Quality gates

- **basedpyright in `recommended` mode and ruff** with
  `select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]`, both in `pyproject.toml`. There is
  no config file at the repo root and no Python setting duplicated in the editor config.
  `recommended` sets `failOnWarnings`, so a warning fails the build like an error.
- **Module layering is import-linter**, `[tool.importlinter]` in the same file, run by
  `pixi run backend-lint` as the second half of that task. Imports are just another
  artifact to lint, so they get no gate of their own; `lint-fix` is ruff alone, because
  where a new module belongs in the layer order is a design decision, not a mechanical
  edit. Four contracts: the layering (`deps | currency_loader | expense_loader` above
  `conversion` above `currency_repository | expense_repository` above `db | config`), the
  fastapi/starlette ban on everything but `deps`, a ban on importing the package root, and
  `acyclic_siblings` for cycles at any depth. In a layer list `|` joins siblings that may
  **not** import each other and `:` joins siblings that **may** - the two are easy to
  transpose and only one of them enforces anything. ruff cannot cover this: `TID251` bans a
  name project-wide rather than per-module, and ruff builds no cross-module graph, so it
  detects no cycles.
