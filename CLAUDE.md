# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Branch and merge rules

The rationale is in [`CONTRIBUTING.md`](CONTRIBUTING.md). This repo is on the GitHub
free plan, so none of this is enforced by GitHub - follow it as if it were.

- **Never push directly to `main`.** Every change goes on a branch, through a PR.
- **The PR title must be a valid Conventional Commit.** It becomes the squashed commit
  subject that release-please parses.
- **Squash-merge only**, keeping `main` linear. The one merge-commit exception is
  documented in `CONTRIBUTING.md`.
- **Before merging:** the `SonarCloud Code Analysis` check passes and every review
  thread is resolved.
- **Merge with `gh pr merge --squash --delete-branch`.**
- **Branch naming:** `<type>/<short-kebab-description>`, e.g. `feat/monthly-report`.

## Releases

Automated by release-please (`.github/workflows/release-please.yml`). **Never
hand-edit versions, git tags, or `CHANGELOG.md`.**

## Source conventions

- **ASCII-only** committed source: no em-dashes, smart quotes, arrows, ellipses. That
  includes the sample data under `backend/data/expenses/`. The loader decodes
  `utf-8-sig`, so a developer's own (uncommitted) exports carry Danish text and
  byte-order marks fine.
- **Comments say what the code does**, and only where that is not plain from reading it.
  No rationale essays, no rejected alternatives, no explaining why a module exists or
  where it sits in the layer order - that reasoning lives in this file and in
  `README.md`, and repeating it in the source gives one fact two places to drift apart.
  Module docstrings are one line; function docstrings are one line, and only where the
  name and signature do not already say it. This is about code, SQL and config comments;
  the prose in `README.md` and this file keeps its current density.
- **Pin versions exactly** - `==` in `pixi.toml`, in both its conda tables and
  `[feature.test.pypi-dependencies]`, bare versions in `frontend/package.json`, GitHub
  Actions by SHA with a version comment.
- **Every suppression carries a reason** beside the pragma: a comment next to
  `# pyright: ignore[...]` (see `backend/src/expense_tracker/__init__.py`), or on/above
  an `// eslint-disable-next-line <rule>`. A bare disable is not acceptable.

## Commands

**Commands live in two layers, and adding one means editing both.**

1. **The stack that runs it defines it**, in the manifest that already owns how its
   tools behave: poe tasks in `backend/pyproject.toml`, the `scripts` block in
   `frontend/package.json`. This is where the command body goes.
2. **`pixi.toml` forwards to it**, one prefixed one-liner per command, so `pixi run`
   stays the single entry point spanning both stacks.

