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

- **ASCII-only** committed source: no em-dashes, smart quotes, arrows, ellipses.
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
tasks like the rest, and only the cluster they drive sits at the workspace root rather
than under `backend/`. They reach it through `$POE_ROOT/..`, never a relative path.

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
  `GET /api/greeting`: no `/` route, no `StaticFiles` mount, no build artifact under
  `backend/`. Pinned by `test_root_is_not_served`,
  `test_static_files_are_not_served` and `test_unknown_api_routes_404`.
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
- **`db.py` imports no fastapi and no `deps`.** The wiring points one way: `deps.py`
  imports `GreetingRepository` from `db.py`, never the reverse. A failed read leaves
  the repository as `GreetingUnavailableError`, and the handler registered in
  `create_app()` is the only place that turns it into a 503. Putting an `HTTPException`
  back in `db.py` is what this split exists to prevent. Pinned by the import-linter
  contracts in `backend/pyproject.toml`, not by a test: the layers contract forbids
  `db -> deps`, and `db knows nothing about HTTP` forbids fastapi and starlette,
  indirectly as well as directly. A **new module** under `src/expense_tracker/` has to
  be added to that contract's `layers` list or the gate fails - `exhaustive = true`
  is what stops the rule quietly ceasing to cover new code.
- **Every repository subclasses `GreetingRepository` and carries `@override`.**
  `PostgresGreetingRepository` in `db.py` and `_FakeGreetingRepository` in `conftest.py`
  do; a new implementation or test double does too. The base class is an `ABC`, so this
  is enforced, not a convention - a look-alike that matches the shape without inheriting
  is rejected. It has to be enforced somewhere, because `dependency_overrides` is an
  untyped dict and would accept anything.
- **`@abstractmethod` on `GreetingRepository` is load-bearing.** Without it the `...`
  body is an ordinary method returning `None` and an empty subclass passes. Removing it
  fails `pixi run backend-lint` three ways: `B027` on the method, `B024` on the class,
  `F401` on the unused import. That gate is why no test asserts it. Keep the body a
  same-line `...`; `raise NotImplementedError` would be a statement coverage counts and
  nothing executes.
- **The HTTP suite never touches PostgreSQL.** `backend/tests/conftest.py` overrides
  the `provide_greeting_repository` dependency with a fake repository; only
  `backend/tests/test_greeting_postgres.py`, behind the registered `postgres` marker,
  connects. A new test that hits `/api/greeting` takes the `client` fixture. That
  module skips when no server answers and **fails** under `CI=true`, so a database that
  did not come up cannot go green.
- **`backend/schema.sql` is the only DDL.** No Alembic, no `Base.metadata.create_all`,
  and every statement in it stays idempotent because `db-init` re-runs against live
  clusters.
- **Six things are declared twice. Change both halves together:**
  - the greeting *payload shape and path* - `backend/src/expense_tracker/__init__.py`
    and `frontend/src/api/greeting.ts`, with nothing checking the agreement. The
    greeting *wording* is not duplicated anywhere: it is one row of the `greeting`
    table;
  - the `greeting` table - `backend/schema.sql` and the `Greeting` model in
    `backend/src/expense_tracker/db.py`, which never creates it and only reads it;
  - the local database connection - `DATABASE_URL` and the `PG*` variables in
    `[feature.test.activation.env]`, against the port and username baked into
    `db-create`'s `initdb` flags;
  - the `@` alias (`frontend/src`) - `frontend/vite.config.ts` and
    `frontend/tsconfig.app.json`, because vite does not read tsconfig `paths`;
  - the `frontend/src/main.tsx` coverage exclusion - `frontend/vite.config.ts` and
    `sonar-project.properties`;
  - `VITE_API_BASE_URL` - set in `frontend/.env`, typed in
    `frontend/src/vite-env.d.ts`.
- **The API origin lives in bare `frontend/.env`, not `.env.development`.** vite loads
  `.env` in every mode, including the `test` mode vitest runs in, where MSW binds its
  handlers to the URL built from it. `frontend/vite.config.ts` also pins `envDir` to
  `frontend/`, because the `test` block moves vite's `root` to the repo root and
  `envDir` would otherwise follow it.
- **Every linted file needs a tsconfig that owns it.** eslint runs type-aware via
  `parserOptions.projectService`, so a `.ts`/`.tsx` file outside every tsconfig's
  `include` fails to lint rather than being skipped. `src/` and `tests/` come from
  `tsconfig.app.json`; `vite.config.ts` and `eslint.config.ts` from
  `tsconfig.node.json`, where a new file at the `frontend/` root has to be added too.
  Same reason `frontend/eslint.config.ts` opens with `globalIgnores(["dist"])`.
- **`frontend/package.json` must not gain a `packageManager` field**, and
  `frontend/pnpm-lock.yaml` must stay at `lockfileVersion: 9.0`. The first bypasses the
  pnpm pin in `pixi.toml`; both break Dependabot's lockfile parsing. See
  [`README.md`](README.md#package-manager).
- **`frontend/pnpm-workspace.yaml` must not gain a `minimumReleaseAge` exemption.** It
  exists only to answer `allowBuilds`. Exempting a version disables the 24-hour
  supply-chain guard for the least-vetted release there is; pick a version that already
  clears the window.

## Quality gates

- **Python:** basedpyright in `recommended` mode and ruff with
  `select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]`, both in
  `backend/pyproject.toml`. There is no config file at the repo root and no Python
  setting duplicated in the editor config.
- **Module layering:** import-linter, `[tool.importlinter]` in the same file, run by
  `pixi run backend-lint` as the second half of that task. Imports are just another
  artifact to lint, so they get no gate of their own; `lint-fix` is ruff alone, because
  where a new module belongs in the layer order is a design decision, not a mechanical
  edit. Four contracts: the `deps` above `db` layering, the
  fastapi/starlette ban on `db`, a ban on importing the package root, and
  `acyclic_siblings` for cycles at any depth. ruff cannot cover this - `TID251` bans a
  name project-wide rather than per-module, and ruff builds no cross-module graph, so
  it detects no cycles.
- **Frontend:** `tsc -b` against a `strict` tsconfig, prettier, and eslint 10 in
  `frontend/eslint.config.ts`. `eslint-config-prettier` is applied last, so **the
  linter owns correctness and prettier owns formatting** - never add a formatting rule
  to the eslint config.
- **Neither stack has a warn tier.** `recommended` sets `failOnWarnings`, and the
  frontend `lint` script passes `--max-warnings 0`; a warning fails the build like an
  error. Without them roughly 45 frontend rules would be advisory, including the XSS,
  `target="_blank"` and leaked-timer rules, `exhaustive-deps`, and
  `reportUnusedDisableDirectives`. Demote a rule deliberately in its config if you
  disagree with it; do not let either flag go.
