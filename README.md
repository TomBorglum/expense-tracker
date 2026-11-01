# expense-tracker

A FastAPI REST API and a React + Tailwind CSS v4 single-page app, as two independent
applications.

`backend/` and `frontend/` are siblings, each owning its own tooling, tests and build.
Neither can see the other: the backend serves JSON and ships no frontend assets, the
frontend builds to its own `dist/` and reaches the API cross-origin over CORS. Either
can be built, tested and linted with the other's directory missing entirely. The root
holds only what spans both - pixi orchestrates the two toolchains, and one SonarCloud
project covers both languages.

Locally that means two processes.

```
expense-tracker/
  pixi.toml, pixi.lock          # environments, dependencies, and one `pixi run` task
                                #   per command, each forwarding to the stack below
  sonar-project.properties      # one Sonar project spanning both languages
  compose.yaml                  # the deployment: three services, two profiled
                                #   loaders, one volume
  .github/                      # CI, release-please, dependabot
  backend/
    pyproject.toml              # hatchling, ruff, pytest, basedpyright, poe tasks
    schema.sql                  # the whole schema: four tables and their indexes
    data/currencies/            # the committed exchange rates, loaded into the database
    src/expense_tracker/        # __init__ (the API), deps, config, db,
                                #   expense_repository, expense_loader
    tests/
      data/expenses/            # sample-*.yaml, the suite's fixtures
    .pgdata/                    # the local PostgreSQL cluster, gitignored
  frontend/
    package.json, pnpm-lock.yaml, pnpm-workspace.yaml
    tsconfig*.json, vite.config.ts, eslint.config.ts
    .prettierrc.json, .prettierignore
    .env                        # VITE_API_BASE_URL - where the API lives
    index.html, src/, tests/
    dist/                       # vite output, gitignored
```

## Contents

