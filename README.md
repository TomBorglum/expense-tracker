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
  .pgdata/                      # the local PostgreSQL cluster, gitignored
  backend/
    pyproject.toml              # hatchling, ruff, pytest, basedpyright, poe tasks
    schema.sql                  # the whole schema: one table, one seeded row
    src/expense_tracker/        # create_app() factory, the whole API
    tests/
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

It answers `503 {"detail": "greeting unavailable"}` when the database is unreachable or
the seed row is missing - both server faults, not client ones.

That is the whole surface. There is no page route and no static mount - the frontend
is a separate app - and no OpenAPI schema, `/docs` or `/redoc`: one hand-written route
does not earn a generated document, and the schema would be public surface advertising
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

PostgreSQL, holding one table with one row: the greeting. Changing the wording is an
`UPDATE`, not a deploy.

The server is a **pixi dependency**, not a container. `postgresql` is pinned in
`pixi.toml` beside python and node, so `direnv allow` provisions it and the `db-*`
tasks drive it. There is no Dockerfile, no compose file, and no `services:` block in
`.github/workflows/ci.yml` - CI runs `pixi run backend-db-init`, exactly what a
developer runs.

### The cluster

`pixi run backend-db-create` runs `initdb` into `.pgdata/` at the repo root
(gitignored). Three settings are baked into the generated `postgresql.conf` rather than
passed at launch, which is why `db-start` needs no flags:

| Setting | Value | Why |
| --- | --- | --- |
| `port` | `5433` | Cannot collide with a system PostgreSQL on 5432 |
| `listen_addresses` | `127.0.0.1` | Off the network entirely |
| `unix_socket_directories` | `/tmp` | Nothing connects over it; the DSN is TCP |

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

`backend/schema.sql` is the entire schema and the only DDL. There is no Alembic - one
table with one row does not earn a migration tool - and the app issues no DDL of its
own, so nothing but `db-init` ever runs it. Every statement in it is idempotent, and
the seed uses `ON CONFLICT DO NOTHING` so re-running never stamps on an edited row.
The `Greeting` model in `backend/src/expense_tracker/db.py` declares the same table a
second time, in Python, with nothing checking the agreement; change both together.

Access is SQLAlchemy 2 async over asyncpg, split across two modules. `db.py` is
persistence alone - the model, the `GreetingRepository` **abstract base class** with
`PostgresGreetingRepository` behind it, and the `GreetingUnavailableError` it raises -
and imports nothing from FastAPI, so it knows no status codes. Callers depend on the
base class and never name the implementation. Implementations subclass it and carry
`@override`, so the coupling is visible at the class declaration and drift fails
`backend-typecheck`. `deps.py` is the wiring: it resolves `DATABASE_URL`, owns the
lifespan, and injects a repository into the route. The dependency arrow runs one way,
`deps.py` to `db.py`, and `create_app()` holds the single handler that maps the
exception to a 503.

The engine is owned by the app's **lifespan** rather than built at import time, and
handed to requests as lifespan state, from which a session is opened per request. That
is not incidental: it means `create_app()` opens no socket, which is what lets most of
the test suite construct a real app with no database anywhere.

`backend/tests/test_app.py` overrides the greeting dependency with a fake repository and
never connects. Only `backend/tests/test_greeting_postgres.py` talks to the real server,
behind the `postgres` marker registered in `backend/pyproject.toml`; it skips when
nothing answers, so a developer who has not run `db-init` does not face a red suite,
and **fails** under `CI=true`, so a database that did not come up cannot go green.

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
- **Pins must be at least 24 hours old.** pnpm 11 refuses to install versions published
  in the last 24 hours (`minimumReleaseAge`) as a supply-chain guard. Because this
  project pins exact versions, pnpm cannot fall back to an older release - it asks you
  to exempt the version in `pnpm-workspace.yaml` instead. **Pick a newer release that
  already clears the window rather than adding an exemption**, which would disable the
  guard for precisely the least-vetted package.
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
| `pixi run backend-db-create` | `poe db-create` | `initdb` a cluster into `.pgdata/`, if there is not one |
| `pixi run backend-db-start` | `poe db-start` | Start the cluster on 127.0.0.1:5433, if it is not running |
| `pixi run backend-db-stop` | `poe db-stop` | Stop the cluster; succeeds if it is already stopped |
| `pixi run backend-db-reset` | `poe db-reset` | Stop the cluster and delete `.pgdata/` entirely |
| `pixi run backend-dev` | `poe dev` | Run the API on uvicorn, port 8000 (with reloader) |
| `pixi run backend-test` | `poe test` | Run the test suite with coverage |
| `pixi run backend-lint` | `poe lint` | Lint with ruff |
| `pixi run backend-lint-fix` | `poe lint-fix` | Auto-fix lint issues |
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
the two directories. `pixi task list` prints this table's first column.

The five `backend-db-*` tasks are the backend's like any other, but the cluster they
drive is a workspace-level artifact like `.pixi/`: it is initdb'd into `.pgdata/` at the
repo root, not under `backend/`. They address it through `$POE_ROOT`, poe's absolute path
to `backend/`, so it does not matter where you invoke them from either.

CI runs every gate above except the two `dev` tasks, the two `-fix` variants,
`backend-format` and the four `backend-db-*` tasks other than `backend-db-init` on each
pull request, then the SonarCloud scan.

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

The backend reads exactly one environment variable, `DATABASE_URL`, and has **no
default** for it: an app that cannot find the setting refuses to start rather than
quietly dialling its own loopback.

`pixi.toml` supplies the development value from `[feature.test.activation.env]`, so
`pixi run backend-dev`, `pixi run backend-test` and the editor all get it without anyone exporting
anything. That block is scoped to the `test` feature deliberately - a root
`[activation.env]` would be folded into the `prod` environment too and hand a
deployment a DSN pointing at its own loopback. **A deployment supplies its own.**

Alongside it sit `PGHOST`, `PGPORT`, `PGUSER` and `PGDATABASE`: the same four facts in
the form `psql` and `createdb` read, which is what lets the `db-*` tasks stay free of
`--host`/`--port`/`--username` flags. Change them together, and together with the
`initdb` flags in `db-create` that create the cluster they describe.

The frontend has exactly one variable of its own, `VITE_API_BASE_URL` - see
[Where the API lives](#where-the-api-lives).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, Conventional Commit, and
squash-merge rules.
