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
pixi run web-lint && pixi run web-test && pixi run web-build
```

The two halves are independent - the backend gates never touch `frontend/` and the
frontend gates never touch `backend/` - so when you have changed only one stack, only
that stack's gates can fail.

## Build invariants

Break one of these and CI goes red on an otherwise correct change.

- **The backend serves no frontend.** It is a REST API: `GET /api/greeting` and
  nothing else. There is no `/` route, no `StaticFiles` mount and no build artifact
  under `backend/`. `test_root_is_not_served` and `test_static_files_are_not_served`
  in `backend/tests/test_app.py` keep it that way. The frontend builds to
  `frontend/dist/`, which is **gitignored** and consumed by nobody in this repo -
  packaging the two into one deployable is out of scope.
- **No OpenAPI.** The app exposes `GET /api/greeting` and nothing else; see
  `create_app()` in `backend/src/expense_tracker/__init__.py`. One hand-written route
  does not earn a generated document, so `docs_url`, `redoc_url` and `openapi_url`
  stay `None` and `test_openapi_docs_are_disabled` keeps them that way. Re-enabling
  the docs routes, or growing `/api` into a namespace, fails the suite **by design**.
- **CORS is open, and that is a dev-time posture.** `create_app()` adds
  `CORSMiddleware` with `allow_origins=["*"]` and **`allow_credentials=False`**. The
  two cannot be combined - the CORS spec forbids it and browsers reject the pair - so
  the day the API grows cookies or an `Authorization` header, the wildcard is what
  has to become a real origin list. `test_cors_does_not_allow_credentials` pins it.
  It is registered **after** the security-headers middleware, which makes it the
  outermost of the two and is what lets it answer a preflight itself.
- **Two places, one value.** The greeting payload is written by hand at both ends:
  `backend/src/expense_tracker/__init__.py` builds it, and
  `frontend/src/api/greeting.ts` declares the matching type, guard and path. There is
  no schema generating either from the other, and nothing checks the agreement now
  that the stacks build separately - so change them together. Three more pairs:
  the `@` alias (`frontend/src`) is declared in both `frontend/vite.config.ts`
  (bundler) and `frontend/tsconfig.app.json` (types) - vite does not read tsconfig
  `paths`; the `frontend/src/main.tsx` coverage exclusion is declared in both
  `frontend/vite.config.ts` and `sonar-project.properties`; and `VITE_API_BASE_URL`
  is set in `frontend/.env` and typed in `frontend/src/vite-env.d.ts`.
- **The API origin lives in bare `frontend/.env`, not `.env.development`.** vite
  loads `.env` in *every* mode, including the `test` mode vitest runs in, and MSW
  binds its handlers to the URL built from it. `frontend/vite.config.ts` also pins
  `envDir` to `frontend/`, because the `test` block moves vite's `root` to the repo
  root and `envDir` would otherwise follow it and find no `.env`.
- **Every linted file needs a tsconfig that owns it.** eslint runs type-aware via
  `parserOptions.projectService`, so a `.ts`/`.tsx` file outside every tsconfig's
  `include` fails to lint rather than being skipped. `src/` and `tests/` come from
  `tsconfig.app.json`; `vite.config.ts` and `eslint.config.ts` are listed in
  `tsconfig.node.json`. A new file at the `frontend/` root has to be added there
  too. For the same reason `frontend/eslint.config.ts` opens with
  `globalIgnores(["dist"])` - eslint only skips `node_modules` on its own, and the
  emitted bundle is JS no tsconfig includes.
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

- **Python:** basedpyright in `recommended` mode and ruff with
  `select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]` - both in `backend/pyproject.toml`.
  There is **no config file at the repo root** and **no Python setting duplicated in the
  editor config** - `.zed/settings.json` pins the server *binary* to the pixi env and
  nothing else. Editors need no pointer to the config: Zed reads
  `backend/pyproject.toml` as the project manifest and sends `backend/` as the LSP
  workspace folder, which is what the server resolves its config against. That matters
  because basedpyright ignores a developer's personal `typeCheckingMode` *only when it
  finds a project config* - finding this one is what makes the repo's setting win over
  a contributor's own.
- **There is no warn tier on the backend either.** `recommended` is a superset of
  pyright's `strict` that adds the based-only rules and sets `failOnWarnings`, so a
  warning fails `pixi run typecheck` like an error. It is why line 52 of
  `backend/src/expense_tracker/__init__.py` reads `_ = response.headers.setdefault(...)`:
  `reportUnusedCallResult` wants a discarded return value said out loud.
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
