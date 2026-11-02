# expense-tracker

A FastAPI REST API and a React + Tailwind CSS v4 single-page app, as two independent
applications.

`backend/` and `frontend/` are siblings, each owning its own tooling, tests and build.
Neither can see the other: the backend serves JSON and ships no frontend assets, the
frontend builds to its own `dist/` and reaches the API cross-origin over CORS. Either can
be built, tested and linted with the other's directory missing entirely, and the root
holds only what spans both. Locally that means two processes.

```
expense-tracker/
  pixi.toml, pixi.lock          # environments, and one `pixi run` task per command
  sonar-project.properties      # one Sonar project spanning both languages
  compose.yaml                  # the deployment: three services, two profiled loaders
  .github/                      # CI, release-please, dependabot
  docs/                         # reference for each subsystem
  backend/
    pyproject.toml              # ruff, pytest, basedpyright, poe tasks
    schema.sql                  # the whole schema: four tables and their indexes
    data/currencies/            # the committed exchange rates
    src/expense_tracker/        # the API, its loaders and its repositories
    tests/data/expenses/        # sample-*.yaml, the suite's fixtures
    .pgdata/                    # the local PostgreSQL cluster, gitignored
  frontend/
    package.json, vite.config.ts, eslint.config.ts, tsconfig*.json
    .env                        # VITE_API_BASE_URL, where the API lives
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

Reference documentation lives under `docs/`: [the API](docs/api.md), [the
database](docs/database.md), [the frontend](docs/frontend.md), [the
images](docs/images.md), [releases](docs/releases.md) and [developing
here](docs/development.md).

## Prerequisites

[direnv](https://direnv.net) and [pixi](https://pixi.sh). The committed `.envrc` runs `use
pixi python`, so entering the directory provisions Python, Node and every dependency from
`pixi.toml`, and re-provisions whenever `pixi.toml` changes. Run `direnv allow` once after
cloning, which covers installation.

PostgreSQL arrives with it. The server is a conda-forge package pinned in `pixi.toml`. See
[Database](#database).

Docker is the one tool pixi does not supply. The three `*-image` tasks call for it, and so
does `compose.yaml`, which is the whole deployment; the development loop runs without
either. A machine without it gets `docker: command not found` from those tasks. See
[Container images](#container-images) and [Deployment](#deployment).

`use pixi` comes from a direnv library. On a workstation it is the one
[`wsl-cloud-init`](https://github.com/TomBorglum/wsl-cloud-init) provisions; in CI, the
`setup-direnv` action from [`TomBorglum/actions`](https://github.com/TomBorglum/actions)
installs its own copy and activates this same `.envrc`. Where that library is absent,
`direnv allow` reports the directive as an unknown command.

`.envrc`'s last line is `dotenv_if_exists`, which puts the database connection settings
and the port the API serves on into the environment. That is stock direnv, and the
**only** thing that puts them there, so `direnv allow` is what makes the database
reachable. See [Configuration](#configuration).

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
launches the API. Every part of that is idempotent, so it is the same one command on the
first day and on any later one. The `backend-db-*` tasks drive the cluster on its own; see
[Database](#database). Loading data is a separate, explicit step:
`pixi run backend-load-expenses` and `pixi run backend-load-currencies`, both under
[docs/database.md](docs/database.md#loading-expenses). An empty table is a legitimate
state, which the API answers `200` with an empty `items` array.

http://localhost:5173 then renders the **Expenses** table, fetched from
`http://localhost:8000/api/expenses` cross-origin, which works only because the API allows
it (see [CORS](#cors)). Before the loader has run it reads `No expenses match the selected
criteria.`, the empty state.

The API alone is enough for backend work; the SPA renders its error state until something
answers on 8000.

## Routes

| Route | What it serves |
| --- | --- |
| `GET /api/expenses` | The `ExpensePayload` model, one object per expense |
| `GET /api/expenses?currency=EUR` | The same, restated in one currency |
| `GET /api/expenses?from_date=&to_date=` | Only the expenses within that range |
| `GET /api/expenses?category=<slug>` | Only that category and what is under it |
| `GET /api/expenses?not_category=<slug>` | Every expense but that subtree |
| `GET /api/expenses/categories` | `CategoryPayload`, each category once, in path order |
| `GET /api/expenses/totals?period=month` | `PeriodTotalPayload`, plus a `summary` |
| `GET /api/currencies` | The `CurrencyPayload` model, one object per rate |

**Every body is an object holding `items`**, so each shape above is what fills that array.
`GET /api/currencies` answers `{"items": [{"from_currency", "to_currency",
"exchange_rate"}, ...]}`. Totals is the one endpoint carrying a second key beside it, [the
range average](docs/api.md#the-range-average). One key across all four keeps `fetchList`
free of per-endpoint knowledge. A refusal body is the plain `{"detail": "..."}` object.

All four send `Cache-Control: no-store`.

Expenses come back **oldest first**, and `amount` is a **string**, not a number: the
column is `numeric(12, 2)`, JSON has no decimal type, and a float round trip is how a
total drifts by a cent. That shape is declared once, as the `ExpensePayload` pydantic
model in `backend/src/expense_tracker/__init__.py`; the tests parse responses back into
it. An unreachable database answers `503 {"detail": "expenses unavailable"}`. An **empty
table answers `200 {"items": []}`**, a database nobody has run the loader against yet
being a legitimate state.

Exchange rates come back **by pair**, `from_currency` then `to_currency`, and
`exchange_rate` is a **string** for the same reason `amount` is: the column is
`numeric(18, 6)`, and an amount multiplied by a rate that made a float round trip has
drifted. The empty table and the unreachable database behave as above, with `{"detail":
"currencies unavailable"}` as the 503 body.

The query parameters each route takes, one currency, a range of dates, one or more
categories, totals and the range average, are in [docs/api.md](docs/api.md).

## CORS

`create_app()` adds `CORSMiddleware` with `allow_origins=["*"]`, because the SPA is served
from its own origin and every call it makes is cross-origin.

`allow_credentials` is **`False`**, which is the pairing the CORS spec allows beside a
wildcard origin and the one browsers accept. This API sends no cookies and reads no
`Authorization` header. Sending either means replacing the wildcard with a real origin
list.

The middleware is registered *after* the security-headers middleware, making it the
outermost of the two. That is what lets it answer a preflight `OPTIONS` itself.

## Database

PostgreSQL, holding four tables: `loaded_expense_file`, `expense` and `category`, which
together are a view of the files in `$EXPENSE_DATA_DIR`, and `currency_rate`, which is a
view of `backend/data/currencies/`. See [Loading
expenses](docs/database.md#loading-expenses) and [Loading exchange
rates](docs/database.md#loading-exchange-rates).

The server is a **pixi dependency**. `postgresql` is pinned in `pixi.toml` beside python
and node, so `direnv allow` provisions it and the `db-*` tasks drive it. CI runs `pixi run
backend-db-init`, exactly what a developer runs.

### The cluster

`pixi run backend-db-create` runs `initdb` into `backend/.pgdata/` (gitignored). Three
settings are baked into the generated `postgresql.conf` rather than passed at launch,
which is why `db-start` needs no flags:

| Setting | Value | Why |
| --- | --- | --- |
| `port` | `$PGPORT`, default `5432` | PostgreSQL's default; a fallback client hits it |
| `listen_addresses` | `127.0.0.1` | Loopback only |
| `unix_socket_directories` | `/tmp` | The DSN is TCP |

The port comes from `backend/.env` (see [Configuration](#configuration)); the other two
are literals in the `db-create` task. Because all three are baked in rather than passed at
launch, **changing `PGPORT` takes a `pixi run backend-db-reset` and a fresh
`backend-db-init`**. `db-create` is a no-op against a `.pgdata/` that already exists.

The superuser and the database are both named `expense_tracker`, so the DSN is identical
on every machine and on CI. Authentication is `trust`, which rests on `listen_addresses`:
this is a throwaway cluster holding public text, rebuildable at any moment from
`backend/schema.sql`.

All five tasks are idempotent, and the chain is `dev` -> `db-init` -> `db-start` ->
`db-create`, so `pixi run backend-dev` brings the cluster up on its way to the API. `pixi
run backend-db-init` brings the database up without a server: the `postgres`-marked tests
need it, and so do the two loaders. `db-reset` throws the cluster away, which is how a
change to an existing table lands.

The schema, the access it grants, and how the two loaders read their files are in
[docs/database.md](docs/database.md).

## Frontend

A React 19 SPA built by vite and styled with Tailwind CSS v4, configured in CSS via
`frontend/src/styles/app.css`.

The palette and the component classes come from [daisyUI](https://daisyui.com), enabled as
a `@plugin` in that same stylesheet. One theme is named: `dim --default`, which daisyUI
binds at `:where(:root)` so it applies whatever the operating system asks for. Colours are
written by role (`bg-base-100`, `text-base-content`, `alert-error`) and the theme points
them at its own palette.

The app is **dark-only**. The theme declares `color-scheme: dark` itself, which keeps
browser-painted UI in step: scrollbars, native `<select>` popups and form controls.
`index.html` repeats it as `<meta name="color-scheme" content="dark">` so the first paint
carries it. Swapping the theme means checking all of that still holds.

`pixi run frontend-build` writes to `frontend/dist/`, vite's default, which is
**gitignored**; CI runs the build as a gate over the bundler and keeps nothing from it.

`GET /api/expenses` is the app's main read, fetched with [TanStack
Query](https://tanstack.com/query) and rendered by
`frontend/src/components/ExpensesTable.tsx` as one table of date, category, amount and
currency. The category cell holds the path and then the row's `key`, dimmed in
parentheses. **The payload shape is written out by hand on both sides and the two must be
changed together**; a mismatch shows up as a 404 or a failed shape guard at runtime. Every
field is a string on the wire, so the guard rejects a numeric amount. A negative amount is
a credit, shown as `+` in green, the sign rewritten on the string alone. Rows keep the
order the API sends them in, and an empty ledger shows as a row.

How the three pickers, the router and the API base URL work is in
[docs/frontend.md](docs/frontend.md).

## Development tasks

`pixi run <task>` is the entry point, and the same command CI runs; a `backend-*` task
forwards to `poe <name>`, a `frontend-*` task to `pnpm run <name>`.

| Task | What it does |
| --- | --- |
| `backend-db-init` | Create, start and schema-load the local database |
| `backend-db-create` | `initdb` a cluster into `backend/.pgdata/`, if absent |
| `backend-db-start` | Start the cluster on `$PGHOST:$PGPORT`, if it is down |
| `backend-db-stop` | Stop the cluster; succeeds if already stopped |
| `backend-db-reset` | Stop the cluster and delete `backend/.pgdata/` |
| `backend-dev` | Start the database if down, then the API on uvicorn |
| `backend-test` | Run the test suite with coverage |
| `backend-lint` | ruff, then the import graph with import-linter |
| `backend-lint-fix` | Auto-fix lint issues (ruff only) |
| `backend-load-expenses` | Read `$EXPENSE_DATA_DIR/*.yaml` into the database |
| `backend-load-currencies` | Replace the rates from `backend/data/currencies/*.tsv` |
| `backend-format` | Format with ruff |
| `backend-format-check` | Check formatting without writing changes |
| `backend-typecheck` | Type-check with basedpyright |
| `backend-image` | Build the API image from the `backend` environment |
| `database-image` | Build the database image: PostgreSQL plus `schema.sql` |
| `frontend-install` | Install dependencies (`--frozen-lockfile`) |
| `frontend-dev` | Run vite's dev server on port 5173 (hot reload) |
| `frontend-build` | Build the frontend into `frontend/dist/` |
| `frontend-typecheck` | Type-check with tsc |
| `frontend-lint` | eslint, type-aware, plus CSS, `--max-warnings 0` |
| `frontend-lint-fix` | Auto-fix lint issues |
| `frontend-test` | Run the tests (vitest) with coverage |
| `frontend-format` | Format with prettier |
| `frontend-format-check` | Check formatting without writing changes |
| `frontend-image` | Build the SPA image from the `frontend` environment |

Every task sets its own working directory in `pixi.toml`, so `pixi run <task>` behaves the
same from any directory, and each addresses its files by a plain relative path, the five
`backend-db-*` included.

That holds without the forwarder too: poe runs a task from the directory of the
`pyproject.toml` it loaded, so `poe -C backend db-start` resolves `backend/.pgdata/`
exactly as `cd backend && poe db-start` does. The *path* travels; the environment does
not. Run it from inside the worktree, where direnv has loaded, so the `${PGPORT:?}` guard
finds the port `.env` names. `pixi task list` prints this table's first column.

CI runs every gate above on each pull request, then the SonarCloud scan. It leaves out the
two `dev` tasks, the two `-fix` variants, `backend-format`, the three `*-image` tasks, the
two loaders and every `backend-db-*` task but `backend-db-init`. The image tasks build
rather than check, `publish.yml` being what builds all three on a pull request, and the
loaders mutate data that `backend-test` already puts through the real database path.

Why they are defined in two layers, how CI runs them, and editor setup are in
[docs/development.md](docs/development.md).

## Environments

`pixi.toml` declares three, on one solve-group so every shared pin is identical across
them: python and the runtime libraries between `default` and `backend`, node and pnpm
between `default` and `frontend`.

| Environment | Contains | Used by |
| --- | --- | --- |
| `default` | all tooling, the app **editable** | editor, local dev, CI, every task |
| `backend` | runtime libraries, the app a **wheel** | the API image |
| `frontend` | node and pnpm, nothing else | the SPA image |

**The three differ in install mode.** An editable install is a redirect to `backend/src`:
nothing is copied, so an edit takes no reinstall. A deployment gets a wheel instead, so an
image carries an artifact rather than the source tree, `backend/data/`, `backend/tests/`
and a directory layout. The settings behave the same either way, the app reading the
environment and opening no file, so a misconfigured process refuses to start in both.

`frontend` is a *toolchain* rather than a payload, and the only environment declaring
`no-default-feature = true`, which is what holds it to node and pnpm. The SPA image
therefore builds from a context with no backend source in it, which keeps a backend commit
from invalidating its layer cache. `pixi run frontend-build` from a blessed shell resolves
through `default`, which is what the editor and CI use; `pixi run -e frontend
frontend-build` is the same build in the lean environment, and the two produce
byte-identical output.

## Container images

Three images, each taking the repository root as its build context and each declaring
itself in a `docker-bake.hcl` beside its Dockerfile, so the local task and `release.yml`
build the same target. All three are published to Docker Hub on a release; see
[docs/releases.md](docs/releases.md).

Two of them are one per stack, built from the lean pixi environment of the same name. The
database image installs no environment at all: it is the official PostgreSQL image plus
`backend/schema.sql`.

How each of the three is built is in [docs/images.md](docs/images.md).

## Releases

Tagged releases are cut by release-please and published to Docker Hub by
`.github/workflows/release.yml`. The whole path, the four jobs, the credential, the
vulnerability gate and the AWS objects behind it, is in
[docs/releases.md](docs/releases.md).

## Deployment

**`compose.yaml` is the deployment.** There is no chart, no manifest and no deploy script
beside it: one file describing the three images as three services, plus the two loaders
behind a `load` profile, on one network with one volume. The target is a single host, a
laptop, and `docker compose up` is the whole operation.

Every service names an `image:` and none a `build:`. `docker compose publish` refuses a
service carrying `build` without `image`, and a release publishes this file as an OCI
artifact to be loaded on a machine holding no checkout. **That is the deployment the file
is for**; this checkout is the development case.

### The services

| Service | Port | What it is |
|---|---|---|
| `database` | none | Carries `schema.sql` and applies it to an empty data dir |
| `backend` | `8000` | The API. Published because the **browser** calls it. |
| `frontend` | `8080` | nginx serving the bundle, API origin substituted at start |
| `load-currencies` | - | `profiles: ["load"]`. One shot, API image, `/currencies` |
| `load-expenses` | - | `profiles: ["load"]`. One shot, API image, `/expenses` |

The database publishes **no port**, which is what makes trust auth safe, the same bargain
`db-create` strikes with `--set=listen_addresses=127.0.0.1` locally. **Adding a `ports:`
entry to that service would publish an unauthenticated superuser to the host.**

`backend` waits on `database` being **healthy**, not merely started: the API answers `200`
with an empty `items` array against an empty table, so a database still applying its
schema would serve empty answers rather than failing. The healthcheck is `pg_isready -h
127.0.0.1`. Without the `-h`, `pg_isready` uses the unix socket, which the entrypoint's
init-phase temporary server answers while the schema is still being applied. That server
is socket-only, so over TCP readiness and init completing are the same moment.

Neither `backend` nor `frontend` declares a healthcheck: the API image is distroless and
holds no shell, curl or wget to probe itself with.

### Running it from a release

A release publishes the file itself, so a host needs **no checkout and no clone**, one
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
effect here. The artifact's tag is what selects a version, and [The published
stack](docs/releases.md#the-published-stack) says why.

- **A relative bind source resolves against compose's download cache**, not the current
  directory. The two defaults in the file are relative and correct for a checkout, so a
  host holding none must name both directories **absolutely**, as the `.env` above does.
  `create_host_path: false` is what turns a missing one into a container that refuses to
  start rather than an empty mount.
- **Loading an `oci://` file prompts** for the interpolation variables and the sources
  they resolved from, every time. `up` takes `-y` for it. **`run` has no such flag**, so
  it wants a `y` typed, or `printf 'y\n' |` ahead of it with `-T`, which is what a script
  needs and what the commands above use.
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

Which images it runs is two variables, `EXPENSE_TRACKER_IMAGE_PREFIX` (default
`expense-tracker`) and `EXPENSE_TRACKER_VERSION` (default `dev`), composing as
`<prefix>-<service>:<version>`, the shape [Releases](#releases) composes published names
in. Pointing the stack at a release is one setting, and **no published name is written
down in this file either**:

```sh
EXPENSE_TRACKER_IMAGE_PREFIX=<namespace>/expense-tracker \
EXPENSE_TRACKER_VERSION=2.1.0 docker compose up -d
```

Where the browser should reach the API is a third, `EXPENSE_TRACKER_API_BASE_URL`,
defaulting to `http://localhost:8000`. **It cannot be `http://backend:8000`**: the bundle
runs in the host's browser, where that name does not resolve. The SPA image's entrypoint
refuses an absent value and one carrying a path, so a mistake here stops that container
rather than serving an app that reaches nothing. Moving the API off host port 8000 means
editing the `ports:` entry and setting this variable to match.

### Loading data

The two loaders are one-shot, so `run --rm` is the precise form and reaches a profiled
service without naming the profile:

```sh
docker compose run --rm load-currencies
docker compose run --rm load-expenses
```

`docker compose --profile load up -d` is the other form, and brings the whole stack up
with both loaders alongside it.

The loaders keep the differing reload shapes
[docs/database.md](docs/database.md#loading-expenses) describes: currencies replace the
whole rate table every run, and expenses are append-only with a ledger that **refuses** a
file whose contents changed. A reclassified month is not cured by re-running
`load-expenses`, but by throwing the database away:

```sh
docker compose down -v                     # drop the volume: this IS the wipe
docker compose up -d                       # a fresh volume re-runs schema.sql
docker compose run --rm load-currencies
docker compose run --rm load-expenses
```

`down -v` drops the one named volume, the image's `initdb.d` re-applies `schema.sql` on
the empty data directory it leaves behind, and both loaders start from nothing. **No
backend code exists for that sequence and none is needed**, which is why the schema
travels in the image.

### The two directories it mounts

```sh
EXPENSE_TRACKER_CURRENCIES_DIR   # default ./backend/data/currencies
EXPENSE_DATA_DIR                 # default ./backend/tests/data/expenses
```

Both are mounted read-only, and both must be readable by **uid 65532**, which is what the
API image runs as.

`EXPENSE_DATA_DIR` is the name `backend/.env` already carries, so **a blessed shell points
`load-expenses` at the private expense repository with no further setting**. The committed
fixture default applies only where that variable is unset.

Both mounts carry **`create_host_path: false`**. Compose creates a missing bind source by
default, and the currency loader replaces the whole rate table from whatever it finds, so
an empty directory **deletes every rate** and reports `0 files read` with exit 0. Refusing
to create the path turns a mistyped directory into a container that does not start:

```
Error response from daemon: invalid mount config for type "bind":
bind source path does not exist: /...
```

The project name is pinned to `expense-tracker` in the file rather than taken from the
directory, so the volume is `expense-tracker_database-data` wherever the file is loaded
from, a checkout, a scratch directory holding one `.env`, or an `oci://` reference, and
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

`EXPENSE_DATA_DIR` is the only value here that is a fact about a *machine* rather than the
project, pointing outside the checkout at a clone of the private data repository. direnv
expands `$HOME` as it loads the file, so the committed default is a real path wherever
that clone sits beside this one; anywhere else, set it in **`backend/.env.local`**, which
`.envrc` loads afterwards and which is gitignored. Unset and set-but-absent differ: unset
aborts on the guard, set-but-absent loads nothing and succeeds. That is what tells a
machine without the data repository from one whose shell was never blessed. See [Loading
expenses](docs/database.md#loading-expenses).

Every one of them is a name the tool itself looks for, which is why no task passes
`--host`, `--port` or `--username`. `UVICORN_PORT` is the API's half of that: uvicorn's
CLI carries `auto_envvar_prefix="UVICORN"`, so it resolves `--port` from the environment
on its own. A second checkout therefore runs its API and its cluster beside the first by
editing this one file.

**The application never opens that file.** `config.py` reads the environment and nothing
else. Loading a dotenv file is the job of whatever *launches* the process, and `.envrc` is
the one launcher that does it here:

```sh
# .envrc
dotenv_if_exists backend/.env
dotenv_if_exists backend/.env.local
```

**So `direnv allow` is a prerequisite.** `.envrc` is the single source of these names:
`pixi run` reads no `.envrc` and `pixi.toml` declares no `[activation.env]`; poe declares
no `envfile`. In a shell direnv has not blessed, the app raises a `ValidationError` naming
the missing settings and every task that reaches a server aborts on a `${PGPORT:?}` guard
first: `backend-db-init` on its own, and `backend-dev` on the one in the `db-create`
behind it, before uvicorn ever binds.

CI gets the same names the same way: `setup-direnv` activates this `.envrc` and forwards
the resulting environment to `$GITHUB_ENV` for the steps after it. It is the first thing
to check if CI ever fails to find `PGPORT`.

One loader covers everything, including what no task wraps:

```sh
psql                                              # the local cluster, no flags
pytest tests/test_expense_postgres.py -k truncate --pdb
python -m expense_tracker.expense_loader ~/exports # any directory, not the configured one
```

`PGHOST`, `PGPORT`, `PGUSER` and `PGDATABASE` are the variables libpq itself reads, so
`psql`, `pg_dump` and friends need no arguments, and a test run started from an editor
reaches the same cluster as `pixi run backend-test`.

**Precedence is short.** `backend/.env` *overwrites* what is already in the environment,
so an `export PGPORT=...` ahead of it leaves the port as the file states it, and
`backend/.env.local` overwrites that in turn. Above both sits **`DATABASE_URL`, which
overrides the four parts wholesale**. That is the deployment path, and a deployment
supplies its own. `database_url()` returns a `sqlalchemy.URL` rather than a `str`, so
`str()` and `repr()` render any password as `***`.

**Every one of them is required.** With no `DATABASE_URL` and none of the four names in
the environment, the process refuses to start and names every missing one.

To move either port off something else has taken, edit **`backend/.env`** itself. `PGPORT`
is baked into the cluster at `initdb` time, so follow that edit with `pixi run
backend-db-reset && pixi run backend-db-init`; `UVICORN_PORT` takes effect on the next
`pixi run backend-dev`. That leaves the file a committed default edited in place, which
shows up as a dirty working tree. `backend/.env.local` is where a value that names one
machine goes. `.gitignore` ignores **every** `.env` variant and names back only the two
committed defaults.

The frontend has exactly one variable of its own, `VITE_API_BASE_URL`. See [Where the API
lives](docs/frontend.md#where-the-api-lives).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, Conventional Commit, and
squash-merge rules. To report a security issue, see [`SECURITY.md`](SECURITY.md); please
do not open a public issue for one.

## License

MIT. See [`LICENSE`](LICENSE).
