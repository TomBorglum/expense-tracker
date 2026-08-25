# CLAUDE.md

Guidance for Claude Code when working in this repository.

**Per-stack invariants live beside the code they govern**, in
[`backend/CLAUDE.md`](backend/CLAUDE.md) and
[`frontend/CLAUDE.md`](frontend/CLAUDE.md). Read the one whose tree you are about to
touch; this file is what applies wherever you are working.

**Each of the three stays under 200 lines.** What earns a place in any of them is under
[Adding to these files](#adding-to-these-files).

## Prerequisites

**`direnv allow` is a precondition, not a convenience.** The single
`dotenv_if_exists backend/.env` line in `.envrc` is what puts `PGHOST`, `PGPORT`,
`PGUSER`, `PGDATABASE` and `UVICORN_PORT` in the environment, and `use pixi python` is
what puts the environment's `pytest`, `ruff` and `vitest` on `PATH`. Nothing else
supplies either - not `pixi run`, which reads no `.envrc` and declares no
`[activation.env]`, and not poe, which declares no `envfile`. A shell that has not been
blessed gets a `ValidationError` from the app and a `PGPORT` abort from the db tasks.

## Working here

- **The invariants in these three files are deliberate**, and every one names the test or
  linter that pins it, or says that nothing does.
- **If an invariant blocks the task, say so rather than routing around it.** Working
  around one silently is how a design property becomes a bug nobody chose.
- **Rationale lives in these files and in `README.md`, not in the source.** See the
  comment policy below.

## Adding to these files

A bullet earns its place only if all three hold. Most candidates fail the first.

1. **Breaking it is a mistake someone would plausibly make** - it looks like an
   improvement, or like the obvious next step. A rule nobody would break unprompted is a
   fact, and facts belong in the code.
2. **The code cannot show the choice was deliberate.** An absence never can: no file says
   why there is no `StaticFiles` mount. A value that is present usually can - ruff's
   `select` list is in `pyproject.toml` and needs no second home.
3. **It names what it prevents**, in one clause. If that clause cannot be written, the
   rule is a description rather than an invariant.

Then state it in one to three lines and end with the test or gate that pins it, or with
"nothing checks this". **Never restate a value that has a single source of truth
elsewhere** - name the file instead. That is the habit this file's backend counterpart
went stale from: it transcribed the import-linter layer list, which then fell two modules
behind the contract it was copied from. A bullet that wants room past 200 lines retires
one.

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

- **ASCII-only** committed source: no em-dashes, smart quotes, arrows, ellipses,
  including the sample data under `backend/data/expenses/`. The loader decodes
  `utf-8-sig`, so a developer's own uncommitted exports carry Danish text and byte-order
  marks fine. Nothing checks this - ruff's `RUF001`-`003` reach confusable characters in
  Python source and nowhere else.
- **Comments say what the code does**, and only where that is not plain from reading it.
  No rationale essays, no rejected alternatives, no explaining where a module sits in the
  layer order - that reasoning lives in these files and in `README.md`, and repeating it
  in the source gives one fact two places to drift apart. Module and function docstrings
  are one line, and only where the name and signature do not already say it. This governs
  code, SQL and config comments; `README.md` keeps its current density, and these files
  answer to [Adding to these files](#adding-to-these-files).
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

**Nothing checks the agreement**, which is what puts these here: change one half and no
gate fails.

| What | The halves | What the pair holds |
|---|---|---|
| The expenses payload and path | `backend/src/expense_tracker/__init__.py` + `frontend/src/api/expenses.ts` | Every expense field is a string on the wire, `amount` included, and the frontend's guard rejects a number. The **query** half is the same pair on the same terms - `currency`, `from_date` and `to_date` in the route signature and in `ExpensesQuery`, where a rename is a silent 422 rather than a type error. |
| The rates payload and path | the same backend file + `frontend/src/api/currencies.ts` | `CurrencyPayload` against the `CurrencyRate` interface, `exchange_rate` a string the guard rejects as a number. `BASE_CURRENCY` is **not** part of the pair - the backend has no notion of a base and needs none, which is what makes `DKK` selectable against an empty rate table. |
| The totals payload and path | the same backend file + `frontend/src/api/totals.ts` | `PeriodTotalPayload` against `PeriodTotal`, every field a string. `amount`, `currency` and `category` are **absent keys, never `null`** - the guard rejects both a number and a null, which is what keeps a period holding nothing apart from one that netted to `0.00`. The **query** half adds `period`, always sent because the backend refuses an absent one, and `group_by`, sent only when grouping because absent is what ungrouped means on both sides. |
| The three tables | `backend/schema.sql` + the `LoadedExpenseFile` and `Expense` models in `expense_repository.py` and `CurrencyRate` in `currency_repository.py` | The models never create the tables and only read them. |
| What is left of the local database connection | `backend/.env` + `db-create`'s `initdb` flags and `db-init`'s `createdb` | `PGUSER` and `PGHOST` against `--username=expense_tracker`, `--set=listen_addresses=127.0.0.1` and `createdb expense_tracker`. `PGPORT` is *not* in this pair - `db-create` takes it as `--set=port="$PGPORT"`, and the rest could follow the same way. |
| The `@` alias (`frontend/src`) | `frontend/vite.config.ts` + `frontend/tsconfig.app.json` | vite does not read tsconfig `paths`. |
| The `frontend/src/main.tsx` coverage exclusion | `frontend/vite.config.ts` + `sonar-project.properties` | One exclusion, two tools that each have to name it. |
| The `frontend/src/routeTree.gen.ts` exclusion | declared three times: `frontend/.prettierignore`, `coverage.exclude` in `frontend/vite.config.ts`, `sonar.exclusions` in `sonar-project.properties` | The file is generated and authored by nobody, so each tool has to name it or it reports on machine-written code. Dropping the prettier one is the loud failure - `frontend-format-check` goes red on the `printWidth` mismatch; the other two fail quietly. **eslint is deliberately not a fourth**; why, in [`frontend/CLAUDE.md`](frontend/CLAUDE.md). |
| `VITE_API_BASE_URL` | `frontend/.env` + `frontend/src/vite-env.d.ts` | Set in the first, typed in the second. |
| daisyUI's `@plugin` descriptors | `frontend/src/styles/app.css` + the `plugin` override in `frontend/eslint.config.ts` | `tailwind-csstree` models core Tailwind's blockless `@plugin` and rejects any descriptor this repo does not name. |
