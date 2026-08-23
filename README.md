# expense-tracker

A FastAPI REST API and a React + Tailwind CSS v4 single-page app, as two independent
applications.

`backend/` and `frontend/` are siblings, each owning its own tooling, tests and build.
Neither can see the other: the backend serves JSON and ships no frontend assets, the
frontend builds to its own `dist/` and reaches the API cross-origin over CORS. Either
can be built, tested and linted with the other's directory missing entirely. The root
holds only what spans both - pixi orchestrates the two toolchains, and one SonarCloud
project covers both languages.

Locally that means two processes. Packaging them into a single deployable artifact is
out of scope for now.

```
expense-tracker/
  pixi.toml, pixi.lock          # environments, dependencies, and one `pixi run` task
                                #   per command, each forwarding to the stack below
  sonar-project.properties      # one Sonar project spanning both languages
  .github/                      # CI, release-please, dependabot
  backend/
    pyproject.toml              # hatchling, ruff, pytest, basedpyright, poe tasks
    schema.sql                  # the whole schema: two tables and an index
    data/expenses/              # the committed expense files, loaded into the database
    src/expense_tracker/        # __init__ (the API), deps, config, db,
                                #   expense_repository, expense_loader
    tests/
    .pgdata/                    # the local PostgreSQL cluster, gitignored
  frontend/
    package.json, pnpm-lock.yaml, pnpm-workspace.yaml
    tsconfig*.json, vite.config.ts, eslint.config.ts
    .prettierrc.json, .prettierignore
    .env                        # VITE_API_BASE_URL - where the API lives
    index.html, src/, tests/
    dist/                       # vite output, gitignored
```

## Prerequisites