- [Prerequisites](#prerequisites)
- [Quickstart](#quickstart)
- [Routes](#routes)
- [CORS](#cors)
- [Database](#database)
- [Frontend](#frontend)
- [Development tasks](#development-tasks)
- [Environments](#environments)
- [Container images](#container-images)
- [Releases](#releases)
- [Deployment](#deployment)
- [Configuration](#configuration)
- [Contributing](#contributing)

Reference documentation lives under `docs/`: [the API](docs/api.md),
[the database](docs/database.md), [the frontend](docs/frontend.md),
[the images](docs/images.md), [releases](docs/releases.md) and
[developing here](docs/development.md).

## Prerequisites

[direnv](https://direnv.net) and [pixi](https://pixi.sh). The committed `.envrc` runs
`use pixi python`, so entering the directory provisions Python, Node and every
dependency from `pixi.toml`, and re-provisions whenever `pixi.toml` changes. Run
`direnv allow` once after cloning, which covers installation.

That includes PostgreSQL: the server is a conda-forge package like everything else, so it
arrives with the rest of the environment. See [Database](#database).

Docker is the one tool pixi does not supply. The three `*-image` tasks call for it, and so
does `compose.yaml`, which is the whole deployment; the development loop runs without
either. A machine without it gets `docker: command not found` from those tasks. See
[Container images](#container-images) and [Deployment](#deployment).

`use pixi` comes from a direnv library. On a workstation it is the one
[`wsl-cloud-init`](https://github.com/TomBorglum/wsl-cloud-init) provisions; in CI, the
`setup-direnv` action from [`TomBorglum/actions`](https://github.com/TomBorglum/actions)
installs its own copy and activates this same `.envrc`. Where that library is absent,
`direnv allow` reports the directive as an unknown command.

Its last line is `dotenv_if_exists`, which puts the database connection settings and the
port the API serves on into the environment. That is stock direnv, and the **only** thing
that puts them there, so `direnv allow` is what makes the database reachable.
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
[Loading expenses](docs/database.md#loading-expenses) and
[Loading exchange rates](docs/database.md#loading-exchange-rates) - because an empty table is a
legitimate state the API answers `200` with an empty `items` array.

Visit http://localhost:5173 and you should see the **Expenses** table, fetched from
`http://localhost:8000/api/expenses` - a genuine cross-origin request, which works only
because the API allows it (see [CORS](#cors)) - and read in turn out of the `expense`
table (see [Database](#database)). Until you run the loader it says
`No expenses match the selected criteria.`, which is the empty state.

The API alone is enough for backend work. The SPA alone runs too; it just renders its
error state until something answers on 8000.

## Routes

| Route | What it serves |
| --- | --- |
| `GET /api/expenses` | `[{"amount", "currency", "date", "category", "key"}, ...]` - the `ExpensePayload` model |
| `GET /api/expenses?currency=EUR` | The same, restated in one currency |
| `GET /api/expenses?from_date=2026-01-01&to_date=2026-01-31` | Only the expenses dated within that range |
| `GET /api/expenses?category=food&category=housing` | Only the expenses in either category, or under it - each value a category **slug** |
| `GET /api/expenses?not_category=food` | Every expense except the ones in `food`, or under it; `category_default` names the root's own sign |
| `GET /api/expenses/categories` | `[{"category", "name", "slug", "parent", "parent_slug"}, ...]` - the `CategoryPayload` model, every category at the levels asked for, once each, in path order; takes `from_level` and `to_level` |
| `GET /api/expenses/totals?period=month` | `[{"period", "from_date", "to_date", "amount", "currency", "category"}, ...]` - the `PeriodTotalPayload` model, taking `group_by`, `currency`, `from_date`, `to_date` and the three category parameters too; its body carries a `summary` beside `items` |
| `GET /api/currencies` | `[{"from_currency", "to_currency", "exchange_rate"}, ...]` - the `CurrencyPayload` model |

**Every body is an object holding `items`**, so each shape above is what fills that
array - `GET /api/currencies` answers
`{"items": [{"from_currency", "to_currency", "exchange_rate"}, ...]}`. An object is what
lets a response gain a field later without breaking a client. Totals is the one endpoint
that has taken that room, with [the range average](docs/api.md#the-range-average) beside its rows;
the other three send `items` alone.
**The key is `items`**: Zalando, whose rule puts the object there, names it that on every
collection, and one key across all four keeps `fetchList` free of per-endpoint knowledge.
A ledger narrowed to a date range is served whole, and `/api/expenses/totals` reads its
whole answer at once. A refusal body is the plain `{"detail": "..."}` object.

All four send `Cache-Control: no-store`.

Expenses come back **oldest first**, and `amount` is a **string**, not a number: the
column is `numeric(12, 2)`, JSON has no decimal type, and a decimal has no exact binary
form, so a float round trip is how a total drifts by a cent. That shape is declared once,
as the `ExpensePayload` pydantic model in `backend/src/expense_tracker/__init__.py`;
the tests parse responses back into it. An unreachable database answers
`503 {"detail": "expenses unavailable"}`, and an **empty table answers
`200 {"items": []}`** - a database nobody has run the loader against yet is a legitimate
state.

Exchange rates come back **by pair**, `from_currency` then `to_currency`, and
`exchange_rate` is a **string** for the same reason `amount` is: the column is
`numeric(18, 6)`, and an amount multiplied by a rate that made a float round trip is an
amount that has drifted. The empty table and the unreachable database behave as above,
with `{"detail": "currencies unavailable"}` as the 503 body.

The query parameters each route takes - one currency, a range of dates, one or more
categories, totals and the range average - are in [docs/api.md](docs/api.md).

## CORS

`create_app()` adds `CORSMiddleware` with `allow_origins=["*"]`, because the SPA is
served from its own origin and every call it makes is cross-origin.

`allow_credentials` is **`False`**, which is the pairing the CORS spec allows beside a
wildcard origin and the one browsers accept. This API sends no cookies and reads no
`Authorization` header. A real origin list is what the wildcard becomes the day it does.

The middleware is registered *after* the security-headers middleware, making it the
outermost of the two. That is what lets it answer a preflight `OPTIONS` itself.

## Database

PostgreSQL, holding four tables: `loaded_expense_file`, `expense` and `category`, which
together are a view of the files in `$EXPENSE_DATA_DIR`, and `currency_rate`, which is a
view of `backend/data/currencies/`. See [Loading expenses](docs/database.md#loading-expenses) and
[Loading exchange rates](docs/database.md#loading-exchange-rates).

The server is a **pixi dependency**. `postgresql` is pinned in `pixi.toml` beside python
and node, so `direnv allow` provisions it and the `db-*` tasks drive it. CI runs
`pixi run backend-db-init`, exactly what a developer runs.

### The cluster

`pixi run backend-db-create` runs `initdb` into `backend/.pgdata/` (gitignored), beside
the only code that talks to it. Three settings are baked into the generated
`postgresql.conf` rather than passed at launch, which is why `db-start` needs no flags:

| Setting | Value | Why |
| --- | --- | --- |
| `port` | `$PGPORT`, `5432` by default | PostgreSQL's own default, so a client that falls back to it finds this cluster |
| `listen_addresses` | `127.0.0.1` | Loopback only |
| `unix_socket_directories` | `/tmp` | The DSN is TCP |

The port comes from `backend/.env` (see [Configuration](#configuration)); the other two
are literals in the `db-create` task. Because all three are baked into the cluster rather
than passed at launch, changing `PGPORT` takes a `pixi run backend-db-reset` and a fresh
`backend-db-init` to take effect - `db-create` is a no-op against a `.pgdata/` that
already exists.

The superuser and the database are both named `expense_tracker`, so the DSN is
identical on every machine and on CI. Authentication is `trust`, which rests on
`listen_addresses`: this is a throwaway cluster holding public text, rebuildable at any
moment from `backend/schema.sql`. These `initdb` flags belong to this cluster alone.

All five tasks are idempotent, and the chain is `dev` depends on `db-init` depends on
`db-start` depends on `db-create` - so `pixi run backend-dev` brings the cluster up on
its way to the API and none of the five is one you normally run by hand.
`pixi run backend-db-init` is the one to reach for when you want the database up without
a server: the `postgres`-marked tests need it, and the two loaders do too.
`db-reset` throws the cluster away, which is how a change to an existing table lands,
`schema.sql` holding `IF NOT EXISTS` statements alone.

The schema, the access it grants, and how the two loaders read their files are in
[docs/database.md](docs/database.md).

## Frontend

A React 19 SPA built by vite and styled with Tailwind CSS v4, configured in CSS via
`frontend/src/styles/app.css`.

The palette and the component classes come from [daisyUI](https://daisyui.com), enabled
as a `@plugin` in that same stylesheet. One theme is named: `dim --default`, which daisyUI
binds at `:where(:root)` so it applies whatever the operating system asks for. Colours are
written by role (`bg-base-100`, `text-base-content`, `alert-error`) and the theme points
them at its own palette.

The app is dark-only by choice, and `dim` is the soft end of what daisyUI ships - the
lightest of its dark themes, a desaturated blue-grey rather than black. The theme
declares `color-scheme: dark` itself, which is what keeps browser-painted UI - scrollbars,
native `<select>` popups, form controls - in step. Because that only reaches the browser
with the stylesheet, `index.html` repeats it as `<meta name="color-scheme" content="dark">`
so the first paint carries it. Swapping the theme means checking all of that still holds.

`pixi run frontend-build` writes to `frontend/dist/`, vite's default. It is
**gitignored**. CI runs the build as a gate over the bundler, which tsc and vitest leave
untouched, and keeps nothing from it.

`GET /api/expenses` is the app's main read, fetched at runtime with
[TanStack Query](https://tanstack.com/query) in `frontend/src/api/expenses.ts` and
rendered by `frontend/src/components/ExpensesTable.tsx` as one table of date, category,
amount and currency - the category cell holding the path and then the row's `key`, the
bank's own text for it, dimmed in parentheses. The payload *shape* is written out by hand
on both sides and the two must be changed together; a mismatch shows up as a 404 or a
failed shape guard at runtime. Every field is a string on the wire - `amount` included,
because JSON has no decimal type - so the guard rejects a numeric amount. Both values are
rendered as they arrive, except that a negative amount - a credit, money coming in - is
shown as `+` in green, the sign rewritten on the string alone, so the amount and the date
reach the page as the API spelled them. The rows keep the order the API sends them in
(oldest first), and an empty ledger arrives as a 200 with an empty `items` array, which
the table shows as a row.

How the three pickers, the router and the API base URL work is in
[docs/frontend.md](docs/frontend.md).

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
| `pixi run backend-load-expenses` | `poe load-expenses` | Read `$EXPENSE_DATA_DIR/*.yaml` into the database, or nothing if that directory is absent |
| `pixi run backend-load-currencies` | `poe load-currencies` | Replace the exchange rates with `backend/data/currencies/*.tsv` |
| `pixi run backend-format` | `poe format` | Format with ruff |
| `pixi run backend-format-check` | `poe format-check` | Check formatting without writing changes |
| `pixi run backend-typecheck` | `poe typecheck` | Type-check with basedpyright (recommended) |
| `pixi run backend-image` | `poe image` | Build the API container image from the `backend` environment |
| `pixi run database-image` | `poe image` | Build the database container image: the PostgreSQL base plus `backend/schema.sql` |
| `pixi run frontend-install` | `pnpm install` | Install frontend dependencies (`--frozen-lockfile`) |
| `pixi run frontend-dev` | `pnpm run dev` | Run vite's dev server on port 5173 (hot reload) |
| `pixi run frontend-build` | `pnpm run build` | Build the frontend into `frontend/dist/` |
| `pixi run frontend-typecheck` | `pnpm run typecheck` | Type-check the frontend with tsc |
| `pixi run frontend-lint` | `pnpm run lint` | Lint the frontend with eslint (type-aware, plus CSS, `--max-warnings 0`) |
| `pixi run frontend-lint-fix` | `pnpm run lint-fix` | Auto-fix frontend lint issues |
| `pixi run frontend-test` | `pnpm run test` | Run the frontend tests (vitest) with coverage |
| `pixi run frontend-format` | `pnpm run format` | Format the frontend with prettier |
| `pixi run frontend-format-check` | `pnpm run format-check` | Check frontend formatting without writing changes |
| `pixi run frontend-image` | `pnpm run image` | Build the SPA container image from the `frontend` environment |

Every task sets its own working directory in `pixi.toml` (`backend/`, `database/` or
`frontend/`), so `pixi run <task>` behaves the same wherever you invoke it from. Each task
stays inside its own directory, and every one of them - the five `backend-db-*` included -
addresses its files by a plain relative path.

That holds when you skip the forwarder too: poe runs a task from the directory of the
`pyproject.toml` it loaded, so `poe -C backend db-start` resolves `backend/.pgdata/`
exactly as `cd backend && poe db-start` does. The *path* travels; the environment does
not. Run it from inside the worktree, where direnv has loaded, so the `${PGPORT:?}` guard
in a `db-*` task finds the port `.env` names. `pixi task list` prints this table's first
column.

CI runs every gate above on each pull request, then the SonarCloud scan. It leaves out the
two `dev` tasks, the two `-fix` variants, `backend-format`, the three `*-image` tasks, the
two loaders and the four `backend-db-*` tasks other than `backend-db-init`. The three
`*-image` tasks build rather than check, and are the only tasks reaching for a tool
outside the runner's pixi environment; `publish.yml` is what builds all three images on a
pull request. The loaders mutate data, and
`test_expense_postgres.py` and `test_currency_postgres.py` already put the committed
sample files through the real database path inside `backend-test`.

Why they are defined in two layers, how CI runs them, and editor setup are in
[docs/development.md](docs/development.md).

## Environments

`pixi.toml` declares three, on one solve-group so every shared pin is identical across
them - python and the runtime libraries between `default` and `backend`, node and pnpm
between `default` and `frontend`:

| Environment | Contains | Used by |
| --- | --- | --- |
| `default` | runtime libraries, test tooling, node, PostgreSQL, and the app **editable** | the editor, local dev, CI, every task |
| `backend` | runtime libraries and the app as a **wheel** | what the API image is built from |
| `frontend` | node and pnpm, and nothing else | what the SPA image is built from |

The install mode is the difference that matters. An editable install is a redirect to
`backend/src`: nothing is copied, so the source tree stays where it was at install time,
which is what gives a developer edit, re-run, no reinstall. A deployment gets the wheel
instead, so an image carries an artifact rather than the source tree, `backend/data/` and
`backend/tests/` and a directory layout.

So the app is declared per feature rather than in the default feature, which is why
`[dependencies]` holds runtime *libraries* only:

```toml
[feature.dev.pypi-dependencies]
expense-tracker = { path = "backend", editable = true }

[feature.backend.pypi-dependencies]
expense-tracker = { path = "backend", editable = false }
```

`backend` gets a real wheel, built by hatchling, containing `src/expense_tracker` and
nothing else. **The split is about what ships, and the settings behave the same either
way.** The app reads its settings from the environment and opens no file, so a
misconfigured process refuses to start in either environment - which you can check
directly, clearing what direnv exported first:

```sh
pixi install -e backend
env -u DATABASE_URL -u PGHOST -u PGPORT -u PGUSER -u PGDATABASE \
  pixi run -e backend python -c "from expense_tracker.config import database_url; database_url()"
# ValidationError: set DATABASE_URL, or all of PGUSER, PGHOST, PGPORT, PGDATABASE
```

Swap `-e backend` for `-e default` and it fails identically: the app reads the
environment, whichever way it was installed.

`frontend` is a *toolchain* rather than a payload. It holds node and pnpm, it runs
`tsc -b && vite build`, and the SPA image ships `dist/` behind nginx instead. It is also
the only environment that declares `no-default-feature = true`: `[dependencies]` **is**
the default feature and is folded into every environment that does not opt out, so the
flag is what holds this one to node and pnpm. That leanness is what lets the SPA image
build from a context with no backend source in it, which in turn keeps a backend commit
from invalidating its layer cache.

`pixi run frontend-build` from a blessed shell still resolves through `default`, which is
what the editor and CI use; `pixi run -e frontend frontend-build` is the same build in the
lean environment, and the two produce byte-identical output.

Both are built by `release.yml` on a published release, and both can be built by hand the
same way CI builds them - `pixi run backend-image` and `pixi run frontend-image`, below.
The database image is published beside them but belongs to neither environment; it is
built from no pixi environment at all.

## Container images

Three images, each taking the repository root as its build context and each declaring
itself in a `docker-bake.hcl` beside its Dockerfile - the context, the Dockerfile and the
two OCI values only that image knows - so both the local task below and `release.yml`
build a target out of that file rather than passing those settings on a command line. All
three are published to Docker Hub by `release.yml`; see [docs/releases.md](docs/releases.md).

Two of them are one per stack, built from the lean pixi environment of the same name. The
database image is the odd one out and installs no environment at all: it is the official
PostgreSQL image plus `backend/schema.sql`, so it has no builder stage and carries nothing
of the lock.

How each of the three is built is in [docs/images.md](docs/images.md).

## Releases

Tagged releases are cut by release-please and published to Docker Hub by
`.github/workflows/release.yml`. The whole path - the four jobs, the credential, the
vulnerability gate and the AWS objects behind it - is in
[docs/releases.md](docs/releases.md).

## Deployment

**`compose.yaml` is the deployment.** There is no chart, no manifest and no deploy script
beside it: one file describing the three images as three services, plus the two loaders
behind a `load` profile, on one network with one volume. The target is a single host - a
laptop - and `docker compose up` is the whole operation.

Every service names an `image:` and none a `build:`. That is a hard rule rather than a
preference: `docker compose publish` refuses a service carrying `build` without `image`,
and a release publishes this file as an OCI artifact to be loaded on a machine holding no
checkout, where there is nothing to build from anyway. **That is the deployment the file
is for**; running it from this checkout is the development case.

### The services

| Service | Port | What it is |
|---|---|---|
| `database` | none | The database image, which carries `schema.sql` and applies it on an empty data directory. Trust auth, reachable on the compose network alone. |
| `backend` | `8000` | The API. Published because the **browser** calls it. |
| `frontend` | `8080` | The SPA, nginx serving the bundle, with the API origin substituted at container start. |
| `load-currencies` | - | `profiles: ["load"]`. One shot, over the API image, reading `/currencies`. |
| `load-expenses` | - | `profiles: ["load"]`. One shot, over the API image, reading `/expenses`. |

The database publishes **no port**, which is what makes trust auth safe - the same bargain
`db-create` strikes with `--set=listen_addresses=127.0.0.1` for the local cluster, and the
reason `docker compose up` needs no arguments and nothing published holds a credential.
Adding a `ports:` entry to that service would publish an unauthenticated superuser to the
host.

`backend` waits on `database` being **healthy**, not merely started. The API answers `200`
with an empty `items` array against an empty table, so a database still applying its schema
would not fail loudly - it would serve plausible, wrong, empty answers. The healthcheck is
`pg_isready -h 127.0.0.1`, and the `-h` is load-bearing: without it `pg_isready` uses the
unix socket, which the entrypoint's init-phase temporary server answers while the schema is
still being applied. That temporary server is socket-only, so over TCP readiness and init
completing are the same moment.

Neither `backend` nor `frontend` declares a healthcheck. The API image is distroless and
holds no shell, no curl and no wget, so there is nothing in it to probe itself with, and
adding one would mean adding a binary to a published image to serve compose.

### Running it from a release

A release publishes the file itself, so a host needs **no checkout and no clone** - one
directory holding one `.env`:

```sh
cat > .env <<'EOF'
EXPENSE_TRACKER_CURRENCIES_DIR=/home/you/somewhere/currencies
EXPENSE_DATA_DIR=/home/you/projects/expense-data/data
EOF

stack=oci://docker.io/tomborglum/expense-tracker:2.1.0
docker compose -f "$stack" up -d -y
printf 'y\n' | docker compose -f "$stack" run --rm -T load-currencies
printf 'y\n' | docker compose -f "$stack" run --rm -T load-expenses
```

That `.env` is the only state the host keeps. The images come out of the artifact pinned
by digest, so neither `EXPENSE_TRACKER_IMAGE_PREFIX` nor `EXPENSE_TRACKER_VERSION` has any
effect here - the artifact's tag is what selects a version, and [The published
stack](docs/releases.md#the-published-stack) says why.

Three things about the `oci://` path are worth knowing before the first run, because none
of them is guessable from the compose documentation and all three were measured:

- **A relative bind source resolves against compose's download cache**, not the current
  directory. The two defaults in the file are relative and correct for a checkout, so a
  host holding none must name both directories **absolutely**, as the `.env` above does.
  `create_host_path: false` is what turns a missing one into a container that refuses to
  start rather than an empty mount.
- **Loading an `oci://` file prompts** for the interpolation variables and the sources
  they resolved from, every time. `up` takes `-y` for it. **`run` has no such flag**, so
  it wants a `y` typed - or `printf 'y\n' |` ahead of it with `-T`, which is what a
  script needs and what the commands above use.
- **`COMPOSE_FILE` cannot carry an `oci://` reference.** Compose splits that variable on
  `:`, so the value becomes three nonexistent paths. Pass `-f oci://...` instead, or set
  `COMPOSE_PATH_SEPARATOR=,` first.

### Running it from this checkout

The three image references default to the local `:dev` tags, which are exactly what the
`*-image` tasks build, so a checkout needs no variables at all:

```sh
pixi run backend-image && pixi run database-image && pixi run frontend-image
docker compose up -d
```

The SPA is then on <http://localhost:8080> and the API on <http://localhost:8000>. **8000
is also the port `pixi run backend-dev` binds**, so the two cannot run at once; stop one
before starting the other, or move the stack with the variables below.

Which images it runs is two variables:

```sh
EXPENSE_TRACKER_IMAGE_PREFIX   # default `expense-tracker`
EXPENSE_TRACKER_VERSION        # default `dev`
```

They compose as `<prefix>-<service>:<version>`, which is the shape
[Releases](#releases) composes published names in, so pointing the stack at a release is
one setting and **no published name is written down in this file either**:

```sh
EXPENSE_TRACKER_IMAGE_PREFIX=<namespace>/expense-tracker \
EXPENSE_TRACKER_VERSION=2.1.0 docker compose up -d
```

Where the browser should reach the API is a third, `EXPENSE_TRACKER_API_BASE_URL`,
defaulting to `http://localhost:8000`. It cannot be `http://backend:8000`: the bundle runs
in the host's browser, where that name does not resolve. The SPA image's entrypoint refuses
an absent value and one carrying a path, so a mistake here stops that container rather than
serving an app that reaches nothing. Moving the API off host port 8000 means editing the
`ports:` entry and setting this variable to match.

### Loading data

The two loaders are one-shot, so `run --rm` is the precise form and reaches a profiled
service without naming the profile:

```sh
docker compose run --rm load-currencies
docker compose run --rm load-expenses
```

`docker compose --profile load up -d` is the other form, and brings the whole stack up with
both loaders alongside it.

The loaders keep the differing reload shapes [Loading
expenses](docs/database.md#loading-expenses) and [Loading exchange rates](docs/database.md#loading-exchange-rates)
describe: currencies replace the whole rate table every run, and expenses are append-only
with a ledger that **refuses** a file whose contents changed.
So a reclassified month is not cured by re-running `load-expenses`. It is cured by throwing
the database away:

```sh
docker compose down -v                     # drop the volume: this IS the wipe
docker compose up -d                       # a fresh volume re-runs schema.sql
docker compose run --rm load-currencies
docker compose run --rm load-expenses
```

`down -v` drops the one named volume, the image's `initdb.d` re-applies `schema.sql` on the
empty data directory it leaves behind, and both loaders start from nothing. **No backend
code exists for that sequence and none is needed** - which is the whole reason the schema
travels in the image rather than being applied by a step of its own.

### The two directories it mounts

```sh
EXPENSE_TRACKER_CURRENCIES_DIR   # default ./backend/data/currencies
EXPENSE_DATA_DIR                 # default ./backend/tests/data/expenses
```

Both are mounted read-only, and both must be readable by **uid 65532**, which is what the
API image runs as.

`EXPENSE_DATA_DIR` is the name `backend/.env` already carries, so **a blessed shell points
`load-expenses` at the private expense repository with no further setting** - the committed
fixture default applies only where that variable is unset. To load the synthetic fixtures
in a shell that has it, override it for the one command.

Both mounts are declared in long syntax carrying **`create_host_path: false`**, and that is
the one setting here with data loss behind it. Compose creates a missing bind source by
default, and the currency loader replaces the whole rate table from whatever it finds, so an
empty directory **deletes every rate** and reports `0 files read` with exit 0. Refusing to
create the path turns a mistyped directory into a container that does not start:

```
Error response from daemon: invalid mount config for type "bind":
bind source path does not exist: /...
```

The project name is pinned to `expense-tracker` in the file rather than taken from the
directory, so the volume is `expense-tracker_database-data` wherever the file is loaded
from - a checkout, a scratch directory holding one `.env`, or an `oci://` reference - and
`down -v` reaches the same one every time.

## Configuration

Where this checkout's backend listens is written down once, in **`backend/.env`**: the
four facts `psql` and `createdb` already read, the port `uvicorn` already reads, and where
the expense files are.

```
PGHOST=127.0.0.1
PGPORT=5432
PGUSER=expense_tracker
PGDATABASE=expense_tracker
UVICORN_PORT=8000
EXPENSE_DATA_DIR=$HOME/projects/expense-data/data
```

`EXPENSE_DATA_DIR` is the odd one out, and knowingly so: it is the only value here that is
a fact about a *machine* rather than about the project, because it points outside the
checkout at the `data/` directory inside a clone of the private data repository. direnv
expands `$HOME` as it loads the file, so the committed default is a real path wherever the
clone sits beside this one; anywhere else, set it in **`backend/.env.local`**, which
`.envrc` loads after `backend/.env` and which is gitignored, so no tracked file carries one
machine's layout. Unset and set-but-absent differ: unset aborts on the guard, and
set-but-absent loads nothing and succeeds, which is what tells a machine without the data
repository from one whose shell was never blessed. See
[Loading expenses](docs/database.md#loading-expenses).

Every one of them is a name the tool itself looks for, which is why no task passes
`--host`, `--port` or `--username`. `UVICORN_PORT` is the API's half of that: uvicorn's
CLI is a click command carrying `auto_envvar_prefix="UVICORN"`, so it resolves `--port`
from the environment on its own, and `poe dev` stays the same command it was. That is
what lets a second checkout run its API beside the first the same way it runs its cluster
beside the first - by editing this one file.

**The application never opens that file.** `config.py` reads the environment and nothing
else, resolving no path in the package. Loading a dotenv file is the job of whatever
*launches* the process, and `.envrc` is the one launcher that does it here:

```sh
# .envrc
dotenv_if_exists backend/.env
dotenv_if_exists backend/.env.local
```

**So `direnv allow` is a prerequisite.** `.envrc` is the single source of these names:
`pixi run` reads no `.envrc` and `pixi.toml` declares no `[activation.env]`; poe declares
no `envfile`. In a shell direnv has not blessed, the app raises a `ValidationError` naming
the missing settings and every task that reaches a server aborts on a `${PGPORT:?}` guard
first - `backend-db-init` on its own, and `backend-dev` on the one in the `db-create`
behind it, before uvicorn ever binds.

CI gets the same names the same way: `setup-direnv` activates this `.envrc` and forwards
the resulting environment to `$GITHUB_ENV` for the steps after it.
`.github/workflows/ci.yml` calls it directly;
`.github/workflows/update-pixi-dependencies.yml` reaches it through the reusable workflow
it delegates to, which activates this same `.envrc` for the pixi version its `use pixi`
line pins. It is the first thing to check if CI ever fails to find `PGPORT`.

One loader covers everything, including what no task wraps:

```sh
psql                                              # the local cluster, no flags
pytest tests/test_expense_postgres.py -k truncate --pdb
python -m expense_tracker.expense_loader ~/exports # a directory other than the configured one
```

`PGHOST`, `PGPORT`, `PGUSER` and `PGDATABASE` are the variables libpq itself reads, so
`psql`, `pg_dump` and friends need no arguments, and a test run started from your editor
reaches the same cluster as `pixi run backend-test`. `backend/.env` is the one place these
names are written, and `pixi.toml` declares none of them.

That split is what makes the deployed path and the local path one code path: the app reads
the environment, as 12-factor has it and as a container supplies it, and a launcher is what
turns a dotenv file into that environment. A wheel-installed package then needs no project
directory to find, deriving no path from `__file__`.

Precedence is short: `backend/.env` *overwrites* what is already in the environment, so
`export PGPORT=...` in your shell leaves the port as the file states it, and
`backend/.env.local` overwrites that in turn. Above both sits `DATABASE_URL`, which the app
prefers over the four parts.

The DSN itself is built per call. `config.py` assembles it with `sqlalchemy.URL`, which
takes the port as a number of its own and escapes any part containing `@`, `:` or `/`.
`database_url()` returns a `URL` rather than a `str`, so `str()` and `repr()` render any
password as `***`, keeping a DSN that reaches a log or a traceback free of one.
**`DATABASE_URL` overrides the four parts wholesale**, and that is the deployment path.
**A deployment supplies its own.**

Every one of them is **required**. With no `DATABASE_URL` and none of the four names in the
environment, the process refuses to start and names every missing one. The environment is
the whole input, in every environment.

To move either port off something else has taken, edit **`backend/.env`** itself, a dotenv
overwriting the ambient environment. `PGPORT` is baked into the cluster at `initdb` time,
so follow that edit with `pixi run backend-db-reset && pixi run backend-db-init`;
`UVICORN_PORT` takes effect on the next `pixi run backend-dev`.

That leaves the file as a committed default you edit in place, which shows up as a dirty
working tree. A port is one of the facts this file exists to state once, so moving it
changes a shared default; `backend/.env.local` is where a value that names a machine goes.

Worth knowing: `.gitignore` ignores **every** `.env` variant and names back only the two
committed defaults, so a `backend/.env.production` you create is untracked as a rule.

The frontend has exactly one variable of its own, `VITE_API_BASE_URL` - see
[Where the API lives](docs/frontend.md#where-the-api-lives).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, Conventional Commit, and
squash-merge rules. To report a security issue, see
[`SECURITY.md`](SECURITY.md) - please do not open a public issue for one.

## License

MIT. See [`LICENSE`](LICENSE).