`pixi run <task>` is what CI calls and what you should reach for. Every task declares
its own `cwd`, so it behaves identically wherever you invoke it. Full table in
[`README.md`](README.md#development-tasks).

The five `backend-db-*` tasks are no exception to either layer: their bodies are poe
tasks like the rest, and the cluster they drive is initdb'd into `backend/.pgdata/`,
addressed by a plain relative path like every other task in that file. poe runs a task
from the directory of the `pyproject.toml` it loaded, so that path holds however the task
was invoked - `cd backend && poe db-init`, `poe -C backend db-init` from anywhere, or the
pixi forwarder. Nothing in `backend/pyproject.toml` needs `$POE_ROOT`. That is the **path**
only: the connection settings come from direnv, so the same invocation from outside the
worktree resolves `.pgdata/` correctly and then aborts on the `${PGPORT:?}` guard.

**`dev` depends on `db-init`**, so `pixi run backend-dev` is the single command that gets a
backend developer a working API: the cluster chain behind it is idempotent, runs once
before uvicorn, and leaves the cluster up afterwards. Neither `load-expenses` nor
`load-currencies` is in that chain - an empty `expense` or `currency_rate` table is a
legitimate `200`, and putting a loader there would work around that invariant rather than
honour it. `test` stays out of that
chain, because "The HTTP suite never touches PostgreSQL" below is a property chaining
`db-init` onto it would hide.

**The delegation is uniform - every task in `pixi.toml` forwards, none defines.** Never
put a command body there; that is what would make the layer a place definitions hide.
Both stacks also stay runnable on their own terms (`cd backend && poe test`,
`cd frontend && pnpm build`), which is what keeps each directory a standalone project.

Before opening a PR, run the gate sequence from `.github/workflows/ci.yml`, in order
(cheapest first, so it fails fast):

```sh
pixi run backend-format-check && pixi run backend-lint &&
pixi run backend-typecheck && pixi run backend-db-init && pixi run backend-test &&
pixi run frontend-install && pixi run frontend-format-check &&
pixi run frontend-typecheck && pixi run frontend-lint && pixi run frontend-test &&
pixi run frontend-build
```

The two halves are independent, so a change to one stack can only fail that stack's
gates.

## Build invariants

Break one of these and CI goes red on an otherwise correct change.

- **The backend serves no frontend.** It is a REST API whose whole surface is
  `GET /api/expenses` and `GET /api/currencies`: no `/` route, no `StaticFiles` mount,
  no build artifact under `backend/`. Pinned by `test_root_is_not_served`,
  `test_static_files_are_not_served` and `test_unknown_api_routes_404`.
- **Both endpoints are read-only over HTTP.** Rows arrive through
  `pixi run backend-load-expenses` and `pixi run backend-load-currencies` and nowhere
  else, so there is no POST, PUT or DELETE and no plan for one. The database is a view of
  the files in `backend/data/expenses/` and `backend/data/currencies/`, which are
  `*.tsv`: tab-separated, named columns checked strictly, expense dates `DD/MM/YYYY`.
- **The two loaders differ on reloading, and that difference is the design.**
  `expense_loader` is append-only: the `loaded_expense_file` ledger skips a file whose
  sha256 matches and *refuses* one that changed, because two identical expense lines are
  two real purchases and nothing in a row says whether it has been loaded before.
  `currency_loader` has no ledger and replaces the whole `currency_rate` table on every
  run, because a rate for a pair is a current fact rather than an event - so editing
  `data/currencies/rates.tsv` and reloading is the supported workflow, not the refused
  one. It parses every file before it deletes anything, so a typo leaves the loaded rates
  untouched, and the delete and the insert share one transaction. Pinned by
  `test_an_edited_rate_replaces_the_old_one` and
  `test_a_bad_file_leaves_the_loaded_rates_intact`.
- **No OpenAPI.** `docs_url`, `redoc_url` and `openapi_url` stay `None` in
  `create_app()`. Pinned by `test_openapi_docs_are_disabled`.
- **CORS is wildcard with `allow_credentials=False`.** The spec forbids the pair, so
  the day the API grows cookies or an `Authorization` header the wildcard is what has
  to become a real origin list. Pinned by `test_cors_does_not_allow_credentials`. It
  is registered after the security-headers middleware, which makes it outermost and
  lets it answer preflights itself.
- **`create_app()` opens no socket.** The engine is built by the lifespan in
  `backend/src/expense_tracker/deps.py`, not by the factory, which is what keeps
  `TestClient(app)` (without `with`) database-free and `uvicorn --factory` working.
  Moving engine creation into `create_app()` breaks the entire HTTP suite.
- **Only `deps.py` imports fastapi, and nothing imports `deps`.** The wiring points one
  way: `deps.py` imports the two repository modules, never the reverse, and those plus
  `db.py`, `config.py` and the two loaders know no HTTP at all. A failed read leaves the
  repository as `ExpensesUnavailableError` or `CurrenciesUnavailableError`, and the two
  handlers registered in `create_app()` are the only place that turn them into a 503. Putting an `HTTPException`
  back in a repository is what this split exists to prevent. Pinned by the
  import-linter contracts in `backend/pyproject.toml`, not by a test.
  A **new module** under `src/expense_tracker/` has to be added to **three** lists, not
  one: the `layers` contract (where `exhaustive = true` fails the gate by itself), and
  the `source_modules` of *both* `forbidden` contracts - a `forbidden` contract has no
  `exhaustive` option, so an unnamed module is silently uncovered by them.
- **`db.py` holds `Base` and nothing else.** Every repository module needs the same
  `DeclarativeBase`, and giving it a module of its own is what lets a second one arrive
  without importing the first - which the `|` between siblings in a layer forbids.
  `currency_repository.py` is that second one, and it imports `Base` from `db`, never
  from `expense_repository`. A new model goes in the repository module that reads it, not
  in `db.py`.
- **Every repository subclasses its ABC and carries `@override`.**
  `PostgresExpenseRepository` and `PostgresCurrencyRepository`, and the two fakes in
  `conftest.py`, all do; a new implementation or test double does too. The base class is an `ABC`, so this is
  enforced, not a convention - a look-alike that matches the shape without inheriting is
  rejected. It has to be enforced somewhere, because `dependency_overrides` is an
  untyped dict and would accept anything.
- **`@abstractmethod` on each repository ABC is load-bearing.**
  Without it the `...` body is an ordinary method returning `None` and an empty subclass
  passes. Removing it fails `pixi run backend-lint` three ways: `B027` on the method,
  `B024` on the class, `F401` on the unused import. That gate is why no test asserts it.
  Keep the body a same-line `...`; `raise NotImplementedError` would be a statement
  coverage counts and nothing executes.
- **An empty `expense` table is 200 with `[]`, not 503.** A database nobody has run the
  loader against yet is a legitimate state and not a fault, and a 503 would train a
  client to retry forever against a server that is working perfectly. So
  `PostgresExpenseRepository` raises only from its `except` arm, with no
  `if not rows: raise` counterpart. Pinned by
  `test_expenses_endpoint_returns_an_empty_list_when_nothing_is_loaded` in both
  `test_app.py` and `test_expense_postgres.py`, and by the `currencies` twins of both -
  `PostgresCurrencyRepository` keeps the same shape. The frontend keeps its half of that
  asymmetry: `ExpensesTable` renders `[]` as a row reading `No expenses loaded.` and
  reserves its `role="alert"` for a request that actually failed.
- **`?currency=` converts in `conversion.py`, and refuses rather than approximates.**
  The module is pure - it takes `ExpenseRecord`s and `CurrencyRateRecord`s and returns
  `ExpenseRecord`s, so `amount` and `currency` are replaced in place and the payload
  shape is the same with the parameter as without it. That is what keeps the *payload*
  half of the frontend out of this: the `Expense` interface in `expenses.ts` and its
  guard are untouched, and only the request URL and the query key gained the parameter. Four refusals are the design,
  not gaps to fill in later: a rate is used **only** in the direction
  `data/currencies/rates.tsv` states it, never inverted and never composed through a
  third currency; a pair loaded twice is refused rather than picked between, and only
  when that pair is needed, so an unrelated duplicate refuses nothing; one unconvertible
  expense refuses the **whole** request, because a list mixing converted and
  unconverted amounts is a column nobody can add up; and a code that is not
  `\A[A-Z]{3}\Z` is refused rather than uppercased, matching the loaders. The one thing
  it does *not* refuse is the identity: `record.currency == target` returns the record
  before any lookup, which is why no `DKK DKK 1.000000` row exists. Arithmetic is
  `Decimal` throughout, `quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)` - spelled
  out because `Decimal` rounds half to **even** by default. `ConversionError` is the
  repositories' pattern reused: the module knows no status code, and the handler in
  `create_app()` is the only place it becomes a 422. That handler reads its exception,
  unlike the two 503s, because the message is about the client's own input and names
  nothing of the database. `conversion.py` is also the module that exercised the "three
  lists, not one" rule above, and it took a **layer of its own** - it imports both
  repository modules, so it sits over them, and the entry points may import it, so it
  sits under them; a `|` sibling of `deps` could be neither.
- **The expenses table renders `amount` and `date` verbatim.** No `Intl.NumberFormat`,
  no `new Date()`. The backend sends `amount` as `str(Decimal)` precisely so no float
  round trip can drift a total by a cent, and formatting it client-side would put that
  round trip back; `date` is a bare `YYYY-MM-DD`, which `new Date()` reads as UTC and
  prints a day early west of Greenwich. `test_app.py`'s
  `test_expense_amounts_are_strings_not_numbers` pins the backend half, and
  `ExpensesTable.test.tsx`'s "shows an alert when an amount arrives as a number" the
  frontend half - the shape guard in `frontend/src/api/expenses.ts` rejects a numeric
  amount rather than coercing it.
- **The HTTP suite never touches PostgreSQL.** `backend/tests/conftest.py` overrides
  the `provide_expense_repository` and `provide_currency_repository` dependencies with
  fake repositories; only `test_expense_postgres.py` and `test_currency_postgres.py`,
  behind the registered `postgres` marker, connect. A new test that hits an endpoint
  takes the `client` fixture. Those modules skip when no server answers and **fail**
  under `CI=true`, so a database that did not come up cannot go green. They TRUNCATE the
  tables they read before and after every test, so running the suite empties a
  developer's loaded data - `pixi run backend-load-expenses` and
  `pixi run backend-load-currencies` put it back.
- **`backend/schema.sql` is the only DDL.** No Alembic, no `Base.metadata.create_all`,
  and every statement in it stays idempotent because `db-init` re-runs against live
  clusters. The loader issues DML only. New tables use
  `GENERATED ALWAYS AS IDENTITY`, not `serial`/`bigserial`, which PostgreSQL's own
  "Don't Do This" page advises against for new applications. `IF NOT EXISTS` adds what
  is missing but never renames or alters, so a change to an existing table means
  `backend-db-reset` and a reload, not another `db-init`.
- **The app reads the environment; loading `backend/.env` is a launcher's job.**
  `config.py` opens no file and resolves no path - no `__file__`, no `env_file=`, no
  `parents[N]`. Reintroducing dotenv reading into the package is the specific regression
  this rule exists to prevent: a wheel-installed package has no project directory to
  derive a path from, so the code either finds nothing or finds a developer's settings,
  depending on how it happened to be installed. **direnv is the one launcher that puts
  those names there**, through the single `dotenv_if_exists` line in `.envrc`. There
  is **no `.env.local` layer** - one file, loaded once - and a dotenv **overwrites** the
  ambient environment, so `export PGPORT=...` is not an override; moving the cluster off
  a taken port means editing `backend/.env` and rebuilding. `[tool.poe]` declares **no
  `envfile`**, and adding one back would be a second loader for one file.
  **`direnv allow` is a prerequisite, not a convenience.** Nothing else supplies the
  settings - not `pixi run`, which reads no `.envrc` and declares no `[activation.env]`,
  and not poe. A shell that has not been blessed gets a `ValidationError` from the app
  and a `PGPORT` abort from the db tasks.
  **CI is a cross-repo dependency, and that is the price of the single loader.**
  `setup-direnv` activates `.envrc` and then forwards the resulting environment to
  `$GITHUB_ENV`; that forwarding arrived in **v1.4.1**, and the pin in `ci.yml` is what
  every later `pixi run` depends on for those names. A `PGPORT` failure in CI means
  checking that pin first, before anything in this repo.
- **`backend/.env` is the single source of the connection settings.** `PGHOST`, `PGPORT`,
  `PGUSER` and `PGDATABASE` live there and nowhere else - `pixi.toml` declares no
  `[activation.env]`, and that absence is deliberate rather than an omission. **The DSN
  is stored nowhere**: `DatabaseSettings.dsn` builds it with `sqlalchemy.URL`, which
  stops the port being written into a URL string a second time and escapes parts
  containing `@`, `:` or `/`. `DATABASE_URL` overrides the four wholesale. Do not
  reintroduce a literal DSN in any manifest, and do not go back to f-string
  interpolation.
- **The dev server's port is `UVICORN_PORT` in `backend/.env`, and `dev` passes no
  `--port`.** uvicorn's CLI is a click command carrying
  `context_settings={"auto_envvar_prefix": "UVICORN"}`, so uvicorn itself resolves
  `--port` from that name - the same shape as `PGHOST` and `psql`, which is the whole
  reason the port belongs in that file rather than in a flag. It is not a connection
  setting: `DatabaseSettings` never sees it and `DATABASE_URL` has nothing to do with
  it. It also takes **no `${UVICORN_PORT:?}` guard**, unlike the db tasks: a lost name
  makes uvicorn *bind* 8000 rather than silently *reach* the wrong server, and `dev`
  aborts on the `${PGPORT:?}` in the `db-init` behind it before uvicorn is ever
  reached.
- **Nothing here falls back to port 5432.** `config.py` refuses to start without its
  settings (`_needs_a_source`), and `db-create` and `db-init` open with a
  `: "${PGPORT:?...}"` guard for the same reason: initdb, psql and createdb each default
  to 5432 and the OS username on their own, so a task that lost the four names would
  reach whatever cluster answers there - applying `schema.sql` to it and reporting
  success - instead of failing. Any new task that reaches a server without passing
  `--port` explicitly takes the guard too. The three `pg_ctl` tasks do not need it: the
  port is baked into `.pgdata/postgresql.conf` by `db-create`, not passed at launch.
- **`database_url()` returns a `URL`, not a `str`.** `str()` and `repr()` of it redact
  the password as `***`, which is what stops a deployment credential reaching a log or a
  traceback; a `str` return would silently give that up. `create_async_engine` and
  `load_directory` both take the `URL` unchanged.
- **`prod` installs the app as a wheel; only `default` installs it editable.** The two
  `[feature.*.pypi-dependencies]` blocks in `pixi.toml` are why `[dependencies]` holds
  runtime *libraries* and not the app. An editable install is a redirect to
  `backend/src`, so it ships the source tree, `backend/tests/` and `backend/data/` and
  pins a container to a directory layout rather than an artifact. **No correctness
  property rests on this** - the app reads the environment either way, so a misconfigured
  process refuses to start in both environments. It is about shipping the right thing.
  Pinned by no test - `pixi run -e prod` is the check, described in `README.md` under
  "Environments".
- **Eight things are declared twice. Change both halves together:**
  - the *payload shape and path* - `backend/src/expense_tracker/__init__.py` against
    `frontend/src/api/expenses.ts`, with nothing checking the agreement. Every expense
    field is a string on the wire, `amount` included, and the frontend's guard rejects a
    number, so a change to `ExpensePayload` is a change to the `Expense` interface;
  - the *rates payload and path* - the same file against
    `frontend/src/api/currencies.ts`, on the same terms: `CurrencyPayload` against the
    `CurrencyRate` interface, `exchange_rate` a string the guard rejects as a number.
    `BASE_CURRENCY` in that module is **not** part of the pair - the backend has no
    notion of a base and needs none, because the identity case it short-circuits is what
    makes `DKK` selectable against an empty rate table;
  - the three tables - `backend/schema.sql` and the `LoadedExpenseFile` and `Expense`
    models in `expense_repository.py` and the `CurrencyRate` model in
    `currency_repository.py`, which never create them and only read them;
  - what is left of the local database connection - `PGUSER` and `PGHOST` in
    `backend/.env`, against `--username=expense_tracker` and
    `--set=listen_addresses=127.0.0.1` in `db-create`'s `initdb` flags, and against
    `createdb expense_tracker` in `db-init`. `PGPORT` is *not* in this list: `db-create`
    takes it as `--set=port="$PGPORT"`, and the rest could follow the same way;
  - the `@` alias (`frontend/src`) - `frontend/vite.config.ts` and
    `frontend/tsconfig.app.json`, because vite does not read tsconfig `paths`;
  - the `frontend/src/main.tsx` coverage exclusion - `frontend/vite.config.ts` and
    `sonar-project.properties`;
  - `VITE_API_BASE_URL` - set in `frontend/.env`, typed in
    `frontend/src/vite-env.d.ts`;
  - daisyUI's `@plugin` descriptors - the block in `frontend/src/styles/app.css`
    against the `plugin` override in `frontend/eslint.config.ts`, because
    `tailwind-csstree` models core Tailwind's blockless `@plugin` and rejects any
    descriptor this repo does not name. See the CSS bullet under "Quality gates".
- **The theme follows the OS, and nothing can override it.** daisyUI is enabled by the
  single `@plugin "daisyui"` block in `frontend/src/styles/app.css`, naming two themes:
  `nord --default`, bound at `:where(:root)`, and `dim --prefersdark`, bound at
  `:root:not([data-theme])` inside `@media (prefers-color-scheme: dark)`. There is no
  `data-theme` attribute, no theme provider, no `@custom-variant dark`, and no `dark:`
  variant anywhere in `src/` - the pair is the whole mechanism, and a user-facing toggle
  would be a feature on top of it, not a config change. A theme paints nothing on its
  own, so the surface is `bg-base-200 text-base-content` on `<body>` in
  `frontend/index.html`: a body background is what propagates to the canvas beyond the
  app shell, and moving it onto a `<div>` is what leaves an unpainted band below short
  content. **Every colour is referenced by role** - `bg-base-100`, `bg-base-200`,
  `text-base-content`, `alert-error` - because a hard-coded shade like `slate-700` is not
  merely awkward with two themes, it is wrong in one of them. jsdom evaluates no CSS, so
  no test covers either half; both are checked by eye, and Chromium's
  `prefers-color-scheme` emulation under *Rendering* is how you reach the one your OS is
  not set to.
- **The API origin lives in bare `frontend/.env`, not `.env.development`.** vite loads
  `.env` in every mode, including the `test` mode vitest runs in, where MSW binds its
  handlers to the URL built from it. `frontend/vite.config.ts` also pins `envDir` to
  `frontend/`, because the `test` block moves vite's `root` to the repo root and
  `envDir` would otherwise follow it.
- **The one route is code-based, in `frontend/src/router.ts`.** No `routeTree.gen.ts`
  and no `@tanstack/router-plugin`: a generated route tree is a committed file that has to
  satisfy prettier, eslint's type-aware pass, a tsconfig that owns it and the coverage
  exclusions, and the plugin drags in `@babel/core`, `chokidar`, `zod` and `unplugin`
  to produce it. `createAppRouter` is a factory rather than a module-level singleton so
  the tests can hand it a `createMemoryHistory`, which is also what keeps `router.ts`
  covered without a new exclusion. The `declare module` block registering `Register` is
  what would give `Link` a typed `to`; without it a path matching no route compiles.
  **Only `App.tsx` imports `Outlet`, and nothing imports `Link`** - it is the layout
  shell and no more, because a nav over a single route would be dead UI.
- **`src/components/` is the router-free layer, not `src/pages/`.** The route owns its
  search schema and its component reads it, so `ExpensesPage` calls `useSearch` and
  `useNavigate` and its test builds a `createMemoryHistory` router the way
  `routing.test.tsx` does. It reaches the route through **`getRouteApi("/")`, never by
  importing `expensesRoute`** - `router.ts` imports the page, so the reverse import is a
  cycle; `getRouteApi` takes a path string, adds no import edge, and stays typed through
  the `declare module` block. Everything under `src/components/` takes props and knows no
  router, which is what keeps `ExpensesTable` and `CurrencySelect` mountable in a bare
  `QueryClientProvider`. Reading the URL from a component instead is what this splits to
  prevent: it would couple a leaf to a route path and put a `RouterProvider` in every
  test that renders it.
- **`validateSearch` fills in an absent parameter and validates nothing else.**
  `?currency=` is handed to the backend as typed, so `/?currency=euro` gets the 422 that
  `conversion.py` raises rather than being corrected or rejected here - re-checking
  `\A[A-Z]{3}\Z` in the frontend would put that pattern in a second place to drift from,
  and the frontend reads no `detail` out of an error body, so the failure surfaces as the
  table's ordinary alert. `CurrencySelect` still shows such a code as its value: a
  `<select>` whose value matches no option displays the first one instead, which would
  disagree with both the URL and the request in flight. There is no "as recorded" mode -
  the parameter is always sent, because an **empty** `?currency=` is a malformed code to
  the backend and not a request for no conversion.
- **The currency options are what the rate table can reach, not a list of ISO codes.**
  `targetCurrencies` in `frontend/src/api/currencies.ts` keeps only the `to_currency` of
  a pair whose `from_currency` is `BASE_CURRENCY`, because a rate is never inverted and
  never composed - a `SEK -> DKK` row makes `DKK` no more reachable from `SEK` than no
  row at all. `BASE_CURRENCY` itself is always offered and needs no rate, since the
  backend returns a record whose currency already equals the target before any lookup.
  A rate list that is pending, 503s, empty or malformed leaves the select disabled at
  `BASE_CURRENCY` and **does not disturb the expenses table**: they are two requests, and
  an empty rate table is a legitimate `200` for the reason an empty ledger is.
- **Every linted file needs a tsconfig that owns it.** eslint runs type-aware via
  `parserOptions.projectService`, so a `.ts`/`.tsx` file outside every tsconfig's
  `include` fails to lint rather than being skipped. `src/` and `tests/` come from
  `tsconfig.app.json`; `vite.config.ts` and `eslint.config.ts` from
  `tsconfig.node.json`, where a new file at the `frontend/` root has to be added too.
  Same reason `frontend/eslint.config.ts` opens with `globalIgnores(["dist"])`.
- **`frontend/package.json` must not gain a `packageManager` field**, and
  `frontend/pnpm-lock.yaml` must stay at `lockfileVersion: 9.0`. The first bypasses the
  pnpm pin in `pixi.toml`; both break Dependabot's lockfile parsing. That lockfile
  version is also what Dependabot reads its pnpm major from, which is why the next
  invariant exists. See [`README.md`](README.md#package-manager).
- **`frontend/pnpm-workspace.yaml` states `minimumReleaseAge: 1440` and must never gain
  a `minimumReleaseAgeExclude`.** Stating the value and excusing a package from it are
  opposites: 1440 is already pnpm 11's default, written down because Dependabot resolves
  this lockfile with pnpm 10 (per the `lockfileVersion: 9.0` pin above), where the
  default is 0 - so without it the 24-hour guard covers CI's *verification* but not
  Dependabot's *resolution*. An exclusion, by contrast, disables the guard for the
  least-vetted release there is; pick a version that already clears the window. Naming
  the value also turns on `minimumReleaseAgeStrict`, which is intended. The file's two
  settings are the whole of it - the other is `allowBuilds`.

## Quality gates

- **Python:** basedpyright in `recommended` mode and ruff with
  `select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]`, both in
  `backend/pyproject.toml`. There is no config file at the repo root and no Python
  setting duplicated in the editor config.
- **Module layering:** import-linter, `[tool.importlinter]` in the same file, run by
  `pixi run backend-lint` as the second half of that task. Imports are just another
  artifact to lint, so they get no gate of their own; `lint-fix` is ruff alone, because
  where a new module belongs in the layer order is a design decision, not a mechanical
  edit. Four contracts: the three-tier `deps | currency_loader | expense_loader` above
  `currency_repository | expense_repository` above `db | config` layering, the
  fastapi/starlette ban on everything but `deps`, a ban on importing the package root,
  and `acyclic_siblings` for cycles at any depth. In a layer list `|` joins siblings
  that may **not** import each other and `:` joins siblings that **may** - the two are
  easy to transpose and only one of them enforces anything. ruff cannot cover this -
  `TID251` bans a name project-wide rather than per-module, and ruff builds no
  cross-module graph, so it detects no cycles.
- **Frontend:** `tsc -b` against a `strict` tsconfig, prettier, and eslint 10 in
  `frontend/eslint.config.ts`. `eslint-config-prettier` is applied last, so **the
  linter owns correctness and prettier owns formatting** - never add a formatting rule
  to the eslint config.
- **CSS is linted by eslint too, not by a second tool.** `@eslint/css` adds a
  `**/*.css` block to the same config and rides the same `frontend-lint` task, so there
  is no stylelint, no third manifest layer and no new pixi task. The block carries no
  rule suppressions, and Tailwind's syntax is **not** hand-written here: it comes from
  `tailwind-csstree`'s `tailwind4`, the extension `@eslint/css` points at for this, so a
  Tailwind at-rule this repo starts using needs no config change. Nothing is exempted -
  `@sourse` and a misspelled `@plugin` descriptor both still fail.
  Two things in that block are load-bearing and neither is a preference:
  - **The `@plugin` `descriptors` override is the one local addition.** daisyUI's
    `@plugin` takes a block; core Tailwind's does not, so `tailwind4` gives it no
    descriptors and css-tree then rejects *every* declaration inside one. It is the
    eighth pair in "declared twice" above. Drop it once
    [tailwind-csstree#63](https://github.com/humanwhocodes/tailwind-csstree/issues/63)
    lands.
  - **`tolerant: true` stays**, for a subtler reason than an unparseable file.
    `tailwind4` reads `source(none)` by trying `<string>` and falling back to `<ident>`,
    and css-tree reports that recovered first attempt through `onParseError` regardless;
    `@eslint/css` promotes every such call to a fatal parse error unless it is
    tolerating them. The prelude itself parses correctly, which is what lets
    `css/no-duplicate-imports` read it - under the old hand-written map it threw on a
    `Raw` prelude and had to be switched off. The cost is that unbalanced braces go
    unreported, because that check is skipped under `tolerant` too.
- **Neither stack has a warn tier.** `recommended` sets `failOnWarnings`, and the
  frontend `lint` script passes `--max-warnings 0`; a warning fails the build like an
  error. Without them roughly 45 frontend rules would be advisory, including the XSS,
  `target="_blank"` and leaked-timer rules, `exhaustive-deps`, and
  `reportUnusedDisableDirectives`. Demote a rule deliberately in its config if you
  disagree with it; do not let either flag go.
