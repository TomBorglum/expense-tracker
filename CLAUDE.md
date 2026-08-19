# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Rule files

Two path-scoped rule files carry the stack-specific invariants. They load themselves the
moment you read a file they cover, which is before you can edit one:

- `.claude/rules/backend.md` - `backend/**` and `pixi.toml`
- `.claude/rules/frontend.md` - `frontend/**`

**Do not open them speculatively.** Reading one here spends the context that split
exists to save, and gets you nothing you would not have been handed anyway.

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
- **Comments say what the code does**, and only where that is not plain from reading
  it. Module docstrings are one line; function docstrings are one line, and only where
  the name and signature do not already say it. No rationale essays in Python or
  TypeScript source.
  **The manifests are the exception, deliberately.** `pixi.toml`, `.envrc`,
  `schema.sql`, `backend/pyproject.toml`, `vite.config.ts`, `pnpm-workspace.yaml` and
  `.zed/settings.json` carry the reasoning for what they pin and for what they
  deliberately leave out, because a setting's justification is no use anywhere but
  beside the setting. Match the density already there when you edit one.
- **Pin versions exactly** - `==` in `pixi.toml`, in both its conda tables and
  `[feature.test.pypi-dependencies]`; `==` for `hatchling` in
  `backend/pyproject.toml`'s `[build-system]`, which `pixi.lock` does not capture; bare
  versions in `frontend/package.json`; GitHub Actions by SHA with a version comment.
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

**The delegation is uniform - every task in `pixi.toml` forwards, none defines.** Never
put a command body there; that is what would make the layer a place definitions hide.
Both stacks also stay runnable on their own terms (`cd backend && poe test`,
`cd frontend && pnpm build`), which is what keeps each directory a standalone project.

`pixi run <task>` is what CI calls and what you should reach for. Every task declares
its own `cwd`, so it behaves identically wherever you invoke it: poe runs a task from
the directory of the `pyproject.toml` it loaded, so a relative path like `.pgdata/`
holds however the task was invoked and nothing needs `$POE_ROOT`. Full table in
[`README.md`](README.md#development-tasks).

**`dev` depends on `db-init`**, so `pixi run backend-dev` is the single command that
gets a backend developer a working API: the cluster chain behind it is idempotent, runs
once before uvicorn, and leaves the cluster up afterwards. `load-expenses` is
deliberately not in that chain - an empty `expense` table is a legitimate `200`, and
putting the loader there would work around that invariant rather than honour it. `test`
stays out of it too, because "the HTTP suite never touches PostgreSQL" is a property
chaining `db-init` onto it would hide.

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

## direnv

**`direnv allow` is a prerequisite, not a convenience.** `backend/.env` holds `PGHOST`,
`PGPORT`, `PGUSER`, `PGDATABASE` and `UVICORN_PORT`, and the single `dotenv_if_exists`
line in `.envrc` is the only thing that puts them in the environment. Not `pixi run`,
which reads no `.envrc` and declares no `[activation.env]`; not poe, whose `[tool.poe]`
declares no `envfile`, and adding one back would be a second loader for one file. A
shell that has not been blessed gets a `ValidationError` from the app and a `PGPORT`
abort from the db tasks.

**CI is a cross-repo dependency, and that is the price of the single loader.**
`setup-direnv` activates `.envrc` and then forwards the resulting environment to
`$GITHUB_ENV`; that forwarding arrived in **v1.4.1**, and the pin in `ci.yml` is what
every later `pixi run` depends on for those names. A `PGPORT` failure in CI means
checking that pin first, before anything in this repo.

## Six things are declared twice. Change both halves together

- the two *payload shapes and paths* - `backend/src/expense_tracker/__init__.py`
  against `frontend/src/api/greeting.ts` for the greeting and
  `frontend/src/api/expenses.ts` for the expenses, with nothing checking either
  agreement. **Every expense field is a string on the wire, `amount` included**: the
  backend sends `str(Decimal)` so no float round trip can drift a total by a cent, and
  `date` is a bare `YYYY-MM-DD`. `test_expense_amounts_are_strings_not_numbers` pins
  that on the backend; the frontend's shape guard rejects a numeric amount rather than
  coercing it, so a change to `ExpensePayload` is a change to the `Expense` interface.
  The greeting *wording* is not duplicated anywhere: it is one row of the `greeting`
  table;
- the three tables - `backend/schema.sql` and the `Greeting` model in
  `greeting_repository.py` plus `LoadedExpenseFile` and `Expense` in
  `expense_repository.py`, which never create them and only read them;
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
  `frontend/src/vite-env.d.ts`.
