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
    schema.sql                  # the whole schema: three tables, one seeded row
    data/expenses/              # the committed expense files, loaded into the database
    src/expense_tracker/        # __init__ (the API), deps, config, db,
                                #   {greeting,expense}_repository, expense_loader
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

## Quickstart

```sh
cd expense-tracker          # direnv provisions the environment on entry
pixi run frontend-install   # install frontend dependencies (pnpm)
pixi run backend-db-init    # create, start and seed the local database
```

`db-init` is idempotent, so it is also how you start the database again on any later
day. Without it the API answers `503` and the page shows its error state.

Then start both, in two terminals:

```sh
pixi run backend-dev   # the REST API on http://localhost:8000
pixi run frontend-dev  # the SPA on http://localhost:5173
```

Visit http://localhost:5173 and you should see `Hello, World!`, fetched from
`http://localhost:8000/api/greeting` - a genuine cross-origin request, which works
only because the API allows it (see [CORS](#cors)) - and read in turn out of the
`greeting` table (see [Database](#database)).

The API alone is enough for backend work. The SPA alone runs too; it just renders its
error state until something answers on 8000.

## Routes

| Route | What it serves |
| --- | --- |
| `GET /api/greeting` | `{"greeting": "<the message column of the greeting table>"}` |
| `GET /api/expenses` | `[{"amount", "currency", "date", "category", "details"}, ...]` - the `ExpensePayload` model |

Both send `Cache-Control: no-store`.

The greeting answers `503 {"detail": "greeting unavailable"}` when the database is
unreachable or the seed row is missing - both server faults, not client ones.

Expenses come back **newest first**, and `amount` is a **string**, not a number: the
column is `numeric(12, 2)`, JSON has no decimal type, and a decimal has no exact binary
form, so a float round trip is how a total drifts by a cent. That shape is declared once,
as the `ExpensePayload` pydantic model in `backend/src/expense_tracker/__init__.py`;
the tests parse responses back into it rather than into untyped dicts. An unreachable
database answers `503 {"detail": "expenses unavailable"}`, but an **empty table answers
`200 []`** - a database nobody has run the loader against yet is a legitimate state, not
a fault, which is where this differs from the greeting's missing row.

Expenses are read-only over HTTP. Rows arrive through `pixi run backend-load-expenses`
and nowhere else, so there is no POST, PUT or DELETE.

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

PostgreSQL, holding three tables: `greeting` (one row - changing the wording is an
`UPDATE`, not a deploy), and `loaded_expense_file` and `expense`, which together are a
view of the files in `backend/data/expenses/`. See
[Loading expenses](#loading-expenses).

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

All five tasks are idempotent, and `db-init` depends on `db-start` depends on
`db-create`, so `pixi run backend-db-init` is the only one you normally need.
`db-reset` throws the cluster away - the cure if a test that edits the greeting row is
killed before it can restore it.

### Schema and access

`backend/schema.sql` is the entire schema and the only DDL. There is no Alembic - three
tables do not earn a migration tool when two of them are append-only and rebuildable
from `backend/data/expenses/` - and the app issues no DDL of its own, so nothing but
`db-init` ever runs it. Every statement in it is idempotent, and the seed uses
`ON CONFLICT DO NOTHING` so re-running never stamps on an edited row. Generated keys use
`GENERATED ALWAYS AS IDENTITY` rather than `bigserial`, which PostgreSQL's own
[Don't Do This](https://wiki.postgresql.org/wiki/Don%27t_Do_This) page advises against
for new applications. The `Greeting`, `LoadedExpenseFile` and `Expense` models declare
the same tables a second time, in Python, with nothing checking the agreement; change
both together.

Access is SQLAlchemy 2 async over asyncpg, split across six modules:

| Module | Holds |
| --- | --- |
| `__init__.py` | `create_app()`, both routes, both exception handlers, `ExpensePayload` |
| `deps.py` | the lifespan, the per-request session, and the two `provide_*_repository` seams |
| `expense_loader.py` | the TSV parser and the `python -m` entry point - the only thing that writes |
| `expense_repository.py` | `LoadedExpenseFile`, `Expense`, and the expense repository |
| `greeting_repository.py` | `Greeting` and the greeting repository |
| `db.py` | the declarative `Base` the two repository modules share |
| `config.py` | the database connection settings, and nothing else |

Each repository module holds its models, an **abstract base class**, its `Postgres*`
implementation and the `...UnavailableError` it raises, and imports nothing from
FastAPI - so neither knows a status code. Callers depend on the base classes and never
name an implementation; implementations subclass them and carry `@override`, so the
coupling is visible at the class declaration and drift fails `backend-typecheck`.
`expense_loader.py` is a *sibling* of `deps.py`, not something below it, and may not
import it - which is what keeps FastAPI out of `python -m`.

The dependency arrows run one way, and are checked rather than merely intended: `pixi
run backend-lint` runs import-linter after ruff, against the contracts in
`backend/pyproject.toml`, which fail the build on an import pointing back up the stack,
on anything but `deps.py` learning about FastAPI, and on a cycle anywhere in the
package. `create_app()` holds the only two handlers that map an exception to a 503.

The engine is owned by the app's **lifespan** rather than built at import time, and
handed to requests as lifespan state, from which a session is opened per request. That
is not incidental: it means `create_app()` opens no socket, which is what lets most of
the test suite construct a real app with no database anywhere.

`backend/tests/test_app.py` overrides both repository dependencies with fakes and never
connects. Only `backend/tests/test_greeting_postgres.py` and
`backend/tests/test_expense_postgres.py` talk to the real server, behind the `postgres`
marker registered in `backend/pyproject.toml`; they skip when nothing answers, so a
developer who has not run `db-init` does not face a red suite, and **fail** under
`CI=true`, so a database that did not come up cannot go green.

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

That rebuild is also the cure after `pixi run backend-test`, which TRUNCATEs both tables
before and after every test in `test_expense_postgres.py` - running the suite empties
whatever you had loaded.

It is the cure for a **schema change**, too. Every statement in `schema.sql` is
`CREATE ... IF NOT EXISTS`, so `db-init` adds what is missing but never renames or alters
what is already there. Pulling a branch that changes a column or a table name means
resetting the cluster, not re-running `db-init`.

## Frontend

A React 19 SPA built by vite and styled with Tailwind CSS v4, configured in CSS via
`frontend/src/styles/app.css` - there is no `tailwind.config.js`.

`pixi run frontend-build` writes to `frontend/dist/`, vite's default. It is **gitignored**
and nothing in this repo consumes it. CI runs the build as a gate because tsc and
vitest never exercise the bundler, but keeps nothing from it.

Row 1 of the `greeting` table is the single source of truth for the greeting: the
backend reads it and serves it from `GET /api/greeting`, and
the page fetches it at runtime with [TanStack Query](https://tanstack.com/query) in
`frontend/src/api/greeting.ts`. Nothing generates a client from a schema, so the
payload *shape* is written out by hand on both sides and the two must be changed
together; a mismatch shows up as a 404 or a failed shape guard at runtime. The wording
itself is duplicated nowhere - it exists only in the database.

Tests use vitest, live in `frontend/tests/`, and reach into the app through the `@`
alias (`@/api/greeting`). The alias is declared twice - `resolve.alias` in
`frontend/vite.config.ts` for the bundler and `paths` in `frontend/tsconfig.app.json`
for the type checker, because vite does not read tsconfig `paths` - so both must point
at the same place. Imports *within* `src/` stay relative.

The backend is stubbed with [MSW](https://mswjs.io). `frontend/tests/setup.ts` starts
the server with `onUnhandledRequest: "error"`, so an unstubbed request fails the test
instead of quietly reaching the network. Handlers bind to the absolute `GREETING_URL`
exported by `frontend/src/api/greeting.ts`, because a path-only pattern would resolve
against jsdom's origin rather than the API's and never match.

`frontend/src/main.tsx` is excluded from coverage in both `frontend/vite.config.ts` and
`sonar-project.properties` - it only wires React to the DOM. `frontend/vite.config.ts`
also pins vitest's root back up to the repo root (`new URL("../", import.meta.url)`),
even though vite's own root is `frontend/`. That is what makes the lcov report record
repo-relative paths like `frontend/src/App.tsx`; without it SonarCloud resolves them
against the Python package and reports the frontend as uncovered - silently, with a
green build.

### Where the API lives

`frontend/.env` holds `VITE_API_BASE_URL`, and `frontend/src/api/greeting.ts` resolves
every request path against it. That one variable is the frontend's only knowledge of
the backend; there is deliberately no vite proxy, so the dev-time request is a real
cross-origin call over the same CORS path a deployed one would take. Override it in
`frontend/.env.local` (gitignored) to point at a backend elsewhere.

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
environment. vite inlines it at build time; there is no runtime lookup to override.

### Package manager

Dependencies are installed with **pnpm**, whose version is pinned in `pixi.toml`
alongside Node. Three deliberate choices:

- **`frontend/package.json` has no `packageManager` field, and must not gain one.**
  pnpm's `pmOnFail` defaults to `download`, so that field would make pnpm fetch and run
  its own copy of the declared version, bypassing the pixi pin.
- **Pins must be at least 24 hours old.** `frontend/pnpm-workspace.yaml` sets
  `minimumReleaseAge: 1440`, so pnpm refuses to install versions published in the last 24
  hours as a supply-chain guard. Because this project pins exact versions, pnpm cannot
  fall back to an older release - it asks you to exempt the version instead. **Pick a
  newer release that already clears the window rather than adding an exemption**, which
  would disable the guard for precisely the least-vetted package.

  The value is 1440 because that is already pnpm 11's default; it is written down for
  **Dependabot**, which is not running pnpm 11. It picks its pnpm major from the
  lockfile, and the `lockfileVersion: 9.0` pin lands it on pnpm 10, where the setting
  defaults to 0. Left implicit, the guard would hold where the lockfile is *verified*
  (CI) and not where it is *resolved* (Dependabot), which is how a transitive package
  five hours old reached `pnpm-lock.yaml` and failed CI in PR #48. One case stays outside
  it: Dependabot deliberately disables the guard for **security** updates, so such a PR
  can still carry a too-young entry. Re-run the job once that version clears 24 hours
  (`gh run rerun <run-id> --failed`) - the check recomputes the cutoff at install time.
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
or those paths do not exist yet and the servers will not start.

Formatting is not configured here: `format_on_save` is left to your own Zed settings.
Formatting is applied by `pixi run frontend-format` and gated in CI by
`pixi run frontend-format-check`, the same way `ruff format` works on the Python side.

To confirm the declared pins match what is installed:

```sh
cd frontend && pnpm ls @tailwindcss/language-server @vtsls/language-server typescript tailwindcss prettier eslint
```

Expect `0.16.0`, `0.3.0`, `6.0.3`, `4.3.3`, `3.9.6`, `10.8.0`. One nested entry is
expected and is not drift: `@vtsls/language-server` bundles its own `typescript@5.9.3`,
which the `tsdk` setting in `.zed/settings.json` redirects to the pinned top-level copy.

To confirm Zed is using them, run this while Zed is open:

```sh
ps -eo pid,args | grep -E '[v]tsls|[t]ailwindcss-language-server|[e]slintServer'
```

Paths under `frontend/node_modules/` mean the pins took effect; paths under
`~/.local/share/zed/` mean they did not - usually a missing `node_modules` or no `node`
on PATH for Zed's remote server. `eslintServer.js` is the exception and always runs from
`~/.local/share/zed/`, because that server is Zed's own and only the module it loads is
pinned; check it by putting `const x: any = 1;` in a `.tsx` file and confirming
`@typescript-eslint/no-explicit-any` fires.

Two things that look like faults but are not: over a remote/WSL backend, Server Info
reports `Binary: Unknown` and `Version: Unknown` for `vtsls` however healthy it is, and
the per-server Logs tab is usually empty because most servers never send
`window/logMessage`. Use the `ps` command above instead. If your editor ever disagrees
with CI, `pixi run backend-typecheck` and `pixi run frontend-lint` are the authority.

## Development tasks

`pixi run <task>` is the entry point, and the same command CI runs.

| Command | Delegates to | What it does |
| --- | --- | --- |
| `pixi run backend-db-init` | `poe db-init` | Create, start and seed the local database (the one you need) |
| `pixi run backend-db-create` | `poe db-create` | `initdb` a cluster into `backend/.pgdata/`, if there is not one |
| `pixi run backend-db-start` | `poe db-start` | Start the cluster on `$PGHOST:$PGPORT`, if it is not running |
| `pixi run backend-db-stop` | `poe db-stop` | Stop the cluster; succeeds if it is already stopped |
| `pixi run backend-db-reset` | `poe db-reset` | Stop the cluster and delete `backend/.pgdata/` entirely |
| `pixi run backend-dev` | `poe dev` | Run the API on uvicorn, port 8000 (with reloader) |
| `pixi run backend-test` | `poe test` | Run the test suite with coverage |
| `pixi run backend-lint` | `poe lint` | Lint with ruff, then check the import graph with import-linter |
| `pixi run backend-lint-fix` | `poe lint-fix` | Auto-fix lint issues (ruff only) |
| `pixi run backend-load-expenses` | `poe load-expenses` | Read `backend/data/expenses/*.tsv` into the database |
| `pixi run backend-format` | `poe format` | Format with ruff |
| `pixi run backend-format-check` | `poe format-check` | Check formatting without writing changes |
| `pixi run backend-typecheck` | `poe typecheck` | Type-check with basedpyright (recommended) |
| `pixi run frontend-install` | `pnpm install` | Install frontend dependencies (`--frozen-lockfile`) |
| `pixi run frontend-dev` | `pnpm run dev` | Run vite's dev server on port 5173 (hot reload) |
| `pixi run frontend-build` | `pnpm run build` | Build the frontend into `frontend/dist/` |
| `pixi run frontend-typecheck` | `pnpm run typecheck` | Type-check the frontend with tsc |
| `pixi run frontend-lint` | `pnpm run lint` | Lint the frontend with eslint (type-aware, `--max-warnings 0`) |
| `pixi run frontend-lint-fix` | `pnpm run lint-fix` | Auto-fix frontend lint issues |
| `pixi run frontend-test` | `pnpm run test` | Run the frontend tests (vitest) with coverage |
| `pixi run frontend-format` | `pnpm run format` | Format the frontend with prettier |
| `pixi run frontend-format-check` | `pnpm run format-check` | Check frontend formatting without writing changes |

Every task sets its own working directory in `pixi.toml` (`backend/` or `frontend/`), so
`pixi run <task>` behaves the same wherever you invoke it from. No task crosses between
the two directories, and every one of them - the five `backend-db-*` included - addresses
its files by a plain relative path. Nothing reaches above its own stack.

That holds when you skip the forwarder too: poe runs a task from the directory of the
`pyproject.toml` it loaded, so `poe -C backend db-start` from anywhere starts the cluster
in `backend/.pgdata/`, exactly as `cd backend && poe db-start` does. `pixi task list`
prints this table's first column.

CI runs every gate above except the two `dev` tasks, the two `-fix` variants,
`backend-format`, `backend-load-expenses` and the four `backend-db-*` tasks other than
`backend-db-init` on each pull request, then the SonarCloud scan. The loader is left out
because it mutates data and CI has no need of it: `test_expense_postgres.py` already
puts the committed sample files through the real database path inside `backend-test`.

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

## Configuration

Where the local database lives is written down once, in **`backend/.env`**, as the four
facts `psql` and `createdb` already read:

```
PGHOST=127.0.0.1
PGPORT=5433
PGUSER=expense_tracker
PGDATABASE=expense_tracker
```

Two readers consume that one file, because two kinds of process need it. **poe** exports
it into every task, via `envfile` in `[tool.poe]` - which is what lets the `db-*` tasks
stay free of `--host`/`--port`/`--username` flags. **`config.py`** reads it directly and
composes the DSN SQLAlchemy connects with, so a process launched outside poe
(`uvicorn --factory`, an editor's test runner) resolves the same values; the path it
looks in is derived from `config.py`'s own location, not the working directory.
`pixi.toml` deliberately declares none of this - a second copy is exactly what this file
replaces.

The DSN itself is stored nowhere. It is composed from the four parts, which is what keeps
the port from being written into a URL string a second time. **`DATABASE_URL` overrides
them wholesale**, and that is the deployment path: there is no `.env` in a deployment, and
the database is one somebody else operates. **A deployment supplies its own.**

None of it has a **default**. With no `DATABASE_URL`, nothing in the environment and no
`.env` on disk, the process refuses to start rather than quietly dialling its own
loopback.

To move the cluster off a port something else has taken, put `PGPORT` in
**`backend/.env.local`** - gitignored, layered over `backend/.env` by both readers, and
the exact counterpart of `frontend/.env.local`. The port is baked into the cluster at
`initdb` time, so follow it with `pixi run backend-db-reset && pixi run backend-db-init`.

One consequence worth knowing: these are no longer pixi activation variables, so a bare
`psql` typed straight into a `pixi shell` needs its own `-p`. Everything that goes through
`pixi run backend-db-*` is unaffected.

The frontend has exactly one variable of its own, `VITE_API_BASE_URL` - see
[Where the API lives](#where-the-api-lives).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, Conventional Commit, and
squash-merge rules.
