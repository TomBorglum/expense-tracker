---
paths:
  - "backend/**"
  - "pixi.toml"
---

# Backend rules

Break one of these and CI goes red on an otherwise correct change.

## The HTTP surface

- **The backend serves no frontend.** Its whole surface is `GET /api/greeting` and
  `GET /api/expenses`: no `/` route, no `StaticFiles` mount, no build artifact under
  `backend/`. Pinned by `test_root_is_not_served`, `test_static_files_are_not_served`
  and `test_unknown_api_routes_404`.
- **Expenses are read-only over HTTP.** Rows arrive through
  `pixi run backend-load-expenses` and nowhere else, so there is no POST, PUT or DELETE
  and no plan for one. The database is a view of the files in `backend/data/expenses/`,
  which are `*.tsv`: tab-separated, five named columns, dates `DD/MM/YYYY`. No test
  fails if you add a write route, which is why this is written down.
- **No OpenAPI.** `docs_url`, `redoc_url` and `openapi_url` stay `None` in
  `create_app()`. Pinned by `test_openapi_docs_are_disabled`.
- **CORS is wildcard with `allow_credentials=False`.** The spec forbids the pair, so
  the day the API grows cookies or an `Authorization` header the wildcard is what has
  to become a real origin list. Pinned by `test_cors_does_not_allow_credentials`. It is
  registered after the security-headers middleware, which makes it outermost and lets
  it answer preflights itself.
- **`create_app()` opens no socket.** The engine is built by the lifespan in `deps.py`,
  not by the factory, which is what keeps `TestClient(app)` (without `with`)
  database-free and `uvicorn --factory` working. Moving engine creation into
  `create_app()` breaks the entire HTTP suite.
- **An empty `expense` table is 200 with `[]`, not 503.** Deliberately asymmetric with
  the greeting, whose missing row *is* a fault because exactly one row is required. A
  database nobody has run the loader against yet is a legitimate state, and a 503 would
  train a client to retry forever against a server that is working perfectly. So
  `PostgresExpenseRepository` raises only from its `except` arm, with no
  `if not rows: raise` counterpart. Pinned by
  `test_expenses_endpoint_returns_an_empty_list_when_nothing_is_loaded` in `test_app.py`
  and `test_the_endpoint_returns_an_empty_list_when_nothing_is_loaded` in
  `test_expense_postgres.py`.

## Module layering

- **Only `deps.py` imports fastapi, and nothing imports `deps`.** The wiring points one
  way: `deps.py` imports `greeting_repository` and `expense_repository`, never the
  reverse, and those two plus `db.py`, `config.py` and `expense_loader.py` know no HTTP
  at all. A failed read leaves the repository as `GreetingUnavailableError` or
  `ExpensesUnavailableError`, and the handlers registered in `create_app()` are the only
  place that turn them into a 503. Putting an `HTTPException` back in a repository is
  what this split exists to prevent.
- A **new module** under `src/expense_tracker/` has to be added to **three** lists, not
  one: the `layers` contract (where `exhaustive = true` fails the gate by itself), and
  the `source_modules` of *both* `forbidden` contracts - a `forbidden` contract has no
  `exhaustive` option, so an unnamed module is silently uncovered by them.
- In a layer list `|` joins siblings that may **not** import each other and `:` joins
  siblings that **may**. The two are easy to transpose and only one of them enforces
  anything.
- **`db.py` holds `Base` and nothing else.** Both repository modules need one shared
  `DeclarativeBase`, and giving it a module of its own is what keeps them from importing
  each other - which the `expense_repository | greeting_repository` layer forbids. A new
  model goes in the repository module that reads it, not in `db.py`.

## Repositories

- **Every repository subclasses its ABC and carries `@override`** - the two Postgres
  ones, and `_FakeGreetingRepository` and `_FakeExpenseRepository` in `conftest.py`; a
  new implementation or test double does too. It has to be enforced somewhere, because
  `dependency_overrides` is an untyped dict that would otherwise accept a look-alike
  matching the shape without inheriting.
- Keep an `@abstractmethod` body a same-line `...`. `raise NotImplementedError` would be
  a statement coverage counts and nothing executes.

## Tests

- **The HTTP suite never touches PostgreSQL.** `tests/conftest.py` overrides both the
  `provide_greeting_repository` and `provide_expense_repository` dependencies with fake
  repositories; only `test_greeting_postgres.py` and `test_expense_postgres.py`, behind
  the registered `postgres` marker, connect. A new test that hits an endpoint takes the
  `client` fixture. Those modules skip when no server answers and **fail** under
  `CI=true`, so a database that did not come up cannot go green.
  `test_expense_postgres.py` TRUNCATEs both expense tables before and after every test,
  so running the suite empties a developer's loaded data -
  `pixi run backend-load-expenses` puts it back.