[direnv](https://direnv.net) and [pixi](https://pixi.sh). The committed `.envrc` runs
`use pixi python`, so entering the directory provisions Python, Node and every
dependency from `pixi.toml`, and re-provisions whenever `pixi.toml` changes. Run
`direnv allow` once after cloning; there is no separate `pixi install` step.

That includes PostgreSQL: the server is a conda-forge package like everything else, so
there is nothing to install system-wide and no container to run. See
[Database](#database).

`.envrc` also runs `use sonarqube_mcp`, which exports the configuration for the
SonarQube MCP server declared in `.mcp.json` - a container giving an editor or agent
access to this project's SonarCloud analysis. It reads `SONARQUBE_TOKEN` and
`SONARQUBE_ORG`; nothing else here needs them.

Neither directive is built into direnv. Both come from the direnv library installed by
[`wsl-cloud-init`](https://github.com/TomBorglum/wsl-cloud-init), whose `setup-direnv`
action CI uses to activate this same `.envrc`. Without that library, `direnv allow`
reports the directives as unknown commands.

Its last line is `dotenv_if_exists`, which puts the database connection settings and the
port the API serves on into the environment. That is stock direnv, and it is the **only**
thing that puts them there - `pixi run` and poe both supply nothing - so `direnv allow` is
what makes the database reachable at all, not just a convenience for bare shell commands.
See [Configuration](#configuration).

## Quickstart

```sh
cd expense-tracker          # direnv provisions the environment on entry
pixi run frontend-install   # install frontend dependencies (pnpm)
```

Then start both, in two terminals:

```sh
pixi run backend-dev   # the local database, then the REST API on http://localhost:8000
pixi run frontend-dev  # the SPA on http://localhost:5173
```

`backend-dev` creates the local database, starts it and applies the schema before it
launches the API, and every part of that is idempotent, so it is the same one command on
the first day and on any later one. The `backend-db-*` tasks drive the cluster on its
own when you want that; see [Database](#database). Sample expenses are a separate,
explicit step - `pixi run backend-load-expenses` and
`pixi run backend-load-currencies`, described under
[Loading expenses](#loading-expenses) and
[Loading exchange rates](#loading-exchange-rates) - because an empty table is a
legitimate state the API answers `200` with `[]`.

Visit http://localhost:5173 and you should see the **Expenses** table, fetched from
`http://localhost:8000/api/expenses` - a genuine cross-origin request, which works only
because the API allows it (see [CORS](#cors)) - and read in turn out of the `expense`
table (see [Database](#database)). Until you run the loader it says
`No expenses loaded.`, which is the empty state and not an error.

The API alone is enough for backend work. The SPA alone runs too; it just renders its
error state until something answers on 8000.

## Routes

| Route | What it serves |
| --- | --- |
| `GET /api/expenses` | `[{"amount", "currency", "date", "category", "details"}, ...]` - the `ExpensePayload` model |
| `GET /api/expenses?currency=EUR` | The same, restated in one currency |
| `GET /api/expenses?from_date=2026-01-01&to_date=2026-01-31` | Only the expenses dated within that range |
| `GET /api/currencies` | `[{"from_currency", "to_currency", "exchange_rate"}, ...]` - the `CurrencyPayload` model |

Both send `Cache-Control: no-store`.

Expenses come back **newest first**, and `amount` is a **string**, not a number: the
column is `numeric(12, 2)`, JSON has no decimal type, and a decimal has no exact binary
form, so a float round trip is how a total drifts by a cent. That shape is declared once,
as the `ExpensePayload` pydantic model in `backend/src/expense_tracker/__init__.py`;
the tests parse responses back into it rather than into untyped dicts. An unreachable
database answers `503 {"detail": "expenses unavailable"}`, but an **empty table answers
`200 []`** - a database nobody has run the loader against yet is a legitimate state, not
a fault, and a 503 would train a client to retry forever against a working server.

Exchange rates come back **by pair**, `from_currency` then `to_currency`, and
`exchange_rate` is a **string** for the same reason `amount` is: the column is
`numeric(18, 6)`, and an amount multiplied by a rate that made a float round trip is an
amount that has drifted. The empty table and the unreachable database behave as above,
with `{"detail": "currencies unavailable"}` as the 503 body.

### Asking for one currency

`?currency=` restates every expense in the code given, **replacing** `amount` and
`currency` rather than adding fields, so the payload is the same shape either way and a
client that does not ask sees exactly what it saw before. `1250.00 DKK` at `0.134048`
comes back as `"167.56" EUR`: `Decimal` arithmetic throughout, quantized to two places
with `ROUND_HALF_UP`, and still a string on the wire.

Only what `data/currencies/rates.tsv` states in that direction is used. A rate is never
inverted and never composed through a third currency, because either would publish a
number the file does not. An expense already in the requested currency passes through
untouched, so the file needs no `DKK DKK 1.000000` row and does not have one.

Anything else is a `422` carrying a plain-string `detail`, the same shape as the 503s
above:

| Request | Body |
| --- | --- |
| `?currency=CHF` | `{"detail": "no exchange rate from DKK to CHF"}` |
| `?currency=euro` | `{"detail": "currency must be an ISO 4217 code"}` |

A lowercase code is refused rather than uppercased, matching the loaders, which refuse
one in a file. One unconvertible expense refuses the **whole** request: a list mixing
converted and unconverted amounts is a column nobody can add up. A pair loaded twice is
refused the same way, and only when that pair is actually needed.

The arithmetic lives in `backend/src/expense_tracker/conversion.py`, which knows no HTTP
and holds no session - it takes records and rates and gives records back, so it is
tested in `backend/tests/test_conversion.py` without a client or a database.

### Asking for a range of dates

`?from_date=` and `?to_date=` narrow the list to the expenses dated between them.
**Both bounds are inclusive**, so `?from_date=2026-01-01&to_date=2026-01-31` is January
including both the 1st and the 31st, and **each is optional on its own**: give only
`from_date` and the range runs to the newest expense there is, give only `to_date` and it
runs from the oldest. Give neither and the request is the one that was there before the
parameters existed.

The filtering is a `WHERE` clause on `expense_date`, not a pass over the rows in Python,
and the `expense_newest_first_idx` index already serves it - so `schema.sql` gained
nothing for this. **A range holding no expenses is `200 []`**, for the reason an empty
table is: it is an answer, not a fault. The two parameters compose with `?currency=`, and
the range is applied first, so an expense outside it needs no exchange rate.

Dates are read as `YYYY-MM-DD` and nothing else - the form the payload's own `date` field
uses. Anything else is a `422` carrying the same plain-string `detail`:

| Request | Body |
| --- | --- |
| `?from_date=01/01/2026` | `{"detail": "from_date must be a date in YYYY-MM-DD form"}` |
| `?to_date=2026-02-30` | `{"detail": "to_date must be a date in YYYY-MM-DD form"}` |
| `?from_date=2026-03-01&to_date=2026-01-01` | `{"detail": "from_date must not be after to_date"}` |

A range that ends before it begins is refused rather than answered with an empty list: an
empty list reads as "no expenses then", and nobody meant that range. That refusal belongs
to the `DateRange` type rather than to the parsing, so it holds however the range is
built, and the repository takes that type instead of two loose dates - it has no ordering
to re-check and no caller to trust. Both live in
`backend/src/expense_tracker/date_range.py`, which knows no HTTP and no database at all,
and are tested in `backend/tests/test_date_range.py`.

Both endpoints are read-only over HTTP. Rows arrive through
`pixi run backend-load-expenses` and `pixi run backend-load-currencies` and nowhere else,
so there is no POST, PUT or DELETE.

That is the whole surface. There is no page route and no static mount - the frontend
is a separate app - and no OpenAPI schema, `/docs` or `/redoc`: two hand-written routes
do not earn a generated document, and the schema would be public surface advertising
it. `backend/tests/test_app.py` asserts that `/`, `/static/*`, any other `/api` path
and the three docs routes all return 404, so none of it can come back by accident.

## CORS

`create_app()` adds `CORSMiddleware` with `allow_origins=["*"]`, because the SPA is
served from its own origin and every call it makes is cross-origin.

`allow_credentials` is **`False`** and has to stay that way while the origin is a
wildcard: the CORS spec forbids the combination and browsers reject it. This API sends
no cookies and reads no `Authorization` header, so nothing is lost. When that changes,
replace the wildcard with a real origin list - not the other way round.

The middleware is registered *after* the security-headers middleware, making it the
outermost of the two. That is what lets it answer a preflight `OPTIONS` itself rather
than passing it to a router with no such route.

## Database

PostgreSQL, holding three tables: `loaded_expense_file` and `expense`, which together are
a view of the files in `backend/data/expenses/`, and `currency_rate`, which is a view of
`backend/data/currencies/`. See [Loading expenses](#loading-expenses) and
[Loading exchange rates](#loading-exchange-rates).

The server is a **pixi dependency**, not a container. `postgresql` is pinned in
`pixi.toml` beside python and node, so `direnv allow` provisions it and the `db-*`
tasks drive it. There is no Dockerfile, no compose file, and no `services:` block in
`.github/workflows/ci.yml` - CI runs `pixi run backend-db-init`, exactly what a
developer runs.

### The cluster

`pixi run backend-db-create` runs `initdb` into `backend/.pgdata/` (gitignored), beside
the only code that talks to it. Three settings are baked into the generated
`postgresql.conf` rather than passed at launch, which is why `db-start` needs no flags:

| Setting | Value | Why |
| --- | --- | --- |
| `port` | `$PGPORT`, `5433` by default | Cannot collide with a system PostgreSQL on 5432 |
| `listen_addresses` | `127.0.0.1` | Off the network entirely |
| `unix_socket_directories` | `/tmp` | Nothing connects over it; the DSN is TCP |

The port comes from `backend/.env` (see [Configuration](#configuration)); the other two
are literals in the `db-create` task. Because all three are baked into the cluster rather
than passed at launch, changing `PGPORT` takes a `pixi run backend-db-reset` and a fresh
`backend-db-init` to take effect - `db-create` is a no-op against a `.pgdata/` that
already exists.

The superuser and the database are both named `expense_tracker`, so the DSN is
identical on every machine and on CI. Authentication is `trust`, which is acceptable
**only** because of `listen_addresses`: this is a throwaway cluster holding one row of
public text, rebuildable at any moment from `backend/schema.sql`. Do not copy the
`initdb` flags anywhere real.

All five tasks are idempotent, and the chain is `dev` depends on `db-init` depends on
`db-start` depends on `db-create` - so `pixi run backend-dev` brings the cluster up on
its way to the API and none of the five is one you normally run by hand.
`pixi run backend-db-init` is the one to reach for when you want the database up without
a server: the `postgres`-marked tests need it, and the two loaders do too.
`db-reset` throws the cluster away - the cure for a change to an existing table, which
`schema.sql`'s `IF NOT EXISTS` statements cannot apply.

### Schema and access

`backend/schema.sql` is the entire schema and the only DDL. There is no Alembic - two
append-only tables rebuildable from `backend/data/expenses/` do not earn a migration
tool - and the app issues no DDL of its own, so nothing but `db-init` ever runs it.
Every statement in it is idempotent, because `db-init` re-runs against live clusters.
Generated keys use `GENERATED ALWAYS AS IDENTITY` rather than `bigserial`, which
PostgreSQL's own
[Don't Do This](https://wiki.postgresql.org/wiki/Don%27t_Do_This) page advises against
for new applications. The `LoadedExpenseFile` and `Expense` models declare the same
tables a second time, in Python, with nothing checking the agreement; change both
together.

Access is SQLAlchemy 2 async over asyncpg, split across five modules:

| Module | Holds |
| --- | --- |
| `__init__.py` | `create_app()`, the route, the exception handler, `ExpensePayload` |
| `deps.py` | the lifespan, the per-request session, and the `provide_expense_repository` seam |
| `expense_loader.py` | the TSV parser and the `python -m` entry point - the only thing that writes |
| `expense_repository.py` | `LoadedExpenseFile`, `Expense`, and the expense repository |
| `db.py` | the declarative `Base` every repository module builds on |
| `config.py` | the database connection settings, and nothing else |

A repository module holds its models, an **abstract base class**, its `Postgres*`
implementation and the `...UnavailableError` it raises, and imports nothing from
FastAPI - so it knows no status code. Callers depend on the base class and never name an
implementation; implementations subclass it and carry `@override`, so the coupling is
visible at the class declaration and drift fails `backend-typecheck`.
`expense_loader.py` is a *sibling* of `deps.py`, not something below it, and may not
import it - which is what keeps FastAPI out of `python -m`.

The dependency arrows run one way, and are checked rather than merely intended: `pixi
run backend-lint` runs import-linter after ruff, against the contracts in
`backend/pyproject.toml`, which fail the build on an import pointing back up the stack,
on anything but `deps.py` learning about FastAPI, and on a cycle anywhere in the
package. `create_app()` holds the only handler that maps an exception to a 503.

The engine is owned by the app's **lifespan** rather than built at import time, and
handed to requests as lifespan state, from which a session is opened per request. That
is not incidental: it means `create_app()` opens no socket, which is what lets most of
the test suite construct a real app with no database anywhere.

`backend/tests/test_app.py` overrides the repository dependency with a fake and never
connects. Only `backend/tests/test_expense_postgres.py` talks to the real server, behind
the `postgres` marker registered in `backend/pyproject.toml`; it skips when nothing
answers, so a developer who has not run `db-init` does not face a red suite, and
**fails** under `CI=true`, so a database that did not come up cannot go green.

### Loading expenses

```sh
pixi run backend-load-expenses      # reads backend/data/expenses/*.tsv into the database
```

Files are `*.tsv`: **tab-separated**, UTF-8, one header line naming exactly these five
columns in this order, then one line per expense.

| Column | Format | Notes |
| --- | --- | --- |
| `Amount` | decimal | At most two decimal places; may be negative |
| `Currency` | ISO 4217 alpha-3 | Uppercase |
| `Date` | `DD/MM/YYYY` | Day first |
| `Category` | free text | Must not be blank |
| `Details` | free text | May be empty |

A third decimal place is refused rather than rounded away by `numeric(12, 2)` in
silence. A negative amount is accepted, because a refund is a negative expense. The
header is checked strictly, which doubles as a delimiter check: a comma-separated file
fails on line 1 naming what it found instead of loading a column of nonsense. A
byte-order mark is tolerated, and blank lines are skipped.

**Re-running the loader is a no-op**, and that is the ledger's doing, not the rows'.
`loaded_expense_file` records each file's name and the SHA-256 of its bytes; a file
already recorded with a matching digest is skipped whole. The expense rows carry no
content hash and no `ON CONFLICT`, deliberately - two identical lines are two real
purchases, so the rows themselves cannot say whether they have been loaded, and hashing
them would silently collapse a pair of same-day fill-ups into one and make the month
come up short.

Each file is its own transaction: its ledger row and its expenses commit together or
not at all, so a run that dies half way can simply be re-run.

**Editing a loaded file is refused.** A known filename arriving with a different digest
stops the run, naming the file and when it was taken in. Skipping it would make a typo
fix appear to work while doing nothing; re-reading it would either duplicate the
unchanged rows or delete from a database meant to be a read-only view. Append a new
file instead, or rebuild:

```sh
pixi run backend-db-reset && pixi run backend-db-init && pixi run backend-load-expenses
```

That rebuild is also the cure after `pixi run backend-test`, which TRUNCATEs the expense
tables before and after every test in `test_expense_postgres.py`, and `currency_rate`
around every test in `test_currency_postgres.py` - running the suite empties whatever you
had loaded.

It is the cure for a **schema change**, too. Every statement in `schema.sql` is
`CREATE ... IF NOT EXISTS`, so `db-init` adds what is missing but never renames or alters
what is already there. Pulling a branch that changes a column or a table name means
resetting the cluster, not re-running `db-init`. A branch that only *adds* a table - as
`currency_rate` did - needs no reset, just `db-init`.

### Loading exchange rates

```sh
pixi run backend-load-currencies    # replaces the rates with backend/data/currencies/*.tsv
```

Same file conventions - tab-separated, UTF-8, strict header, BOM tolerated, blank lines
skipped - over three columns.

| Column | Format | Notes |
| --- | --- | --- |
| `FROM_CURRENCY` | ISO 4217 alpha-3 | Uppercase |
| `TO_CURRENCY` | ISO 4217 alpha-3 | Uppercase |
| `EXCHANGE_RATE` | decimal | At most six decimal places; must be positive |

A seventh decimal place is refused rather than rounded away by `numeric(18, 6)`, and a
zero or negative rate converts nothing, so it is refused too.

**This loader replaces rather than appends**, which is the opposite of the expense
loader above and is the point rather than an inconsistency. A rate for a pair is a
current fact, not an event: there is no ledger table, every run deletes the rates it
finds and inserts the file's, and **editing a rate and re-running is the supported
workflow**. Deleting and inserting share one transaction, so nothing ever observes the
table empty, and every file is parsed *before* anything is deleted, so a typo leaves the
loaded rates exactly as they were.

## Frontend

A React 19 SPA built by vite and styled with Tailwind CSS v4, configured in CSS via
`frontend/src/styles/app.css` - there is no `tailwind.config.js`.

The palette and the component classes come from [daisyUI](https://daisyui.com), enabled
as a `@plugin` in that same stylesheet. Two themes are named and the operating system
picks between them: `nord --default` is the baseline, and `dim --prefersdark` takes over
under `prefers-color-scheme: dark`. There is no `data-theme` attribute, no theme
provider, no toggle, and no `dark:` variant in `src/` - colours are written by role
(`bg-base-100`, `text-base-content`, `alert-error`) and the two themes repoint them.

The pair is chosen to match: both sit in the same desaturated blue-grey family (base hues
260.7 and 264.1), and both are soft - `dim` is the lightest dark theme daisyUI ships, and
`nord` is one of the few light ones that stops short of pure white. Swapping either half
means checking that still holds.

`pixi run frontend-build` writes to `frontend/dist/`, vite's default. It is **gitignored**
and nothing in this repo consumes it. CI runs the build as a gate because tsc and
vitest never exercise the bundler, but keeps nothing from it.

`GET /api/expenses` is the app's main read, fetched at runtime with
[TanStack Query](https://tanstack.com/query) in `frontend/src/api/expenses.ts` and
rendered by `frontend/src/components/ExpensesTable.tsx` as one table of amount, currency,
date, category and details. Nothing generates a client from a schema, so the payload
*shape* is written out by hand on both sides and the two must be changed together; a
mismatch shows up as a 404 or a failed shape guard at runtime. Every field is a string on
the wire - `amount` included, because JSON has no decimal type - so the guard rejects a
numeric amount rather than letting a float round trip through the page. Both
values are rendered exactly as they arrive: formatting the amount client-side would put
back the round trip `str(Decimal)` exists to prevent, and `new Date()` on a bare
`YYYY-MM-DD` reads it as UTC and prints a day early west of Greenwich. The rows keep the
order the API sends them in (newest first) and are never re-sorted, and an empty ledger
arrives as a 200 with `[]`, so the table says so in a row instead of raising an alert.

### Choosing a currency

A select beside the heading picks the currency the expenses are presented in, and the
choice is the `?currency=` the table asks the API for. **The conversion stays the
backend's** - the frontend sends a code and renders the strings that come back, so the
`Decimal` arithmetic in `conversion.py` is the only place an amount is ever computed.

The choice lives in the **URL**, so `/?currency=EUR` is a link worth sending and a reload
returns to it. `validateSearch` in `frontend/src/router.ts` supplies `DKK` when the
parameter is absent and checks nothing else: a code the backend refuses is passed through
and answered with a 422, which reaches the page as its ordinary "Could not load the
expenses." The parameter is always sent - an **empty** `?currency=` is a malformed code
to the backend, not a request for no conversion, so there is no "as recorded" mode and
the ledger's own currency is simply `DKK`, the one code that needs no rate.

The options are read from `GET /api/currencies` by `frontend/src/api/currencies.ts` and
are **not** a list of ISO codes. Because a rate is used only in the direction
`rates.tsv` states it and is never composed, the only reachable targets are the
`to_currency` of a pair whose `from_currency` is the base - `EUR`, `GBP`, `NOK`, `SEK`,
`USD` today. The file's `EUR -> DKK` and `USD -> DKK` rows are ignored here: they convert
*into* the base, which is where the expenses already are. A rate list that has not
arrived, fails, or comes back empty leaves the select disabled on `DKK` and does not
disturb the table below - they are two independent requests, and an empty rate table is a
working server for the reason an empty ledger is.

### Choosing a date range

A calendar beside the currency select picks the days the expenses are drawn from, and the
choice is the `?from_date=` and `?to_date=` the table asks the API for. **The filtering
stays the backend's** - it is a `WHERE` clause on `expense_date`, described under
[Asking for a range of dates](#asking-for-a-range-of-dates); the frontend sends two dates
and drops no row of its own.

Both bounds live in the **URL** alongside the currency, so
`/?currency=EUR&from_date=2026-01-01&to_date=2026-01-31` is a link worth sending.
`validateSearch` in `frontend/src/router.ts` fills an absent bound with the first or last
day of the current month, from one reading of the clock, and checks nothing else - a date
the backend refuses is passed through and answered with a 422, which reaches the page as
its ordinary "Could not load the expenses." Both parameters are always sent, and there is
no clear button: an **empty** `?from_date=` is a malformed date to the backend rather than
a request for everything, so the way to see more is to pick earlier or later days. A range
holding no expenses is a 200 with `[]`, which the table shows as a row and not an alert.

The control is [DayPicker](https://daypicker.dev) in `mode="range"`, pinned as
`@daypicker/react`. It was chosen over daisyUI's own calendar component because that one
is the `cally` web component, which renders into a shadow root that the tests cannot see
through - every query in `frontend/tests/` goes by role and accessible name. DayPicker
renders an ordinary `<table role="grid">` of buttons instead. It brings `date-fns` along
transitively; nothing in `src/` imports it, because `frontend/src/dates.ts` is the one
place a `Date` becomes a `YYYY-MM-DD` and it is built from the local field getters -
`toISOString()` would name the previous day east of Greenwich, the mirror of the trap
`new Date()` sets on the way in.

It shows two calendars side by side, each with a month and a year dropdown for a caption
and no arrows at all. They navigate **independently** - the left can sit on January 2025
while the right shows December 2026 - and follow one another only far enough to stay in
order, so any span is two clicks away rather than a run of chevron presses. A range can
start in either panel and end in the other. Opening puts one panel on each end of the
range currently selected.

Those dropdowns need a finite list, so the calendar is bounded: 1 January of `FIRST_YEAR`
in `frontend/src/dates.ts` through 31 December of the current year. Both bounds are
invented - nothing publishes the range the data actually spans - and with no arrows that
list is the whole of what navigation can reach, so an expense dated before `FIRST_YEAR`
cannot be reached by clicking. A URL naming such a day still works, since the dates are
passed through as typed.

The panel closes on a click outside it or on Escape, like the select beside it, and either
way a half-picked range is discarded rather than left disagreeing with the URL.

The calendar also cannot be made to select a range that ends before it begins: DayPicker
orders the pair itself, so a click before the start becomes the new start. The backend
still refuses an inverted range, because the URL can be typed by hand.

### Routing

One route, declared by where its file sits, with
[TanStack Router](https://tanstack.com/router)'s file-based routing:
`frontend/src/routes/index.tsx` is `/`, the expenses table, and
`frontend/src/routes/__root.tsx` is the layout it renders inside.
`@tanstack/router-plugin`, configured inline in `frontend/vite.config.ts`, reads that
directory and writes `frontend/src/routeTree.gen.ts`.

**That generated file is committed and never hand-edited.** It is part of the runtime
rather than a build artifact - `tsc`, eslint and the editor all need it on a fresh
checkout, and every frontend gate except the build reads it without being able to
produce it. Two independent checks keep it honest, and they catch different things:
adding a route file fails `frontend-typecheck`, because `createFileRoute("/new")` is
not assignable against a stale tree; a rename, a deletion or a changed path typechecks
fine and is caught instead by the `git diff --exit-code` step `.github/workflows/ci.yml`
runs after `frontend-build`, the one gate that runs vite and so the one that
regenerates. The file is excluded from prettier, coverage and Sonar - three declarations
that nothing checks agree - while eslint is covered by the file's own
`/* eslint-disable */` header rather than by an ignore pattern, which would make eslint
warn every time an editor opened it. Prettier's exclusion is not a preference: the
generator formats with prettier's own defaults rather than `.prettierrc.json`, so the
file lands at `printWidth` 80 and could never pass the check at 88.

`createAppRouter` in `frontend/src/router.ts` takes an optional history so the tests can
pass `createMemoryHistory()`; `frontend/src/main.tsx` calls it with none and gets the
browser's. The `declare module` block at its foot is what makes a `Link`'s `to` typed
against the real route tree. `__root.tsx` is the only file that renders the router's own
components; there is no nav, because one over a single route would be dead UI.

The route owns its search schema, so its component is the one that reads it - and under
file-based routing they are the same module, so `index.tsx` holds `validateSearch` and
the page together and reads the URL through `Route.useSearch()`. **The router-free layer
is `frontend/src/components/`**: `ExpensesTable` and `CurrencySelect` take props, know
nothing of the URL, and mount in a bare `QueryClientProvider`. `autoCodeSplitting` is on,
so the route's component is emitted as its own chunk. A deployed SPA needs its server to
fall back to `index.html` so a non-root path resolves on a cold load; vite's dev server
does that already, and nothing in this repo serves `frontend/dist/`.

Tests use vitest, live in `frontend/tests/`, and reach into the app through the `@`
alias (`@/api/expenses`). The alias is declared twice - `resolve.alias` in
`frontend/vite.config.ts` for the bundler and `paths` in `frontend/tsconfig.app.json`
for the type checker, because vite does not read tsconfig `paths` - so both must point
at the same place. Imports *within* `src/` stay relative.

The backend is stubbed with [MSW](https://mswjs.io). `frontend/tests/setup.ts` starts
the server with `onUnhandledRequest: "error"`, so an unstubbed request fails the test
instead of quietly reaching the network. Handlers bind to the absolute `EXPENSES_URL`
exported by the module under `frontend/src/api/`, because a path-only pattern would
resolve against jsdom's origin rather than the API's and never match.

`frontend/src/main.tsx` is excluded from coverage in both `frontend/vite.config.ts` and
`sonar-project.properties` - it only wires React to the DOM. `frontend/vite.config.ts`
also pins vitest's root back up to the repo root (`new URL("../", import.meta.url)`),
even though vite's own root is `frontend/`. That is what makes the lcov report record
repo-relative paths like `frontend/src/App.tsx`; without it SonarCloud resolves them
against the Python package and reports the frontend as uncovered - silently, with a
green build.

### Where the API lives

`frontend/.env` holds `VITE_API_BASE_URL`, and the modules under `frontend/src/api/`
resolve every request path against it. That one variable is the frontend's only
knowledge of the backend; there is deliberately no vite proxy, so the dev-time request
is a real cross-origin call over the same CORS path a deployed one would take. Override
it in `frontend/.env.local` (gitignored) to point at a backend elsewhere.

Two details worth knowing:

- It lives in bare `.env`, not `.env.development`, because vite loads `.env` in *every*
  mode - including the `test` mode vitest runs in, where MSW needs the same value.
- `frontend/vite.config.ts` pins `envDir` to `frontend/`. Without it, the `test`
  block's repo-root `root` would drag env-file lookup up there too and leave the suite
  with no base URL.

It is typed in `frontend/src/vite-env.d.ts`, which also sets
`ViteTypeOptions.strictImportMetaEnv` - that drops vite's `any` index signature on
`ImportMetaEnv`, so a mistyped `import.meta.env.VITE_*` is a type error rather than a
silent `undefined`.

The flip side of `.env` loading in every mode is that `pixi run frontend-build` **bakes
`http://localhost:8000` into the bundle**. That is fine today, since the build exists
as a CI gate and nothing deploys it, but a real deployment needs the value supplied for
the production mode via a `.env.production` or a `VITE_API_BASE_URL` in the build
environment. vite inlines it at build time; there is no runtime lookup to override. Note
that `.gitignore` ignores every `.env` variant but the two committed defaults, so a
`.env.production` you add has to be named back in before it can be committed - deliberate,
since that is the shape a real credential usually arrives in.

### Package manager

Dependencies are installed with **pnpm**, whose version is pinned in `pixi.toml`
alongside Node. Three deliberate choices:

- **`frontend/package.json` has no `packageManager` field, and must not gain one.**
  pnpm's `pmOnFail` defaults to `download`, so that field would make pnpm fetch and run
  its own copy of the declared version, bypassing the pixi pin.
- **Pins must be at least three days old.** `frontend/pnpm-workspace.yaml` sets
  `minimumReleaseAge: 4320`, so pnpm refuses to install versions published in the last
  three days as a supply-chain guard. Because this project pins exact versions, pnpm
  cannot fall back to an older release - it asks you to exempt the version instead.
  **Pick a newer release that already clears the window rather than adding an
  exemption**, which would disable the guard for precisely the least-vetted package.

  The value is 4320 because it has to equal `cooldown.default-days` in
  `.github/dependabot.yml`, which is three days. Dependabot does not use that window
  only to choose versions: it passes `min(semver tier, default-days)` to pnpm as
  `--config.minimumReleaseAge`, enforced across its entire resolution, so anything
  already in the repo that is younger than the gate fails the weekly update job with
  `ERR_PNPM_NO_MATURE_MATCHING_VERSION` instead of skipping an update. Equal values
  leave no such gap. Tiers above the floor - `semver-minor-days`, `semver-major-days` -
  delay selection only and never raise the gate, because Dependabot caps it at
  `default-days`.

  Writing the value down at all is for **Dependabot**, which is not running pnpm 11. It
  picks its pnpm major from the lockfile, and the `lockfileVersion: 9.0` pin lands it on
  pnpm 10, where the setting defaults to 0. Left implicit, the guard would hold where the
  lockfile is *verified* (CI) and not where it is *resolved* (Dependabot), which is how a
  transitive package five hours old reached `pnpm-lock.yaml` and failed CI in PR #48. One
  case stays outside it: Dependabot deliberately disables the guard for **security**
  updates, so such a PR can still carry a too-young entry. Re-run the job once that
  version clears the window (`gh run rerun <run-id> --failed`) - the check recomputes the
  cutoff at install time.
- **Install scripts are answered explicitly.** pnpm 11 exits non-zero while a
  dependency's install script is neither allowed nor denied, which would fail
  `pixi run frontend-install` in CI. The decision lives in `frontend/pnpm-workspace.yaml`
  under `allowBuilds`, the only place pnpm 11 still reads it. `msw` is denied there:
  its script only copies the browser service worker, and the tests use `msw/node`.

## Editor setup (Zed)

`.zed/settings.json` exists to make Zed **report** what CI enforces. Every entry does
one job: pin a language server to the version this repo pins. None of them configures a
linter or a type checker - each stack's own config file already does that, and
duplicating it in the editor is how the two drift apart. Read the file itself for the
per-server reasoning.

Preconditions: run `direnv allow` (for the basedpyright path under `.pixi/`) and
`pixi run frontend-install` (for the frontend servers under `frontend/node_modules/`),
or those paths do not exist yet and the servers will not start. `direnv allow` is also
what puts the database settings into the environment, so a test runner launched from
inside the editor reaches the local cluster only if the editor inherits that environment
- one started from a shell direnv has blessed does.

Formatting is not configured here: `format_on_save` is left to your own Zed settings.
Formatting is applied by `pixi run frontend-format` and gated in CI by
`pixi run frontend-format-check`, the same way `ruff format` works on the Python side.

To confirm the declared pins match what is installed:

```sh
cd frontend && pnpm ls @tailwindcss/language-server @vtsls/language-server typescript tailwindcss prettier eslint
```

Expect `0.16.0`, `0.3.0`, `6.0.3`, `4.3.3`, `3.9.6`, `10.8.1`. One nested entry is
expected and is not drift: `@vtsls/language-server` bundles its own `typescript@5.9.3`,
which the `tsdk` setting in `.zed/settings.json` redirects to the pinned top-level copy.

To confirm Zed is using them, open a `.tsx` file **and** `frontend/src/styles/app.css`
first - Zed starts a language server only when a buffer of a language it serves is open,
so a server you have given nothing to do is absent from the list below rather than
broken - then run:

```sh
ps -eo pid,args | grep -E '[v]tsls|[c]ss-language-server|[e]slintServer'
```

Expect four processes. `@tailwindcss/language-server` ships **two** binaries and this
repo runs both, so that middle pattern is deliberately loose enough to match each:
`tailwindcss-language-server` completes class names in TSX, and `css-language-server`
is the Tailwind-aware CSS server that replaces `vscode-css-language-server` in the
`CSS` block. The second one needs Zed **1.16.1 or newer**, which is where the
`tailwindcss-intellisense-css` adapter was added; on an older Zed the name resolves to
nothing and `.css` files get no language server at all.

Paths under `frontend/node_modules/` mean the pins took effect; paths under
`~/.local/share/zed/` mean they did not - usually a missing `node_modules` or no `node`
on PATH for Zed's remote server. `eslintServer.js` is the exception and always runs from
`~/.local/share/zed/`, because that server is Zed's own and only the module it loads is
pinned; check it by putting `const x: any = 1;` in a `.tsx` file and confirming
`@typescript-eslint/no-explicit-any` fires.

Three things that look like faults but are not. Over a remote/WSL backend, Server Info
reports `Binary: Unknown` and `Version: Unknown` for `vtsls` however healthy it is, and
the per-server Logs tab is usually empty because most servers never send
`window/logMessage`. Use the `ps` command above instead. Zed also underlines
`tailwindcss-intellisense-css` in `.zed/settings.json` as **"Property
tailwindcss-intellisense-css is not allowed"** - the setting is applied regardless, and
the same key in your own `settings.json` draws no warning at all. It is an upstream
schema bug: Zed builds the *project* settings schema from its language-attached servers
only, where the *user* settings schema also includes opt-in ones (zed#46766), and this
server is opt-in. `ps` is the check that settles it. If your editor ever disagrees
with CI, `pixi run backend-typecheck` and `pixi run frontend-lint` are the authority.

## Development tasks

`pixi run <task>` is the entry point, and the same command CI runs.

| Command | Delegates to | What it does |
| --- | --- | --- |
| `pixi run backend-db-init` | `poe db-init` | Create, start and apply the schema to the local database, without a server in front of it |
| `pixi run backend-db-create` | `poe db-create` | `initdb` a cluster into `backend/.pgdata/`, if there is not one |
| `pixi run backend-db-start` | `poe db-start` | Start the cluster on `$PGHOST:$PGPORT`, if it is not running |
| `pixi run backend-db-stop` | `poe db-stop` | Stop the cluster; succeeds if it is already stopped |
| `pixi run backend-db-reset` | `poe db-reset` | Stop the cluster and delete `backend/.pgdata/` entirely |
| `pixi run backend-dev` | `poe dev` | Start the database if it is not up, then run the API on uvicorn, port `$UVICORN_PORT` (with reloader) |
| `pixi run backend-test` | `poe test` | Run the test suite with coverage |
| `pixi run backend-lint` | `poe lint` | Lint with ruff, then check the import graph with import-linter |
| `pixi run backend-lint-fix` | `poe lint-fix` | Auto-fix lint issues (ruff only) |
| `pixi run backend-load-expenses` | `poe load-expenses` | Read `backend/data/expenses/*.tsv` into the database |
| `pixi run backend-load-currencies` | `poe load-currencies` | Replace the exchange rates with `backend/data/currencies/*.tsv` |
| `pixi run backend-format` | `poe format` | Format with ruff |
| `pixi run backend-format-check` | `poe format-check` | Check formatting without writing changes |
| `pixi run backend-typecheck` | `poe typecheck` | Type-check with basedpyright (recommended) |
| `pixi run frontend-install` | `pnpm install` | Install frontend dependencies (`--frozen-lockfile`) |
| `pixi run frontend-dev` | `pnpm run dev` | Run vite's dev server on port 5173 (hot reload) |
| `pixi run frontend-build` | `pnpm run build` | Build the frontend into `frontend/dist/` |
| `pixi run frontend-typecheck` | `pnpm run typecheck` | Type-check the frontend with tsc |
| `pixi run frontend-lint` | `pnpm run lint` | Lint the frontend with eslint (type-aware, plus CSS, `--max-warnings 0`) |
| `pixi run frontend-lint-fix` | `pnpm run lint-fix` | Auto-fix frontend lint issues |
| `pixi run frontend-test` | `pnpm run test` | Run the frontend tests (vitest) with coverage |
| `pixi run frontend-format` | `pnpm run format` | Format the frontend with prettier |
| `pixi run frontend-format-check` | `pnpm run format-check` | Check frontend formatting without writing changes |

Every task sets its own working directory in `pixi.toml` (`backend/` or `frontend/`), so
`pixi run <task>` behaves the same wherever you invoke it from. No task crosses between
the two directories, and every one of them - the five `backend-db-*` included - addresses
its files by a plain relative path. Nothing reaches above its own stack.

That holds when you skip the forwarder too: poe runs a task from the directory of the
`pyproject.toml` it loaded, so `poe -C backend db-start` resolves `backend/.pgdata/`
exactly as `cd backend && poe db-start` does. The *path* travels; the environment does
not. Run it from inside the worktree, where direnv has loaded - invoked from outside, a
`db-*` task resolves its paths correctly and then aborts on its `${PGPORT:?}` guard rather
than reaching for whatever cluster answers on 5432. `pixi task list` prints this table's
first column.

CI runs every gate above except the two `dev` tasks, the two `-fix` variants,
`backend-format`, the two loaders and the four `backend-db-*` tasks other than
`backend-db-init` on each pull request, then the SonarCloud scan. The loaders are left
out because they mutate data and CI has no need of them: `test_expense_postgres.py` and
`test_currency_postgres.py` already put the committed sample files through the real
database path inside `backend-test`.

### Where commands are defined

The middle column is not decoration - **`pixi.toml` defines no commands, it only
forwards.** Each stack owns its own, in the manifest that already owns how its tools
behave:

- **Backend:** `[tool.poe.tasks]` in `backend/pyproject.toml`, beside the ruff, pytest
  and basedpyright config they invoke. Python has no built-in task runner, so
  [poethepoet](https://poethepoet.natn.io) supplies one.
- **Frontend:** the `scripts` block in `frontend/package.json`, where a Node developer
  expects it.

Two layers rather than one buys both properties at once: `pixi run` is a single
discoverable index across two ecosystems, and each directory stays a standalone project
you can run natively.

```sh
cd backend  && poe test    # poe with no task lists the backend's
cd frontend && pnpm test   # pnpm run lists the frontend's
```

The cost is that adding a command means two edits - define it in the stack's manifest,
then forward it from `pixi.toml`. Put the command body in the stack, never in the
forwarder.

## Environments

`pixi.toml` declares two, on one solve-group so python is pinned identically across both:

| Environment | Contains | Used by |
| --- | --- | --- |
| `default` | runtime libraries, test tooling, node, PostgreSQL, and the app **editable** | the editor, local dev, CI, every task |
| `prod` | runtime libraries and the app as a **wheel** | what an image is built from |

The install mode is the difference that matters. An editable install is a redirect to
`backend/src`: nothing is copied, so the source tree has to stay where it was at install
time. That is exactly what a developer wants - edit, re-run, no reinstall - and exactly
what a deployment must not have, because it would ship the source tree, `backend/data/`
and `backend/tests/` inside the image and pin the container to a directory layout rather
than to an artifact.

So the app is declared per feature rather than in the default feature, which is why
`[dependencies]` holds runtime *libraries* only:

```toml
[feature.dev.pypi-dependencies]
expense-tracker = { path = "backend", editable = true }

[feature.prod.pypi-dependencies]
expense-tracker = { path = "backend", editable = false }
```

`prod` gets a real wheel, built by hatchling, containing `src/expense_tracker` and
nothing else. **No correctness property rests on the split.** The app reads its settings
from the environment and opens no file, so a misconfigured process refuses to start in
either environment - which you can check directly, clearing what direnv exported first:

```sh
pixi install -e prod
env -u DATABASE_URL -u PGHOST -u PGPORT -u PGUSER -u PGDATABASE \
  pixi run -e prod python -c "from expense_tracker.config import database_url; database_url()"
# ValidationError: set DATABASE_URL, or all of PGUSER, PGHOST, PGPORT, PGDATABASE
```

Swap `-e prod` for `-e default` and it fails identically. This is a change from an
earlier design in which the wheel was what kept a container away from the developer's
`backend/.env`; the app no longer reads that file at all, so the guarantee no longer
depends on how it was installed.

Nothing in CI builds `prod` yet; it is verified by hand until there is an image to build.

## Configuration

Where this checkout's backend listens is written down once, in **`backend/.env`**: the
four facts `psql` and `createdb` already read, and the port `uvicorn` already reads.

```
PGHOST=127.0.0.1
PGPORT=5433
PGUSER=expense_tracker
PGDATABASE=expense_tracker
UVICORN_PORT=8000
```

Every one of them is a name the tool itself looks for, which is why no task passes
`--host`, `--port` or `--username`. `UVICORN_PORT` is the API's half of that: uvicorn's
CLI is a click command carrying `auto_envvar_prefix="UVICORN"`, so it resolves `--port`
from the environment on its own, and `poe dev` stays the same command it was. That is
what lets a second checkout run its API beside the first the same way it runs its cluster
beside the first - by editing this one file.

**The application never opens that file.** `config.py` reads the environment and nothing
else - no path is resolved in the package, and none needs to be. Loading a dotenv file is
the job of whatever *launches* the process, and exactly one thing does it here:

```sh
# .envrc
dotenv_if_exists backend/.env
```

**So `direnv allow` is a prerequisite, not a convenience.** Nothing else supplies these
names. `pixi run` reads no `.envrc` and `pixi.toml` declares no `[activation.env]`; poe
declares no `envfile`. In a shell direnv has not blessed, the app raises a
`ValidationError` naming the missing settings and every task that reaches a server aborts
on a `${PGPORT:?}` guard first - `backend-db-init` on its own, and `backend-dev` on the
one in the `db-create` behind it, before uvicorn ever binds. Nothing falls back to a
default.

CI gets the same names the same way: `setup-direnv` (v1.4.1 or newer) activates this
`.envrc` and forwards the resulting environment to `$GITHUB_ENV` for the steps after it.
That makes the action's pin in `.github/workflows/ci.yml` load-bearing - it is the first
thing to check if CI ever fails to find `PGPORT`.

One loader covers everything, including what no task wraps:

```sh
psql                                              # the local cluster, no flags
pytest tests/test_expense_postgres.py -k truncate --pdb
python -m expense_tracker.expense_loader ~/exports # a directory other than data/expenses
```

`PGHOST`, `PGPORT`, `PGUSER` and `PGDATABASE` are the variables libpq itself reads, so
`psql`, `pg_dump` and friends need no arguments, and a test run started from your editor
reaches the same cluster as `pixi run backend-test`. `pixi.toml` deliberately declares
none of this - a second copy is exactly what `backend/.env` replaces.

That split is the point rather than an implementation detail. A dotenv file is a
developer convenience, and an application that parses one has to know where it lives -
which for a wheel-installed package means deriving a path from `__file__` and getting a
directory that does not exist. Reading the environment is the 12-factor rule a container
needs, and it makes the deployed path (`DATABASE_URL` from an orchestrator) and the local
path (`backend/.env` via a launcher) the same code.

Precedence barely exists, which is the point of one loader reading one file: `backend/.env`
*overwrites* what is already in the environment, so `export PGPORT=...` in your shell does
not change the port. Only `DATABASE_URL`, which the app prefers over the four parts, sits
above it.

The DSN itself is stored nowhere. `config.py` builds it with `sqlalchemy.URL`, which
keeps the port from being written into a URL string a second time and escapes any part
containing `@`, `:` or `/` instead of emitting a URL that parses as something else.
`database_url()` returns a `URL` rather than a `str`, so `str()` and `repr()` render any
password as `***` - a DSN that reaches a log or a traceback cannot leak one.
**`DATABASE_URL` overrides the four parts wholesale**, and that is the deployment path.
**A deployment supplies its own.**

None of it has a **default**. With no `DATABASE_URL` and none of the four names in the
environment, the process refuses to start - naming every missing one - rather than
quietly dialling its own loopback. Nothing on disk can answer for them, in any
environment, because nothing on disk is consulted.

To move either port off something else has taken, edit **`backend/.env`** itself. There
is no `.env.local` layer on the backend side - one file, loaded once - and a dotenv
overwrites the ambient environment, so `export PGPORT=...` in your shell is not an
override. `PGPORT` is baked into the cluster at `initdb` time, so follow that edit with
`pixi run backend-db-reset && pixi run backend-db-init`; `UVICORN_PORT` is baked into
nothing and takes effect on the next `pixi run backend-dev`.

That leaves the file as a committed default you edit in place, which shows up as a dirty
working tree. Deliberate: a port is one of the facts this file exists to state once, and
a machine that needs a different one has genuinely changed a shared default rather than
set a private preference.

Worth knowing: `.gitignore` ignores **every** `.env` variant and names back only the two
committed defaults, so a `backend/.env.production` you create is untracked by default
rather than by memory.

The frontend has exactly one variable of its own, `VITE_API_BASE_URL` - see
[Where the API lives](#where-the-api-lives).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, Conventional Commit, and
squash-merge rules.
