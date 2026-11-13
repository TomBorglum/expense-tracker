# CLAUDE.md

**Per-stack invariants live beside the code they govern**, in
[`backend/CLAUDE.md`](backend/CLAUDE.md) and
[`frontend/CLAUDE.md`](frontend/CLAUDE.md). Read the one governing the tree being changed.
This file applies everywhere.

**Each of the three stays under 200 lines**, no line past 90 characters. What earns a
place in any of them is under [Adding to these files](#adding-to-these-files).

## Prerequisites

**`direnv allow` is a precondition.** Two `dotenv_if_exists` lines in `.envrc` put
`backend/.env` and `stack/.env` in the environment, and they are the only loader of
either: **a variable is named in exactly one `.env`**, the one owning what it describes.
`use pixi python` puts the environment's `pytest`, `ruff` and `vitest` on `PATH`. An
unblessed shell gets a `ValidationError` from the app and a `PGPORT` abort from the db
tasks.

## Working here

- **Every invariant in these three files names the test or linter that pins it**, or says
  that nothing does.
- **Rationale lives in these files and under `docs/`, not in the source**, per the comment
  policy below.
- **If an invariant blocks the task, say so.**

## Adding to these files

A bullet earns its place only if all three hold. Most candidates fail the first.

1. **It states a property this tree holds today**, in the present tense.
2. **Reading the code does not make that property plain.** A value with a single source of
   truth elsewhere is already shown by the code. Ruff's `select` list is in
   `pyproject.toml` and needs no second home.
3. **It fits in one clause.** Anything longer is a description, and descriptions belong in
   `README.md` or under `docs/`.

Then state it in one to three lines and end with the test or gate that pins it, or with
"nothing checks this". **Never restate a value that has a single source of truth
elsewhere**; name the file instead. A bullet that wants room past 200 lines retires one.

## Branch, merge and release rules

The `main-protection` ruleset rule pinning each of these is named in
[`CONTRIBUTING.md`](CONTRIBUTING.md). Nobody can bypass that ruleset.

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
  runs, and that token buys the Docker Hub credential out of AWS. `publish.yml` grants it
  as a ceiling the called workflow lowers. Nothing checks this;
  [`docs/publish.md`](docs/publish.md) has the reasoning.

## Source conventions

- **This repository is public.** Nothing confidential is ever committed. Real spending
  lives in the private repository `EXPENSE_DATA_DIR` points at, and the files under
  `backend/tests/data/expenses/` are synthetic fixtures. Secret scanning with push
  protection is on, and covers credentials.
- **ASCII-only** committed source: no em-dashes, smart quotes, arrows, ellipses,
  including the sample data under `backend/tests/data/expenses/`. A developer's own
  uncommitted month files carry Danish text, PyYAML decoding UTF-8 and stripping a
  byte-order mark itself. Nothing checks this; ruff's `RUF001`-`003` cover confusable
  characters in Python source.
- **Comments say what the code does**, and only where that is not plain from reading it.
  Rationale lives in these files and under `docs/`. Module and function docstrings are one
  line, and only where the name and signature do not already say it. This governs code,
  SQL and config comments; these files answer to
  [Adding to these files](#adding-to-these-files).
- **`README.md` carries under 600 lines, and `docs/` under 1050 in all**, however many
  files it holds. README answers what the application is, how to run it, how it is laid
  out, what the commands are and how to configure it; anything deeper is a `docs/` page.
  A passage that wants room past either number retires one. Nothing checks either;
  `wc -l README.md` and `cat docs/*.md | wc -l` are the counts.
- **No line in a file one of these budgets governs passes 90 characters**, so a budget is
  met by retiring prose and never by widening it. It binds every `.md` file the two
  bullets above and the 200 above them count. Nothing checks this;
  `awk 'length > 90' <file>` is the count.
- **`.github/workflows/` carries under 200 comment lines in all**, however many files it
  holds, and a comment that wants room past that retires one. The budget covers the whole
  directory rather than each file. Nothing checks this;
  `cat .github/workflows/*.yml | grep -c '^[[:space:]]*#'` is the count.
- **A compose file's `name:` is `<repository>-<directory>` and every `${...}` carries a
  `:?` naming the `.env` that owns it**, bar `IMAGE_PREFIX`/`IMAGE_TAG`, which take a
  `:-` placeholder, the digest document overriding them. The release workflow gates all
  three.
- **Pin versions exactly:** `==` in `pixi.toml`, in both its conda tables and
  `[feature.test.pypi-dependencies]`, bare versions in `frontend/package.json`, GitHub
  Actions by SHA with a version comment.
- **Every suppression carries a reason** beside the pragma: a comment next to
  `# pyright: ignore[...]` (see `backend/tests/test_date_range.py`), or on/above
  an `// eslint-disable-next-line <rule>`.

## Commands

**Commands live in two layers, and adding one means editing both.** The directory that
runs a command defines it, in the manifest that owns its tools: poe tasks in
`backend/pyproject.toml`, `scripts` in `frontend/package.json`, and
`database/pyproject.toml`, a poe manifest and nothing else. **`pixi.toml` only forwards**,
one prefixed one-liner per command, so `pixi run` is the single entry point spanning every
directory and no command body lives there. Each task declares its own `cwd` and addresses
paths relative to its own manifest, which keeps every directory runnable on its own terms
(`cd backend && poe test`). Full table in [`README.md`](README.md#development-tasks),
reasoning under
[Where commands are defined](docs/development.md#where-commands-are-defined).

**`dev` depends on `db-init`**, so `pixi run backend-dev` alone brings up a working API.
The chain is idempotent, runs once before uvicorn, and leaves the cluster up. An empty
`expense` or `currency_rate` table is a legitimate `200`, and the HTTP suite runs without
PostgreSQL, as [`backend/CLAUDE.md`](backend/CLAUDE.md) states.

**A warning fails the build like an error in both stacks**, by the mechanism each stack's
file gives.

## Fast inner loop

`pixi run <task>` is what CI calls. While iterating, run the one tool that covers the
change; a blessed shell has it on `PATH` already:

```sh
cd backend  && pytest tests/test_conversion.py -k half_cent
cd frontend && pnpm exec vitest run tests/ExpensesTable.test.tsx
```

Backend `pytest` picks up `--strict-markers` and coverage from `[tool.pytest.ini_options]`
either way. The `postgres`-marked modules need `pixi run backend-db-init` first; every
other backend test and the whole frontend suite run without a database.

Before opening a PR, run the gate sequence from `.github/workflows/ci.yml`, in order,
cheapest first:

```sh
pixi run backend-format-check && pixi run backend-lint &&
pixi run backend-typecheck && pixi run backend-db-init && pixi run backend-test &&
pixi run frontend-install && pixi run frontend-format-check &&
pixi run frontend-typecheck && pixi run frontend-lint && pixi run frontend-test &&
pixi run frontend-build
```

The two halves are independent, so a change to one stack can only fail that stack's gates.

## Declared twice - change both halves together

Each bullet names two halves and the property they hold; **nothing checks any of them**.
The five payload pairs share a backend half, `backend/src/expense_tracker/__init__.py`.

- **The collection envelope** + `frontend/src/api/fetchList.ts`: `_collection` builds
  `{"items": [...]}`, the totals route alone adding a `summary` beside it.
- **The expenses payload and query** + `frontend/src/api/expenses.ts`: every field a
  string, `amount` included, `key` mandatory and never empty, both category lists slugs.
- **The rates payload and path** + `frontend/src/api/currencies.ts`: `CurrencyPayload`
  vs `CurrencyRate`, `exchange_rate` a string; `BASE_CURRENCY` is the frontend's alone.
- **The totals payload and query** + `frontend/src/api/totals.ts`: `PeriodTotalPayload`
  against `PeriodTotal`, `amount`/`currency`/`category` absent keys when they have none.
- **The categories payload and query** + `frontend/src/api/categories.ts`: five string
  fields, `parent`/`parent_slug` absent at depth 1, separator `category_filter.SEPARATOR`.
- **The four tables:** `backend/schema.sql` + the models in `expense_repository.py` and
  `currency_repository.py`; `category.slug`'s CHECK matches `category_filter.SLUG_PATH`.
- **The local database connection:** `backend/.env` + `db-create`'s `initdb` flags and
  `db-init`'s `createdb`; `PGPORT` reaches `db-create` as `--set=port="$PGPORT"`.
- **The deployed database connection:** `stack/compose.yaml`'s `database` service +
  `backend/.env`; the pair is created on **first boot only**, so a volume ignores edits.
- **The pixi version:** `.envrc` + the builder image in both Dockerfiles; dependabot
  ignores that image, so all three move by hand.
- **The release workflow's version pin:** `publish.yml`'s `uses:` + the AWS release
  role's `job_workflow_ref` condition, **in the console**: its pattern ends
  `@refs/tags/v*.*.*`, whose two literal dots exclude `@v1` and `@v1.1`, so a moving pin
  fails every release at the credential exchange.
- **The four suppression files:** `frontend/` and `database/`'s `.trivyignore.yaml`
  and `.vex/*.openvex.json` + the `trivyignores` and `vex-documents` keys naming them in
  `.github/docker-hub-publish.yml`, both defaulting to empty: a file the config does not
  name is applied to nothing. [`docs/publish.md`](docs/publish.md) states which is which.
- **The published image names:** this repository's own name + the Docker Hub
  repositories: renaming this GitHub repository renames what a release publishes to.
- **The image reference formula:** `stack/compose.yaml`'s five `image:` keys + the
  config's `images.directories`: `-<service>` must spell a directory it names.
- **The stack's interpolation variables:** the same `image:` keys + the two the release
  workflow sets: `IMAGE_PREFIX` and `IMAGE_TAG`, both defaulted.
- **The called workflow's declared inputs** + `publish.yml`'s `with:`/`secrets:`; the
  `aws-role-arn` **secret** holds the account id.
- **The Docker Hub namespace:** `DOCKERHUB_NAMESPACE` + the account the PAT in SSM
  belongs to, **both outside this repository**.
- **The bake target name:** the three `docker-bake.hcl` files + the target name the
  release workflow fixes: `image`.
- **The `frontend/src/main.tsx` coverage exclusion:** `frontend/vite.config.ts` +
  `sonar-project.properties`: one exclusion, two tools that each name it.
- **The `frontend/src/routeTree.gen.ts` exclusion:** `frontend/.prettierignore` +
  `frontend/vite.config.ts` + `sonar-project.properties`; prettier's half has the gate.
