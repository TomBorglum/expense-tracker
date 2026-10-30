# CLAUDE.md

Guidance for Claude Code when working in this repository.

**Per-stack invariants live beside the code they govern**, in
[`backend/CLAUDE.md`](backend/CLAUDE.md) and
[`frontend/CLAUDE.md`](frontend/CLAUDE.md). Read the one whose tree you are about to
touch; this file is what applies wherever you are working.

**Each of the three stays under 200 lines.** What earns a place in any of them is under
[Adding to these files](#adding-to-these-files).

## Prerequisites

**`direnv allow` is a precondition.** The single `dotenv_if_exists backend/.env` line in
`.envrc` puts `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE` and `UVICORN_PORT` in the
environment, and `use pixi python` puts the environment's `pytest`, `ruff` and `vitest` on
`PATH`. `.envrc` is the only source of either. A shell that has not been blessed gets a
`ValidationError` from the app and a `PGPORT` abort from the db tasks.

## Working here

- **The invariants in these three files are deliberate**, and every one names the test or
  linter that pins it, or says that nothing does.
- **If an invariant blocks the task, say so.**
- **Rationale lives in these files and in `README.md`, not in the source.** See the
  comment policy below.

## Adding to these files

A bullet earns its place only if all three hold. Most candidates fail the first.

1. **It states a property this tree holds today**, in the present tense.
2. **Reading the code does not make that property plain.** A value with a single source of
   truth elsewhere is already shown by the code - ruff's `select` list is in
   `pyproject.toml` and needs no second home.
3. **It fits in one clause.** Anything longer is a description, and descriptions belong in
   `README.md`.

Then state it in one to three lines and end with the test or gate that pins it, or with
"nothing checks this". **Never restate a value that has a single source of truth
elsewhere** - name the file instead. A bullet that wants room past 200 lines retires one.

## Branch, merge and release rules

The rationale is in [`CONTRIBUTING.md`](CONTRIBUTING.md), which maps each rule to the
ruleset rule that pins it. The `main-protection` ruleset enforces every one of them and
nobody can bypass it.

- **Never push directly to `main`.** Every change goes on a branch, through a PR.
- **The PR title must be a valid Conventional Commit.** It becomes the squashed commit
  subject that release-please parses.
- **Squash-merge only**, keeping `main` linear.
- **Before merging:** the `Checks` and `SonarCloud Code Analysis` checks pass and every
  review thread is resolved. Both are required by the ruleset, by those exact names.
- **Merge with `gh pr merge --squash --delete-branch`.**
- **Branch naming:** `<type>/<short-kebab-description>`, e.g. `feat/monthly-report`.
- **Releases are automated** by release-please
  (`.github/workflows/release-please.yml`). **Never hand-edit versions, git tags, or
  `CHANGELOG.md`.**
- **A job that checks out the repository never gets `id-token: write`.** Checked-out code
  is code that runs - a Dockerfile, `pixi install`, `pnpm install` - and that token is
  what buys the Docker Hub credential out of AWS. `release.yml` is split into `build` and
  `push` for this reason. `publish.yml` grants both permissions, but a caller's are only a
  ceiling a called job can lower, and `build` lowers them. Nothing checks this: `ci.yml`
  and `release.yml`'s `build` job are the only jobs that check out, and neither asks for
  the token today.

## Source conventions

- **This repository is public.** Nothing confidential is ever committed - real spending
  lives in the private repository `EXPENSE_DATA_DIR` points at, and the files under
  `backend/tests/data/expenses/` are synthetic fixtures. Secret scanning with push
  protection is on, and covers credentials.
- **ASCII-only** committed source: no em-dashes, smart quotes, arrows, ellipses,
  including the sample data under `backend/tests/data/expenses/`. PyYAML decodes UTF-8 and
  strips a byte-order mark itself, so a developer's own uncommitted month files carry
  Danish text fine. Nothing checks this; ruff's `RUF001`-`003` cover confusable characters
  in Python source.
- **Comments say what the code does**, and only where that is not plain from reading it.
  Rationale lives in these files and in `README.md`. Module and function docstrings are one
  line, and only where the name and signature do not already say it. This governs code, SQL
  and config comments; these files answer to
  [Adding to these files](#adding-to-these-files).
- **Pin versions exactly** - `==` in `pixi.toml`, in both its conda tables and
  `[feature.test.pypi-dependencies]`, bare versions in `frontend/package.json`, GitHub
  Actions by SHA with a version comment.
- **Every suppression carries a reason** beside the pragma: a comment next to
  `# pyright: ignore[...]` (see `backend/tests/test_date_range.py`), or on/above
  an `// eslint-disable-next-line <rule>`.

## Commands

**Commands live in two layers, and adding one means editing both.**

1. **The directory that runs it defines it**, in the manifest that already owns how its
   tools behave: poe tasks in `backend/pyproject.toml`, the `scripts` block in
   `frontend/package.json`, and `database/pyproject.toml`, which is a poe manifest and
   nothing else. This is where the command body goes.
2. **`pixi.toml` forwards to it**, one prefixed one-liner per command, so `pixi run`
   stays the single entry point spanning every directory.

**The delegation is uniform - every task in `pixi.toml` forwards, none defines.** Each
directory also stays runnable on its own terms (`cd backend && poe test`,
`cd frontend && pnpm build`), which is what keeps it a standalone project.
Every task declares its own `cwd` and addresses paths relative to its own manifest, so it
behaves identically wherever you invoke it. Full table and reasoning in
[`README.md`](README.md#development-tasks), under
[Where commands are defined](README.md#where-commands-are-defined).

**`dev` depends on `db-init`**, so `pixi run backend-dev` is the single command that gets
a backend developer a working API: the cluster chain behind it is idempotent, runs once
before uvicorn, and leaves the cluster up afterwards. The chain is `db-init` alone - an
empty `expense` or `currency_rate` table is a legitimate `200`, and the HTTP suite runs
without PostgreSQL, as [`backend/CLAUDE.md`](backend/CLAUDE.md) states.

**A warning fails the build like an error in both stacks.** The mechanism is in each
stack's file.

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
other backend test and the whole frontend suite run without a database.

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

**Nothing checks the agreement.**

| What | The halves | What the pair holds |
|---|---|---|
| The collection envelope | `backend/src/expense_tracker/__init__.py` + `frontend/src/api/fetchList.ts` | `_collection` builds `{"items": [...]}`, plus a `summary` the totals route alone passes; `fetchList` unwraps `items` for the three list endpoints and `fetchCollection` validates both halves for totals. The frontend proves its half against its own mocks, in `tests/msw/handlers.ts`. |
| The expenses payload and path | `backend/src/expense_tracker/__init__.py` + `frontend/src/api/expenses.ts` | Every expense field is a string on the wire, `amount` included, and the frontend's guard rejects a number. `key` is the bank's own text for the row, **mandatory and never empty**, so it is always a present string. The **query** half is the same pair on the same terms - `currency`, `from_date`, `to_date` and the three category keys in the route signature and in `ExpensesQuery`. `category` and `not_category` are the repeated keys two `list[str]` read, appended once per value and absent when the list is empty; `category_default` is the root's own sign, spelled `all` or `none` on both sides, and sent wherever that sign has to be explicit. Both lists carry **slugs**. The frontend states a selection in `src/categorySelection.ts` and the backend in `category_filter.py`, and **each states it independently of the other**. |
| The rates payload and path | the same backend file + `frontend/src/api/currencies.ts` | `CurrencyPayload` against the `CurrencyRate` interface, `exchange_rate` a string the guard rejects as a number. `BASE_CURRENCY` is the frontend's alone, which is what makes `DKK` selectable against an empty rate table. |
| The totals payload and path | the same backend file + `frontend/src/api/totals.ts` | `PeriodTotalPayload` against `PeriodTotal`, every field a string - `category` holding the path the summed rows carry, the same one `/api/expenses` shows, which `?group_by=` switches on. `amount`, `currency` and `category` are **absent keys when they have no value**, and the guard rejects both a number and a null, which is what keeps a period holding nothing apart from one that netted to `0.00`; such a period carries the span alone. Beside the rows, `SummaryPayload` fills a `summary` - one entry per currency, `average` a string, **both keys always present**, an entry existing only for a currency that has expenses - and it is **identical grouped or not**, which is what lets one request serve both halves of the view. The **query** half adds `period`, always sent, `group_by`, sent when grouping, and the three category keys on the expenses row's terms. |
| The categories payload and path | the same backend file + `frontend/src/api/categories.ts` | `CategoryPayload` against the `Category` interface, five string fields: `category` is the whole `:`-separated path, `name` its last level, `slug` the path's URL spelling, and `parent`/`parent_slug` the pair above it, **absent on a depth-1 row**, the mirror of the totals row's rule above. The slug is the loader's: it assigns it and `slug` carries it. The separator is `category_filter.SEPARATOR`, its only declaration, which the four other fields exist to keep true and which lets the picker build its tree from `parent_slug` alone. The **query** half is `to_level` alone against `CategoriesQuery`, always sent, the tree the picker shows being bounded; `from_level` is the backend's own. The list is what the picker offers, and a URL slug outside it is still sent. |
| The four tables | `backend/schema.sql` + the `LoadedExpenseFile`, `Expense` and `Category` models in `expense_repository.py` and `CurrencyRate` in `currency_repository.py` | The models read the tables. `category.slug`'s CHECK is the shape `category_filter.SLUG_PATH` states in Python, so that pair moves together too. |
| What is left of the local database connection | `backend/.env` + `db-create`'s `initdb` flags and `db-init`'s `createdb` | `PGUSER` and `PGHOST` against `--username=expense_tracker`, `--set=listen_addresses=127.0.0.1` and `createdb expense_tracker`. `PGPORT` reaches `db-create` as `--set=port="$PGPORT"` instead. |
| The pixi version | `.envrc` + the builder image in **both** `backend/Dockerfile` and `frontend/Dockerfile` | `use pixi 0.81.0` against `ghcr.io/prefix-dev/pixi:0.81.0-noble`. Both resolve the same `pixi.lock`, so the three agree on one version and the image installs what a developer and CI install. `.github/dependabot.yml`'s `docker` entry **ignores** that image, so all three move together by hand. |
| The release workflow's path | `.github/workflows/release.yml` + the `job_workflow_ref` condition on the AWS release role's trust policy | The trust policy pins `TomBorglum/expense-tracker/.github/workflows/release.yml@refs/tags/v*`, and **the other half is in the AWS console**, so this path is a literal in two systems. `job_workflow_ref` names the **called** workflow, which is why `release.yml` keeps that path and `publish.yml` took a new one: **renaming or moving `release.yml` breaks the policy.** A release whose credential step fails with an STS `AccessDenied` is this pair out of agreement. `README.md`, under Releases, records the policy so the pair is written down somewhere. |
| The published image names | `release.yml`'s `images` step + the Docker Hub repositories themselves | Composed as `<namespace>/<github repository name>-<directory>`, reading `github.event.repository.name`, so **renaming this GitHub repository renames what a release publishes to** and `latest` forks silently onto new repositories. Nothing checks this; the `meta` job logs each pair on every pull request. |
| The Docker Hub namespace | the `DOCKERHUB_NAMESPACE` repository variable + the Docker Hub account the PAT in SSM belongs to | `release.yml` takes the namespace as an input and spells it once, and `publish.yml` fills it from the variable, so **both halves sit outside the repository**. `meta` checks the shape, not the account: a release that composes image names the credential cannot push to is this pair out of agreement. `README.md`, under Releases, records the variable. |
| The bake target name | `backend/docker-bake.hcl` and `frontend/docker-bake.hcl` + `release.yml`'s `bake-target`, `targets` and `set:` keys | `image`, which is what lets metadata-action's generated label and annotation files merge onto the target the stack declares. An image published carrying no release metadata is this pair out of agreement, and nothing else reports it. The `files` list is ordered on the same terms - bake merges `labels` per key and the last file wins, so the stack's own file goes last. |
| The API base URL placeholder | `frontend/Dockerfile` + `frontend/docker/40-api-base-url.sh` | `__EXPENSE_TRACKER_API_BASE_URL__`, written into `.env.production.local` before `vite build` and rewritten across the document root at container start. The script treats a document root holding no placeholder as its normal restart case, so a bundle served with the literal token in it is this pair out of agreement. The builder's `grep -rq` over `dist/` covers the token's presence in a build. |
| The `@` alias (`frontend/src`) | `frontend/vite.config.ts` + `frontend/tsconfig.app.json` | Each resolves it for its own tool; vite reads tsconfig `paths` for neither. |
| The `frontend/src/main.tsx` coverage exclusion | `frontend/vite.config.ts` + `sonar-project.properties` | One exclusion, two tools that each have to name it. |
| The `frontend/src/routeTree.gen.ts` exclusion | declared three times: `frontend/.prettierignore`, `coverage.exclude` in `frontend/vite.config.ts`, `sonar.exclusions` in `sonar-project.properties` | The file is generated, so each tool names it to keep its report to hand-written code. The prettier one is the half with a gate behind it: `frontend-format-check` goes red on the `printWidth` mismatch. **eslint covers it through `globalIgnores` instead**; why, in [`frontend/CLAUDE.md`](frontend/CLAUDE.md). |
| `VITE_API_BASE_URL` | `frontend/.env` + `frontend/src/vite-env.d.ts` | Set in the first, typed in the second. |
| daisyUI's `@plugin` descriptors | `frontend/src/styles/app.css` + the `plugin` override in `frontend/eslint.config.ts` | `tailwind-csstree` models core Tailwind's blockless `@plugin`, and the override names the descriptors this repo uses. |
