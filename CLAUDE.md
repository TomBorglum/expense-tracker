# CLAUDE.md

Guidance for Claude Code when working in this repository.

**Per-stack invariants live beside the code they govern**, in
[`backend/CLAUDE.md`](backend/CLAUDE.md) and
[`frontend/CLAUDE.md`](frontend/CLAUDE.md). Read the one whose tree you are about to
touch; this file is what applies wherever you are working.

## Prerequisites

**`direnv allow` is a precondition, not a convenience.** The single
`dotenv_if_exists backend/.env` line in `.envrc` is what puts `PGHOST`, `PGPORT`,
`PGUSER`, `PGDATABASE` and `UVICORN_PORT` in the environment, and `use pixi python` is
what puts the environment's `pytest`, `ruff` and `vitest` on `PATH`. Nothing else
supplies either - not `pixi run`, which reads no `.envrc` and declares no
`[activation.env]`, and not poe, which declares no `envfile`. A shell that has not been
blessed gets a `ValidationError` from the app and a `PGPORT` abort from the db tasks.

## Working here

- **The invariants in these three files are deliberate**, and nearly every one names the
  test or linter that pins it. The handful pinned by nothing say so.
- **If an invariant blocks the task, say so rather than routing around it.** Working
  around one silently is how a design property becomes a bug nobody chose.
- **Rationale lives in these files and in `README.md`, not in the source.** See the
  comment policy below.

## Branch, merge and release rules

The rationale, and the one merge-commit exception, are in
[`CONTRIBUTING.md`](CONTRIBUTING.md). This repo is on the GitHub free plan, so none of it
is enforced by GitHub - follow it as if it were.

- **Never push directly to `main`.** Every change goes on a branch, through a PR.
- **The PR title must be a valid Conventional Commit.** It becomes the squashed commit
  subject that release-please parses.
- **Squash-merge only**, keeping `main` linear.
- **Before merging:** the `SonarCloud Code Analysis` check passes and every review thread
  is resolved.
- **Merge with `gh pr merge --squash --delete-branch`.**
- **Branch naming:** `<type>/<short-kebab-description>`, e.g. `feat/monthly-report`.
- **Releases are automated** by release-please
  (`.github/workflows/release-please.yml`). **Never hand-edit versions, git tags, or
  `CHANGELOG.md`.**

## Source conventions

- **ASCII-only** committed source: no em-dashes, smart quotes, arrows, ellipses. That
  includes the sample data under `backend/data/expenses/`. The loader decodes
  `utf-8-sig`, so a developer's own (uncommitted) exports carry Danish text and
  byte-order marks fine. Nothing in CI checks this - ruff's `RUF001`-`003` reach
  confusable characters in Python source and nowhere else.
- **Comments say what the code does**, and only where that is not plain from reading it.
  No rationale essays, no rejected alternatives, no explaining why a module exists or
  where it sits in the layer order - that reasoning lives in these files and in
  `README.md`, and repeating it in the source gives one fact two places to drift apart.
  Module docstrings are one line; function docstrings are one line, and only where the
  name and signature do not already say it. This is about code, SQL and config comments;
  the prose in `README.md` and these files keeps its current density.
- **Pin versions exactly** - `==` in `pixi.toml`, in both its conda tables and
  `[feature.test.pypi-dependencies]`, bare versions in `frontend/package.json`, GitHub
  Actions by SHA with a version comment.
- **Every suppression carries a reason** beside the pragma: a comment next to
  `# pyright: ignore[...]` (see `backend/src/expense_tracker/__init__.py`), or on/above
  an `// eslint-disable-next-line <rule>`. A bare disable is not acceptable.

## Commands

**Commands live in two layers, and adding one means editing both.**

1. **The stack that runs it defines it**, in the manifest that already owns how its tools
   behave: poe tasks in `backend/pyproject.toml`, the `scripts` block in
   `frontend/package.json`. This is where the command body goes.
2. **`pixi.toml` forwards to it**, one prefixed one-liner per command, so `pixi run`
   stays the single entry point spanning both stacks.