## Database and configuration

- **`backend/schema.sql` is the only DDL.** No Alembic, no `Base.metadata.create_all`,
  and every statement in it stays idempotent because `db-init` re-runs against live
  clusters. The loader issues DML only. New tables use `GENERATED ALWAYS AS IDENTITY`,
  not `serial`/`bigserial`, which PostgreSQL's own "Don't Do This" page advises against
  for new applications. `IF NOT EXISTS` adds what is missing but never renames or
  alters, so a change to an existing table means `backend-db-reset` and a reload, not
  another `db-init`.
- **The app reads the environment; loading `backend/.env` is a launcher's job.**
  `config.py` opens no file and resolves no path - no `__file__`, no `env_file=`, no
  `parents[N]`. Reintroducing dotenv reading into the package is the specific regression
  this rule exists to prevent: a wheel-installed package has no project directory to
  derive a path from, so the code either finds nothing or finds a developer's settings,
  depending on how it happened to be installed. There is **no `.env.local` layer** - one
  file, loaded once - and a dotenv **overwrites** the ambient environment, so
  `export PGPORT=...` is not an override; moving the cluster off a taken port means
  editing `backend/.env` and rebuilding. `direnv allow` is what supplies those names;
  see `CLAUDE.md`.
- **`backend/.env` is the single source of the connection settings**, and **the DSN is
  stored nowhere**: `DatabaseSettings.dsn` builds it with `sqlalchemy.URL`, which stops
  the port being written into a URL string a second time and escapes parts containing
  `@`, `:` or `/`. `DATABASE_URL` overrides the four wholesale. Do not reintroduce a
  literal DSN in any manifest, and do not go back to f-string interpolation.
- **`database_url()` returns a `URL`, not a `str`.** `str()` and `repr()` of it redact
  the password as `***`, which is what stops a deployment credential reaching a log or a
  traceback; a `str` return would silently give that up. `create_async_engine` and
  `load_directory` both take the `URL` unchanged.
- **Nothing here falls back to port 5432.** `config.py` refuses to start without its
  settings (`_needs_a_source`), and `db-create` and `db-init` open with a
  `: "${PGPORT:?...}"` guard for the same reason: initdb, psql and createdb each default
  to 5432 and the OS username on their own, so a task that lost the four names would
  reach whatever cluster answers there - applying `schema.sql` to it and reporting
  success - instead of failing. Any new task that reaches a server without passing
  `--port` explicitly takes the guard too. The three `pg_ctl` tasks do not need it: the
  port is baked into `.pgdata/postgresql.conf` by `db-create`, not passed at launch.
- **The dev server's port is `UVICORN_PORT` in `backend/.env`, and `dev` passes no
  `--port`.** uvicorn's CLI carries
  `context_settings={"auto_envvar_prefix": "UVICORN"}`, so it resolves `--port` from
  that name itself, the same shape as `PGHOST` and `psql`. Not a connection setting -
  `DatabaseSettings` never sees it. It takes **no `${UVICORN_PORT:?}` guard**, unlike
  the db tasks: a lost name makes uvicorn *bind* 8000 rather than silently *reach* the
  wrong server, and `dev` aborts on the `${PGPORT:?}` behind it first.

## Packaging

- **`prod` installs the app as a wheel; `[feature.dev.pypi-dependencies]` holds the only
  editable install**, folded in by the `default` environment. That split is why
  `[dependencies]` holds runtime *libraries* and not the app: an editable install is a
  redirect to `backend/src`, so it would ship `backend/tests/` and `backend/data/` and
  pin a container to a directory layout rather than an artifact. **No correctness
  property rests on this** - the app reads the environment either way, so a
  misconfigured process refuses to start in both. It is about shipping the right thing,
  and `pixi run -e prod` is the check (`README.md`, "Environments").

## Quality gates

- **Python:** basedpyright in `recommended` mode, which sets `failOnWarnings` so a
  warning fails `backend-typecheck` like an error, and ruff with
  `select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]`. Both in `backend/pyproject.toml`;
  there is no config file at the repo root and no Python setting duplicated in the
  editor config.
- **Module layering:** import-linter, `[tool.importlinter]` in the same file, run by
  `pixi run backend-lint` as the second half of that task. Imports are just another
  artifact to lint, so they get no gate of their own; `lint-fix` is ruff alone, because
  where a new module belongs in the layer order is a design decision, not a mechanical
  edit. Four contracts: the three-tier `deps | expense_loader` above
  `expense_repository | greeting_repository` above `db | config` layering, the
  fastapi/starlette ban on everything but `deps`, a ban on importing the package root,
  and `acyclic_siblings` for cycles at any depth. ruff cannot cover this - `TID251` bans
  a name project-wide rather than per-module, and ruff builds no cross-module graph, so
  it detects no cycles.
