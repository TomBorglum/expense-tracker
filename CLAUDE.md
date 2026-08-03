# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Branch and merge rules (soft, must be followed)

This repo is on the GitHub **free plan**, so branch protection and required checks
**cannot be enforced**. The rules below are enforced by discipline only - follow
them as if GitHub blocked non-compliant merges. The full rationale lives in
[`CONTRIBUTING.md`](CONTRIBUTING.md); the hard rules:

- **Never push directly to `main`.** Make every change on a branch and open a PR.
- **Squash-merge only** (rebase is fine; **no merge commits**, except the
  multi-entry-branch exception documented in `CONTRIBUTING.md`).
- **The PR title must be a valid Conventional Commit** - it becomes the squashed
  commit subject that release-please parses (`feat`/`fix`/`deps` cut releases;
  other types ride along hidden).
- **Wait for the `SonarCloud Code Analysis` check to pass before merging.**
- **Resolve all review threads before merging.**
- **Keep `main` linear** (no force-pushes) and **delete the branch after merge**:
  `gh pr merge --squash --delete-branch`.
- **Branch naming:** `<type>/<short-kebab-description>` (e.g. `feat/monthly-report`).

## Releases

Releases are automated by [release-please](https://github.com/googleapis/release-please)
via `.github/workflows/release-please.yml`. **Never hand-edit versions, git tags,
or `CHANGELOG.md`** - merging Conventional-Commit PRs into `main` drives the
`.release-please-manifest.json` version, and merging the release PR tags and
publishes the GitHub Release.

## Source conventions

- **ASCII-only** committed source (no em-dashes, smart quotes, arrows, ellipses).
- **Pin dependency versions exactly** (`==` in `pixi.toml`) and **SHA-pin GitHub
  Actions** with a version comment.

## Commands

`pixi run <task>` is the single interface for both stacks - the same commands CI
runs, so passing them locally means passing CI. Every task declares its own `cwd`
in `pixi.toml` (`backend/` or `frontend/`), so it behaves identically no matter
where you invoke it from. The full task table is in
[`README.md`](README.md#development-tasks).

Before opening a PR, run the gate sequence from `.github/workflows/ci.yml`, in
order (cheapest first, so it fails fast):

```sh
pixi run lint && pixi run format-check && pixi run typecheck && pixi run test &&
pixi run web-install && pixi run web-format-check && pixi run web-check &&
pixi run web-lint && pixi run web-test && pixi run web-verify
```

## Build invariants

Break one of these and CI goes red on an otherwise correct change.

- **The committed bundle.** `backend/src/expense_tracker/static/` is vite output
  and **is committed**, so the wheel is self-contained and the `prod` environment
  needs no Node. Any change under `frontend/` must be followed by
  `pixi run web-build` with the result committed - `pixi run web-verify` fails
  otherwise. Rationale in [`README.md`](README.md#frontend).
- **No OpenAPI.** The app exposes `/` (the shell), `GET /api/greeting` (JSON) and
  the `/static` mount, and nothing else; see `create_app()` in
  `backend/src/expense_tracker/__init__.py`. One hand-written route does not earn a
  generated document, so `docs_url`, `redoc_url` and `openapi_url` stay `None` and
  `test_openapi_docs_are_disabled` in `backend/tests/test_app.py` keeps them that
  way. Re-enabling the docs routes, or growing `/api` into a namespace, fails the
  suite **by design**.
- **Two places, one value.** The greeting payload is written by hand at both ends:
  `backend/src/expense_tracker/__init__.py` builds it, and
  `frontend/src/api/greeting.ts` declares the matching type, guard and path. There
  is no schema generating either from the other, so change them together.
  The `@` alias (`frontend/src`) is declared in both `frontend/vite.config.ts`
  (bundler) and `frontend/tsconfig.app.json` (types) - vite does not read tsconfig
  `paths`. The `frontend/src/main.tsx` coverage exclusion is declared in both
  `frontend/vite.config.ts` and `sonar-project.properties`. Change each pair
  together.
- **Every linted file needs a tsconfig that owns it.** eslint runs type-aware via
  `parserOptions.projectService`, so a `.ts`/`.tsx` file outside every tsconfig's
  `include` fails to lint rather than being skipped. `src/` and `tests/` come from
  `tsconfig.app.json`; `vite.config.ts` and `eslint.config.ts` are listed in
  `tsconfig.node.json`. A new file at the `frontend/` root has to be added there
  too.
- **`frontend/package.json` must not gain a `packageManager` field**, and
  `frontend/pnpm-lock.yaml` must stay at `lockfileVersion: 9.0`. The first would
  bypass the pnpm pin in `pixi.toml`; both would break Dependabot's lockfile
  parsing. See [`README.md`](README.md#package-manager) and
  `.github/dependabot.yml`.
- **`frontend/pnpm-workspace.yaml` must not gain a `minimumReleaseAge` exemption.**
  It exists only to answer `allowBuilds` (pnpm 11 no longer reads the `pnpm` field
  in `package.json`, and an unanswered install script makes `pixi run web-install`
  exit non-zero). Exempting a version would disable the 24-hour supply-chain guard
  for precisely the least-vetted release; pick a version that already clears the
  window instead.

## Quality gates

- **Python:** basedpyright in `strict` mode, and ruff with
  `select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]` - both configured in
  `backend/pyproject.toml`.
- **Frontend:** `tsc -b` against a `strict` tsconfig, prettier, and eslint 10 in
  `frontend/eslint.config.ts` - typescript-eslint `strictTypeChecked` +
  `stylisticTypeChecked` (type-aware, via `parserOptions.projectService`), ESLint
  React `strict-type-checked`, `eslint-plugin-react-hooks`, `react-refresh`, the
  vitest plugin over `tests/`, and `perfectionist/sort-imports` for import order.
  `eslint-config-prettier` is applied last, so **the linter owns correctness and
  prettier owns formatting** - never add a formatting rule to the eslint config.
- **There is no warn tier on the frontend.** The `lint` script runs
  `eslint . --max-warnings 0`, so a warning fails the build exactly like an error.
  Without it the plugins' own severities would leave roughly 45 rules advisory -
  including the XSS, `target="_blank"` and leaked-timer rules, `exhaustive-deps`,
  `vitest/no-disabled-tests`, and `reportUnusedDisableDirectives` (so stale
  suppressions would never be reported). Demote a rule deliberately in
  `eslint.config.ts` if you disagree with it; do not let the flag go.
- **Suppressions carry a reason.** Match the existing style: an inline comment
  next to the pragma saying why, as with the two
  `# pyright: ignore[reportUnusedFunction]` in
  `backend/src/expense_tracker/__init__.py`. On the frontend that means an
  `// eslint-disable-next-line <rule>` with the reason on the line above or beside
  it - a bare disable is not acceptable.