**The delegation is uniform - every task in `pixi.toml` forwards, none defines.** Never
put a command body there; that is what would make the layer a place definitions hide.
Both stacks also stay runnable on their own terms (`cd backend && poe test`,
`cd frontend && pnpm build`), which is what keeps each directory a standalone project.
Every task declares its own `cwd` and addresses paths relative to its own manifest, so it
behaves identically wherever you invoke it and nothing needs `$POE_ROOT`. Full table and
reasoning in [`README.md`](README.md#development-tasks), under
[Where commands are defined](README.md#where-commands-are-defined).

**`dev` depends on `db-init`**, so `pixi run backend-dev` is the single command that gets
a backend developer a working API: the cluster chain behind it is idempotent, runs once
before uvicorn, and leaves the cluster up afterwards. Neither `load-expenses` nor
`load-currencies` is in that chain - an empty `expense` or `currency_rate` table is a
legitimate `200`, and putting a loader there would work around that invariant rather than
honour it. `test` stays out of it too, because "The HTTP suite never touches PostgreSQL"
in [`backend/CLAUDE.md`](backend/CLAUDE.md) is a property chaining `db-init` onto it would
hide.

**Neither stack has a warn tier** - a warning fails the build like an error. The
mechanism, and what would go advisory without it, is in each stack's file.

## Fast inner loop

`pixi run <task>` is what CI calls, and the full gate below is what you run before opening
a PR. While iterating, run the one tool that covers what you changed. A blessed shell has
both on `PATH` already:

```sh
cd backend  && pytest tests/test_conversion.py -k half_cent
cd frontend && pnpm exec vitest run tests/ExpensesTable.test.tsx
```

Backend `pytest` picks up `--strict-markers` and coverage from `[tool.pytest.ini_options]`
either way. The `postgres`-marked modules need `pixi run backend-db-init` first; every
other backend test and the whole frontend suite need no database.

Before opening a PR, run the gate sequence from `.github/workflows/ci.yml`, in order
(cheapest first, so it fails fast):

```sh
pixi run backend-format-check && pixi run backend-lint &&
pixi run backend-typecheck && pixi run backend-db-init && pixi run backend-test &&
pixi run frontend-install && pixi run frontend-format-check &&
pixi run frontend-typecheck && pixi run frontend-lint && pixi run frontend-test &&
pixi run frontend-build
```

The two halves are independent, so a change to one stack can only fail that stack's gates.

## Declared twice - change both halves together

Each pair is named by the two files that hold it. Nothing checks the agreement.

- **The expenses payload and path** - `backend/src/expense_tracker/__init__.py` against
  `frontend/src/api/expenses.ts`. Every expense field is a string on the wire, `amount`
  included, and the frontend's guard rejects a number, so a change to `ExpensePayload` is
  a change to the `Expense` interface. The **query** half is the same pair on the same
  terms: `currency`, `from_date` and `to_date` are named in the route signature there and
  in `ExpensesQuery` here, and a rename on either side is a silent `422` rather than a
  type error.
- **The rates payload and path** - the same backend file against
  `frontend/src/api/currencies.ts`, on the same terms: `CurrencyPayload` against the
  `CurrencyRate` interface, `exchange_rate` a string the guard rejects as a number.
  `BASE_CURRENCY` in that module is **not** part of the pair - the backend has no notion
  of a base and needs none, because the identity case it short-circuits is what makes
  `DKK` selectable against an empty rate table.
- **The three tables** - `backend/schema.sql` against the `LoadedExpenseFile` and
  `Expense` models in `backend/src/expense_tracker/expense_repository.py` and the
  `CurrencyRate` model in `backend/src/expense_tracker/currency_repository.py`, which
  never create them and only read them.
- **What is left of the local database connection** - `PGUSER` and `PGHOST` in
  `backend/.env` against `--username=expense_tracker` and
  `--set=listen_addresses=127.0.0.1` in `db-create`'s `initdb` flags, and against
  `createdb expense_tracker` in `db-init`. `PGPORT` is *not* in this list: `db-create`
  takes it as `--set=port="$PGPORT"`, and the rest could follow the same way.
- **The `@` alias (`frontend/src`)** - `frontend/vite.config.ts` against
  `frontend/tsconfig.app.json`, because vite does not read tsconfig `paths`.
- **The `frontend/src/main.tsx` coverage exclusion** - `frontend/vite.config.ts` against
  `sonar-project.properties`.
- **The `frontend/src/routeTree.gen.ts` exclusion** - declared three times:
  `frontend/.prettierignore`, `coverage.exclude` in `frontend/vite.config.ts` and
  `sonar.exclusions` in `sonar-project.properties`. The file is generated from
  `frontend/src/routes/` and is authored by nobody, so each has to name it or that tool
  reports on machine-written code. Dropping the prettier one is the loud failure - the
  generator formats at `printWidth` 80 and the repo checks at 88, so
  `frontend-format-check` goes red; the other two fail quietly. **eslint is deliberately
  not a fourth**: the file's own `/* eslint-disable */` header covers it, and an ignore
  pattern would make eslint warn "File ignored because of a matching ignore pattern"
  every time an editor opens the file. Explained under "The generated tree is excluded
  from prettier, coverage and Sonar" in
  [`frontend/CLAUDE.md`](frontend/CLAUDE.md).
- **`VITE_API_BASE_URL`** - set in `frontend/.env`, typed in
  `frontend/src/vite-env.d.ts`.
- **react-day-picker's class and variable names** - the `.rdp-root` block at the foot of
  `frontend/src/styles/app.css` against the `@daypicker/react` version pinned in
  `frontend/package.json`. That selector and the five `--rdp-*` custom properties it sets
  are the package's internals, and its stylesheet is unlayered, so a rename in a major
  bump leaves the calendar in the library's own blue under both themes with a green build
  - jsdom evaluates no CSS and nothing else looks. Explained under "The calendar is themed
  through its own variables" in [`frontend/CLAUDE.md`](frontend/CLAUDE.md).
- **daisyUI's `@plugin` descriptors** - the block in `frontend/src/styles/app.css`
  against the `plugin` override in `frontend/eslint.config.ts`, because
  `tailwind-csstree` models core Tailwind's blockless `@plugin` and rejects any
  descriptor this repo does not name. Explained under "CSS is linted by eslint too" in
  [`frontend/CLAUDE.md`](frontend/CLAUDE.md).
